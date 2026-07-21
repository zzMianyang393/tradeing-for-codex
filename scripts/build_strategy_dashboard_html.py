"""Build a self-contained HTML dashboard explaining research outcomes + charts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _downsample(points: list[dict], max_points: int = 180) -> list[dict]:
    if len(points) <= max_points:
        return points
    step = max(1, len(points) // max_points)
    out = points[::step]
    if out[-1] is not points[-1]:
        out.append(points[-1])
    return out


def load_chart_payloads(root: Path) -> dict:
    charts: dict = {}

    # 10U informal full history equity from trades
    ten_u = root / "reports/ten_u_event_trend_informal_full_history_v2.json"
    if ten_u.exists():
        j = json.loads(ten_u.read_text(encoding="utf-8"))
        trades = j.get("trades") or []
        eq = [{"t": "start", "equity": 10.0, "label": "start"}]
        for tr in trades:
            eq.append(
                {
                    "t": (tr.get("exit") or tr.get("entry") or "")[:10],
                    "equity": float(tr.get("equity_after") or 0),
                    "label": f"{tr.get('symbol','')} {tr.get('direction','')} pnl={tr.get('net_pnl')}",
                }
            )
        charts["ten_u_event_trend_v2_informal"] = {
            "title": "10U Event Trend v2（全量非正式回放权益）",
            "subtitle": "注意：收益高度依赖少数大单；非正式/污染窗，非交易批准",
            "type": "equity_from_trades",
            "series": eq,
            "trades": trades,
            "metrics": j.get("account_summary") or {},
        }

    # sealed screen path if present
    screen = root / "reports/ten_u_event_trend_screen_v2.json"
    if screen.exists():
        j = json.loads(screen.read_text(encoding="utf-8"))
        acc = j.get("account") or {}
        details = acc.get("trades_detail") or []
        eq = [{"t": "start", "equity": float(acc.get("starting_equity") or 10), "label": "start"}]
        for tr in details:
            # may only have equity_after
            tlabel = str(tr.get("exit_ts") or tr.get("entry_ts") or "")
            if isinstance(tr.get("exit_ts"), int):
                tlabel = _iso(int(tr["exit_ts"]))
            eq.append(
                {
                    "t": tlabel[:16],
                    "equity": float(tr.get("equity_after") or eq[-1]["equity"]),
                    "label": f"{tr.get('symbol')} {tr.get('exit_reason')}",
                }
            )
        charts["ten_u_event_trend_v2_sealed"] = {
            "title": "10U Event Trend v2（密封窗 45 天）",
            "subtitle": "仅 3 笔；状态 insufficient_evidence",
            "type": "equity_from_trades",
            "series": eq,
            "trades": [
                {
                    "symbol": t.get("symbol"),
                    "net_pnl": t.get("net_pnl"),
                    "equity_after": t.get("equity_after"),
                    "exit_reason": t.get("exit_reason"),
                }
                for t in details
            ],
            "metrics": {
                "ending_equity": acc.get("ending_equity"),
                "return_fraction": acc.get("return_fraction"),
                "trades": acc.get("trades"),
                "profit_factor": acc.get("profit_factor"),
                "max_drawdown_fraction": acc.get("max_drawdown_fraction"),
            },
        }

    # low vol fixed risk
    lv = root / "reports/low_volatility_drift_fixed_risk_audit.json"
    if lv.exists():
        j = json.loads(lv.read_text(encoding="utf-8"))
        agg = j.get("aggregate") or {}
        ec = agg.get("equity_curve") or []
        series = [
            {"t": _iso(int(p["ts"])), "equity": float(p["equity"])}
            for p in _downsample(ec, 200)
            if isinstance(p, dict) and "equity" in p
        ]
        charts["low_volatility_drift_bb_breakout_fixed_risk_v1"] = {
            "title": "低波漂移布林突破（固定风险）历史权益",
            "subtitle": "历史约 +64%，状态 frozen_awaiting_prospective——未批准交易",
            "type": "equity_curve",
            "series": series,
            "metrics": {
                "total_return_pct": agg.get("total_return_pct"),
                "max_drawdown_pct": agg.get("max_drawdown_pct"),
                "accepted_positions": agg.get("accepted_positions"),
                "final_equity": agg.get("final_equity"),
                "initial_equity": agg.get("initial_equity"),
                "status": j.get("status"),
            },
            "folds": {
                name: {
                    "return_hint": (
                        (fold.get("aggregate") or fold).get("total_return_pct")
                        if isinstance(fold, dict)
                        else None
                    )
                }
                for name, fold in (j.get("folds") or {}).items()
            },
        }

    return charts


def build_html(inventory: dict, charts: dict) -> str:
    inv_json = json.dumps(inventory, ensure_ascii=False)
    charts_json = json.dumps(charts, ensure_ascii=False)
    # escape for script tag
    inv_json = inv_json.replace("</", "<\\/")
    charts_json = charts_json.replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>策略研究总览 — 为什么全军覆没？</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg: #0b1020;
      --card: #141b2d;
      --text: #e8eefc;
      --muted: #9aa8c7;
      --accent: #5b8cff;
      --bad: #ff6b7a;
      --ok: #3dd68c;
      --warn: #ffc857;
      --line: #243049;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
      background: radial-gradient(1200px 600px at 10% -10%, #1a2744 0%, var(--bg) 55%);
      color: var(--text); line-height: 1.55;
    }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 28px 18px 80px; }}
    h1 {{ font-size: 1.75rem; margin: 0 0 8px; }}
    h2 {{ font-size: 1.25rem; margin: 28px 0 12px; }}
    h3 {{ font-size: 1.05rem; margin: 18px 0 8px; color: #cfe0ff; }}
    p, li {{ color: var(--muted); }}
    .hero {{
      background: linear-gradient(135deg, #18233b, #10182a);
      border: 1px solid var(--line); border-radius: 16px; padding: 22px 22px 10px;
      box-shadow: 0 12px 40px rgba(0,0,0,.35);
    }}
    .badge {{
      display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px;
      background: #2a1a22; color: var(--bad); border: 1px solid #5a2a35; margin-right: 8px;
    }}
    .badge.ok {{ background: #13291f; color: var(--ok); border-color: #1f5a3d; }}
    .badge.warn {{ background: #2a2414; color: var(--warn); border-color: #5a4a1f; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap: 12px; margin: 16px 0; }}
    .card {{
      background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px;
    }}
    .card strong {{ display: block; font-size: 1.4rem; color: var(--text); }}
    .card span {{ font-size: 12px; color: var(--muted); }}
    .callout {{
      border-left: 4px solid var(--accent); background: #121a2c; padding: 12px 14px;
      border-radius: 0 10px 10px 0; margin: 14px 0;
    }}
    .callout.warn {{ border-left-color: var(--warn); }}
    .callout.bad {{ border-left-color: var(--bad); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px 6px; text-align: left; vertical-align: top; }}
    th {{ color: #bcd0ff; position: sticky; top: 0; background: #10182a; }}
    tr:hover td {{ background: rgba(91,140,255,.06); }}
    .status {{ font-family: ui-monospace, Consolas, monospace; font-size: 11px; color: #9ec1ff; }}
    input, select {{
      background: #0e1526; color: var(--text); border: 1px solid var(--line);
      border-radius: 8px; padding: 8px 10px; width: 100%;
    }}
    .filters {{ display: grid; grid-template-columns: 1fr 180px 180px; gap: 10px; margin: 12px 0; }}
    @media (max-width: 800px) {{ .filters {{ grid-template-columns: 1fr; }} }}
    .chart-box {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 12px; margin: 12px 0 20px; }}
    canvas {{ max-height: 320px; }}
    .muted {{ color: var(--muted); font-size: 13px; }}
    code {{ background: #0e1526; padding: 1px 6px; border-radius: 4px; }}
    .pill {{ display:inline-block; padding:2px 8px; border-radius:6px; background:#1b2438; margin: 0 4px 4px 0; font-size:11px; }}
  </style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <span class="badge">获准交易：0</span>
    <span class="badge warn">研究条目：见下方</span>
    <h1>策略研究总览：为什么烧了很多 token，却一个都没通过？</h1>
    <p>这份页面把「测试太严 vs 策略本身没边」说清楚，并汇总全部注册策略状态；有历史权益序列的会画收益曲线。
    <br/><span class="muted">生成时间：{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} · 本地文件打开即可（数据已内嵌）</span></p>
  </div>

  <h2>1. 先回答你的核心疑问</h2>
  <div class="grid" id="kpi"></div>

  <div class="callout bad">
    <strong style="color:var(--text)">不是单纯「测试写坏了」。</strong>
    <p style="margin:6px 0 0">大部分失败写的是：扣完手续费/滑点后期望为负、样本外翻车、或利润全靠少数月份/单币。
    这和「程序算错」不同——是按你这套研究纪律在问：<em>扣真实成本后，换一段时间、换一批币，还赚钱吗？</em></p>
  </div>

  <div class="callout warn">
    <strong style="color:var(--text)">规则确实偏严，但严的是「批准上交易」的门，不是「允许你看一眼历史曲线」的门。</strong>
    <p style="margin:6px 0 0">对小资金，严格是有意的：集中度高、前视偏差、成本吃光的东西，上实盘会更快归零。
    不过：有几条历史曲线其实「看起来不错」（例如低波突破约 +64%），它们被挡在门外是因为
    <strong>还没过可重复性/集中度/前瞻</strong>，不是因为回测引擎拒绝显示数字。</p>
  </div>

  <h3>失败原因通常分 5 类（不是一种「过严」）</h3>
  <ol>
    <li><strong>成本墙</strong>：毛利有、扣 0.05%×2 + 滑点 + 多腿后变负（基差、funding carry、跨期最典型）。</li>
    <li><strong>样本外失效</strong>：形成期还行，换一段日子就亏（多数趋势/突破模板）。</li>
    <li><strong>集中度/故事单</strong>：总收益正，但一两个月或一个币贡献过大（布林回归、10U 的 RAVE）。</li>
    <li><strong>方法作废</strong>：前视、标签污染、旧路由复用 → 标 invalid，数字直接作废。</li>
    <li><strong>证据不够</strong>：交易太少、窗口太短，不判「通过」（不等于「证明亏」）。</li>
  </ol>

  <div class="callout">
    <strong style="color:var(--text)">对小白的大白话</strong>
    <p style="margin:6px 0 0">
      Token 买到的是一套「很难骗自己」的筛子 + 一堆「在这套筛子下不成立」的实验记录。
      这很打击人，但比「回测很好看、实盘归零」便宜。
      <br/>若你想要「更容易通过」：可以主动放宽批准门槛（例如允许 paper 观察历史为正的候选），
      那是<strong>产品决策</strong>，不是证明市场突然有了 edge。
    </p>
  </div>

  <h2>2. 有权益曲线的重点案例</h2>
  <p class="muted">完整「每笔交易画在 K 线上」需要逐策略重放行情，报告里通常只存事件/权益点。
  下面优先展示<strong>已有权益序列或成交权益路径</strong>的策略。点击图例可切换。</p>
  <div id="charts"></div>

  <h2>3. 全部策略状态表（可筛选）</h2>
  <div class="filters">
    <input id="q" placeholder="搜索 ID / 名称 / 原因关键词…" />
    <select id="statusFilter"><option value="">全部状态</option></select>
    <select id="sourceFilter"><option value="">全部来源</option></select>
  </div>
  <div class="card" style="overflow:auto; max-height:70vh;">
    <table>
      <thead>
        <tr>
          <th>ID</th><th>名称</th><th>状态</th><th>历史线索</th><th>为何不通过 / 说明</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>

  <h2>4. 接下来你可以怎么做（务实）</h2>
  <ul>
    <li><strong>不要</strong>把「0 通过」理解成程序坏了；优先理解失败类型分布。</li>
    <li>若目标是<strong>先看盘理解</strong>：从本页曲线 + 观察名单开始（低波突破、周频截面空等）。</li>
    <li>若目标是<strong>要能交易</strong>：需要新研究 epoch + 你愿意接受的放宽门槛，而不是重复旧闸门。</li>
    <li>若目标是<strong>每笔交易的 K 线标注</strong>：下一步可对 1～2 个候选做专用回放页（按策略拉 15m/1H 画 entry/exit）。</li>
  </ul>
  <p class="muted">数据来源：<code>reports/prod/strategy_status_inventory.json</code> 与关键 audit 报告内嵌生成。</p>
</div>

<script>
const INVENTORY = {inv_json};
const CHARTS = {charts_json};

function kpi() {{
  const s = INVENTORY.strategies || [];
  const el = document.getElementById('kpi');
  const by = INVENTORY.counts_by_status || {{}};
  const rejected = (by.rejected||0)+(by.historical_rejected||0)+(by.rejected_at_formation||0);
  const watch = Object.entries(by).filter(([k]) => k.includes('watch') || k.includes('frozen_awaiting') || k.includes('posthoc') || k.includes('combo_watchlist')).reduce((a,[,v])=>a+v,0);
  el.innerHTML = `
    <div class="card"><strong>0</strong><span>获准 paper / 实盘</span></div>
    <div class="card"><strong>${{s.length}}</strong><span>注册/观察条目</span></div>
    <div class="card"><strong>${{rejected}}</strong><span>明确拒绝类</span></div>
    <div class="card"><strong>${{watch}}</strong><span>观察/冻结（仍非批准）</span></div>
  `;
}}

function histOf(r) {{
  if (r.hist_return_pct != null) {{
    let t = `ret≈${{Number(r.hist_return_pct).toFixed(2)}}%`;
    if (r.hist_dd_pct != null) t += `, DD≈${{Number(r.hist_dd_pct).toFixed(2)}}%`;
    if (r.hist_note) t += ` (${{r.hist_note}})`;
    return t;
  }}
  if (r.display) return r.display;
  const mh = (INVENTORY.metric_hints||{{}})[r.id];
  if (mh && mh.return_fraction != null) return `ret≈${{(Number(mh.return_fraction)*100).toFixed(2)}}%`;
  if (mh && mh.return_pct != null) return `ret≈${{mh.return_pct}}`;
  return '—';
}}

function fillFilters() {{
  const statuses = [...new Set((INVENTORY.strategies||[]).map(x=>x.status).filter(Boolean))].sort();
  const sources = [...new Set((INVENTORY.strategies||[]).map(x=>x.source).filter(Boolean))].sort();
  const sf = document.getElementById('statusFilter');
  const of = document.getElementById('sourceFilter');
  statuses.forEach(s => {{ const o=document.createElement('option'); o.value=s; o.textContent=s; sf.appendChild(o); }});
  sources.forEach(s => {{ const o=document.createElement('option'); o.value=s; o.textContent=s; of.appendChild(o); }});
}}

function renderTable() {{
  const q = document.getElementById('q').value.trim().toLowerCase();
  const st = document.getElementById('statusFilter').value;
  const so = document.getElementById('sourceFilter').value;
  const tb = document.getElementById('tbody');
  tb.innerHTML = '';
  (INVENTORY.strategies||[]).forEach(r => {{
    const blob = `${{r.id}} ${{r.name_cn||''}} ${{r.status||''}} ${{r.reason||''}}`.toLowerCase();
    if (q && !blob.includes(q)) return;
    if (st && r.status !== st) return;
    if (so && r.source !== so) return;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><code>${{r.id||''}}</code></td>
      <td>${{r.name_cn||''}}</td>
      <td class="status">${{r.status||''}}</td>
      <td>${{histOf(r)}}</td>
      <td>${{(r.reason||'').replace(/</g,'&lt;')}}</td>`;
    tb.appendChild(tr);
  }});
}}

function renderCharts() {{
  const host = document.getElementById('charts');
  const ids = Object.keys(CHARTS);
  if (!ids.length) {{
    host.innerHTML = '<p class="muted">未找到可内嵌的权益曲线文件。</p>';
    return;
  }}
  ids.forEach((id, idx) => {{
    const c = CHARTS[id];
    const box = document.createElement('div');
    box.className = 'chart-box';
    const m = c.metrics || {{}};
    const pills = Object.entries(m).slice(0,8).map(([k,v]) => `<span class="pill">${{k}}: ${{typeof v==='number'?(Math.abs(v)<10?Number(v).toFixed(4):Number(v).toFixed(2)):v}}</span>`).join('');
    box.innerHTML = `<h3>${{c.title}}</h3><p class="muted">${{c.subtitle||''}}</p><div>${{pills}}</div><canvas id="c${{idx}}"></canvas>`;
    host.appendChild(box);
    const labels = (c.series||[]).map(p => p.t);
    const data = (c.series||[]).map(p => p.equity);
    new Chart(document.getElementById('c'+idx), {{
      type: 'line',
      data: {{
        labels,
        datasets: [{{
          label: 'Equity',
          data,
          borderColor: '#5b8cff',
          backgroundColor: 'rgba(91,140,255,.15)',
          fill: true,
          tension: 0.15,
          pointRadius: data.length > 80 ? 0 : 2,
        }}]
      }},
      options: {{
        responsive: true,
        plugins: {{ legend: {{ labels: {{ color: '#cfe0ff' }} }} }},
        scales: {{
          x: {{ ticks: {{ color: '#9aa8c7', maxTicksLimit: 10 }}, grid: {{ color: '#1c2740' }} }},
          y: {{ ticks: {{ color: '#9aa8c7' }}, grid: {{ color: '#1c2740' }} }}
        }}
      }}
    }});
    if (c.trades && c.trades.length && c.trades.length <= 40) {{
      const pre = document.createElement('pre');
      pre.className = 'muted';
      pre.style.whiteSpace = 'pre-wrap';
      pre.style.fontSize = '11px';
      pre.textContent = c.trades.map(t => JSON.stringify(t)).join('\\n');
      box.appendChild(pre);
    }}
  }});
}}

kpi();
fillFilters();
renderTable();
renderCharts();
document.getElementById('q').addEventListener('input', renderTable);
document.getElementById('statusFilter').addEventListener('change', renderTable);
document.getElementById('sourceFilter').addEventListener('change', renderTable);
</script>
</body>
</html>
"""


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    inv_path = root / "reports/prod/strategy_status_inventory.json"
    if not inv_path.exists():
        # try build
        import subprocess
        import sys

        subprocess.check_call([sys.executable, str(root / "scripts/build_strategy_status_inventory.py")])
    inventory = json.loads(inv_path.read_text(encoding="utf-8"))
    charts = load_chart_payloads(root)
    html = build_html(inventory, charts)
    out = root / "reports/prod/strategy_research_dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    # also copy to docs for discoverability
    docs_out = root / "docs/strategy_research_dashboard.html"
    docs_out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}")
    print(f"Wrote {docs_out}")
    print(f"charts: {list(charts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
