"""Multi-strategy candlestick dashboard with equity overlay (TV-style).

Embeds chartable strategies that have local price data + trades/equity.
Other registered strategies appear as 'no chart data' in the list.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def _iso_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def parse_ts_any(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = int(value)
        return v // 1000 if v > 10_000_000_000 else v
    text = str(value).replace("Z", "+00:00")
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def load_ohlcv_csv(path: Path, *, bar_seconds: int | None = None) -> list[dict]:
    """Load OHLCV; if bar_seconds set, resample from finer bars."""
    raw: list[dict] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        # support event_trend full and generic 15m exports
        for row in reader:
            try:
                if "timestamp_ms" in row:
                    t = int(row["timestamp_ms"]) // 1000
                elif "ts" in row:
                    t = parse_ts_any(row["ts"]) or 0
                elif "timestamp" in row:
                    t = parse_ts_any(row["timestamp"]) or 0
                else:
                    continue
                o = float(row.get("open") or row.get("o"))
                h = float(row.get("high") or row.get("h"))
                l = float(row.get("low") or row.get("l"))
                c = float(row.get("close") or row.get("c"))
                vol = float(
                    row.get("volume_quote")
                    or row.get("volume")
                    or row.get("volume_base")
                    or 0
                )
                raw.append({"time": t, "open": o, "high": h, "low": l, "close": c, "volume": vol})
            except (TypeError, ValueError, KeyError):
                continue
    raw.sort(key=lambda x: x["time"])
    if not bar_seconds or not raw:
        return raw
    # resample to bar_seconds (e.g. 3600 for 1H from 15m)
    buckets: dict[int, dict] = {}
    for bar in raw:
        key = bar["time"] - (bar["time"] % bar_seconds)
        b = buckets.get(key)
        if b is None:
            buckets[key] = {
                "time": key,
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "volume": bar["volume"],
            }
        else:
            b["high"] = max(b["high"], bar["high"])
            b["low"] = min(b["low"], bar["low"])
            b["close"] = bar["close"]
            b["volume"] += bar["volume"]
    return [buckets[k] for k in sorted(buckets)]


def downsample(points: list[dict], max_n: int = 250) -> list[dict]:
    if len(points) <= max_n:
        return points
    step = max(1, len(points) // max_n)
    out = points[::step]
    if out[-1] is not points[-1]:
        out.append(points[-1])
    return out


def symbol_to_15m_path(root: Path, symbol: str) -> Path | None:
    base = symbol.replace("-USDT-SWAP", "").replace("-USDT", "")
    p = root / "data" / f"{base}_15m.csv"
    return p if p.exists() else None


def build_ten_u(root: Path) -> dict | None:
    data_dir = root / "data" / "event_trend_v1"
    files = {
        "RAVE-USDT-SWAP": data_dir / "RAVE_1h_full.csv",
        "LAB-USDT-SWAP": data_dir / "LAB_1h_full.csv",
        "ETH-USDT-SWAP": data_dir / "ETH_1h_full.csv",
    }
    candles = {}
    for sym, path in files.items():
        if path.exists():
            candles[sym] = load_ohlcv_csv(path)

    informal_path = root / "reports/ten_u_event_trend_informal_full_history_v2.json"
    if not informal_path.exists() or not candles:
        return None
    j = json.loads(informal_path.read_text(encoding="utf-8"))
    trades = []
    equity = [{"time": None, "equity": 10.0}]
    for i, t in enumerate(j.get("trades") or []):
        et = parse_ts_any(t.get("entry"))
        xt = parse_ts_any(t.get("exit"))
        if et is None or xt is None:
            continue
        trades.append(
            {
                "id": i + 1,
                "symbol": t.get("symbol"),
                "direction": t.get("direction"),
                "entry_time": et,
                "exit_time": xt,
                "entry_iso": t.get("entry"),
                "exit_iso": t.get("exit"),
                "exit_reason": t.get("exit_reason"),
                "net_pnl": t.get("net_pnl"),
                "equity_after": t.get("equity_after"),
            }
        )
        equity.append({"time": xt, "equity": float(t.get("equity_after") or 0)})
    # fix first equity time to first candle
    if equity and candles:
        first_t = min(c[0]["time"] for c in candles.values() if c)
        equity[0]["time"] = first_t

    acc = j.get("account_summary") or {}
    return {
        "id": "ten_u_event_trend_v2",
        "name": "10U 战神 Event Trend v2（非正式全量）",
        "status": "active_research_not_validated",
        "timeframe": "1H",
        "note": "污染窗/非正式回放；非交易批准。右侧纵轴为账户权益(USDT)。",
        "metrics": {
            "ending_equity": acc.get("ending_equity"),
            "return_pct": round(float(acc.get("return_fraction") or 0) * 100, 2),
            "max_dd_pct": round(float(acc.get("max_drawdown_fraction") or 0) * 100, 2),
            "trades": acc.get("trades"),
            "profit_factor": acc.get("profit_factor"),
        },
        "candles": candles,
        "trades": trades,
        "equity": equity,
        "default_symbol": "RAVE-USDT-SWAP"
        if any(t["symbol"] == "RAVE-USDT-SWAP" for t in trades)
        else (trades[0]["symbol"] if trades else "ETH-USDT-SWAP"),
    }


def build_low_vol(root: Path) -> dict | None:
    path = root / "reports/low_volatility_drift_fixed_risk_audit.json"
    if not path.exists():
        return None
    j = json.loads(path.read_text(encoding="utf-8"))
    agg = j.get("aggregate") or {}
    closed = agg.get("closed_positions") or []
    if not closed:
        return None

    # top symbols by trade count
    counts = Counter(t.get("symbol") for t in closed if t.get("symbol"))
    top_symbols = [s for s, _ in counts.most_common(8)]

    candles: dict[str, list] = {}
    for sym in top_symbols:
        p15 = symbol_to_15m_path(root, sym)
        if p15:
            # resample 15m -> 1H to keep HTML size reasonable
            candles[sym] = load_ohlcv_csv(p15, bar_seconds=3600)

    ec = agg.get("equity_curve") or []
    equity = []
    for p in downsample(ec, 300):
        if isinstance(p, dict) and "equity" in p:
            t = parse_ts_any(p.get("ts"))
            if t:
                equity.append({"time": t, "equity": float(p["equity"])})

    trades = []
    for i, t in enumerate(closed):
        et = parse_ts_any(t.get("entry_ts") or t.get("entry_timestamp_utc"))
        xt = parse_ts_any(t.get("exit_ts") or t.get("exit_timestamp_utc"))
        if et is None or xt is None:
            continue
        if t.get("symbol") not in candles:
            continue  # only chartable symbols
        trades.append(
            {
                "id": i + 1,
                "symbol": t.get("symbol"),
                "direction": t.get("direction"),
                "entry_time": et,
                "exit_time": xt,
                "entry_iso": t.get("entry_timestamp_utc") or _iso_ms(et * 1000),
                "exit_iso": t.get("exit_timestamp_utc") or _iso_ms(xt * 1000),
                "exit_reason": t.get("exit_reason") or "",
                "net_pnl": t.get("realized_pnl"),
                "equity_after": None,
                "entry_price": t.get("entry_price"),
                "exit_price": t.get("exit_price"),
            }
        )

    if not candles:
        return None

    return {
        "id": "low_volatility_drift_bb_breakout_fixed_risk_v1",
        "name": "低波漂移布林突破（固定风险）",
        "status": str(j.get("status") or "frozen_awaiting_prospective"),
        "timeframe": "1H（由15m合成）",
        "note": "多币组合账户权益叠在所选币K线上（右轴）。仅嵌入成交最多的币种K线。未批准交易。",
        "metrics": {
            "return_pct": agg.get("total_return_pct"),
            "max_dd_pct": agg.get("max_drawdown_pct"),
            "trades": agg.get("accepted_positions"),
            "final_equity": agg.get("final_equity"),
            "initial_equity": agg.get("initial_equity"),
            "win_rate": agg.get("realized_win_rate"),
        },
        "candles": candles,
        "trades": trades,
        "equity": equity,
        "default_symbol": top_symbols[0] if top_symbols else "ETH-USDT-SWAP",
        "symbol_trade_counts": dict(counts.most_common(15)),
    }


def build_no_data_list(root: Path, chartable_ids: set[str]) -> list[dict]:
    inv = root / "reports/prod/strategy_status_inventory.json"
    if not inv.exists():
        return []
    rows = json.loads(inv.read_text(encoding="utf-8")).get("strategies") or []
    out = []
    for r in rows:
        rid = r.get("id")
        if rid in chartable_ids:
            continue
        out.append(
            {
                "id": rid,
                "name": r.get("name_cn") or rid,
                "status": r.get("status"),
                "reason": (r.get("reason") or "")[:160],
                "hist": r.get("hist_return_pct") or r.get("display") or "—",
            }
        )
    return out


def html_page(payload: dict) -> str:
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>多策略 K 线 + 权益叠加</title>
  <script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
  <style>
    :root {{
      --bg:#0b0e11; --panel:#131722; --border:#1e222d; --text:#d1d4dc;
      --muted:#787b86; --green:#26a69a; --red:#ef5350; --blue:#2962ff; --gold:#f0b90b;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--text); }}
    header {{ padding:12px 16px; background:var(--panel); border-bottom:1px solid var(--border); }}
    header h1 {{ margin:0; font-size:16px; }}
    header p {{ margin:6px 0 0; color:var(--muted); font-size:12px; line-height:1.5; }}
    .toolbar {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; padding:10px 16px; background:#0f1318; border-bottom:1px solid var(--border); }}
    label {{ font-size:12px; color:var(--muted); }}
    select, button {{ background:#1c212b; color:var(--text); border:1px solid var(--border); border-radius:6px; padding:6px 10px; font-size:13px; }}
    button {{ cursor:pointer; }}
    button:hover {{ border-color:var(--blue); }}
    .layout {{ display:grid; grid-template-columns: 1fr 340px; height: calc(100vh - 130px); }}
    @media(max-width:1000px){{ .layout{{ grid-template-columns:1fr; height:auto; }} #side{{ max-height:320px; }} }}
    #chartBox {{ min-height:520px; border-right:1px solid var(--border); position:relative; }}
    #side {{ overflow:auto; background:var(--panel); }}
    .trade {{ padding:10px 12px; border-bottom:1px solid var(--border); cursor:pointer; font-size:12px; }}
    .trade:hover, .trade.on {{ background:#1a2030; }}
    .long {{ color:var(--green); }} .short {{ color:var(--red); }}
    .pos {{ color:var(--green); }} .neg {{ color:var(--red); }}
    .meta {{ color:var(--muted); font-size:11px; }}
    .pill {{ display:inline-block; background:#1b2438; padding:2px 8px; border-radius:999px; font-size:11px; margin:2px 4px 2px 0; }}
    .section {{ padding:10px 12px; border-bottom:1px solid var(--border); }}
    .warn {{ color:#f0b90b; }}
    #nodata {{ padding:12px; font-size:12px; color:var(--muted); }}
    #nodata details {{ margin-top:8px; }}
    #nodata summary {{ cursor:pointer; color:#9ec1ff; }}
  </style>
</head>
<body>
<header>
  <h1>多策略蜡烛图 + 账户权益叠加</h1>
  <p>
    主图：K 线（选中币种）· 右轴金色线：账户权益（该策略回测的资金曲线）· 箭头/圆点：开平仓。<br/>
    只有本地存在「价格 + 成交/权益」的策略能画图；其余列在右侧「无图数据」。权益是<strong>整账户</strong>，不是单币仓位盈亏。
  </p>
</header>
<div class="toolbar">
  <label>策略
    <select id="strategy"></select>
  </label>
  <label>币种（K线）
    <select id="symbol"></select>
  </label>
  <button type="button" id="fit">全图</button>
  <button type="button" id="toggleEq">切换权益线</button>
  <span class="meta" id="stats"></span>
</div>
<div class="layout">
  <div id="chartBox"></div>
  <div id="side">
    <div class="section" id="metrics"></div>
    <div class="section meta">点击成交 → 缩放到该笔；权益线对应当时<strong>账户总权益</strong></div>
    <div id="trades"></div>
    <div id="nodata"></div>
  </div>
</div>
<script>
const DATA = {blob};
let showEquity = true;
let chart, candleSeries, equitySeries;

const strategySel = document.getElementById('strategy');
const symbolSel = document.getElementById('symbol');
const tradesEl = document.getElementById('trades');
const metricsEl = document.getElementById('metrics');
const statsEl = document.getElementById('stats');
const nodataEl = document.getElementById('nodata');

(DATA.strategies || []).forEach(s => {{
  const o = document.createElement('option');
  o.value = s.id; o.textContent = s.name;
  strategySel.appendChild(o);
}});

function cur() {{
  return (DATA.strategies || []).find(s => s.id === strategySel.value);
}}

function ensureChart() {{
  if (chart) return;
  const el = document.getElementById('chartBox');
  chart = LightweightCharts.createChart(el, {{
    layout: {{ background: {{ type: 'solid', color: '#0b0e11' }}, textColor: '#d1d4dc' }},
    grid: {{ vertLines: {{ color: '#1e222d' }}, horzLines: {{ color: '#1e222d' }} }},
    crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
    rightPriceScale: {{ borderColor: '#1e222d' }},
    leftPriceScale: {{ visible: true, borderColor: '#1e222d' }},
    timeScale: {{ borderColor: '#1e222d', timeVisible: true, secondsVisible: false }},
  }});
  candleSeries = chart.addCandlestickSeries({{
    upColor: '#26a69a', downColor: '#ef5350',
    borderUpColor: '#26a69a', borderDownColor: '#ef5350',
    wickUpColor: '#26a69a', wickDownColor: '#ef5350',
    priceScaleId: 'right',
  }});
  equitySeries = chart.addLineSeries({{
    color: '#f0b90b',
    lineWidth: 2,
    priceScaleId: 'left',
    title: '账户权益',
  }});
  chart.priceScale('left').applyOptions({{
    scaleMargins: {{ top: 0.1, bottom: 0.2 }},
  }});
  chart.priceScale('right').applyOptions({{
    scaleMargins: {{ top: 0.1, bottom: 0.2 }},
  }});
  const ro = new ResizeObserver(() => {{
    chart.applyOptions({{ width: el.clientWidth, height: el.clientHeight || 520 }});
  }});
  ro.observe(el);
  chart.applyOptions({{ width: el.clientWidth, height: el.clientHeight || 520 }});
}}

function setEquityVisible(v) {{
  showEquity = v;
  if (!equitySeries) return;
  // lightweight-charts v4: applyOptions visible
  equitySeries.applyOptions({{ visible: v }});
}}

function renderNoData() {{
  const list = DATA.no_chart || [];
  nodataEl.innerHTML = `<details><summary>无 K 线数据的策略（${{list.length}}）— 报告里没有可绑定的成交/行情包</summary>
    <div style="max-height:200px;overflow:auto;margin-top:8px">
    ${{list.map(x => `<div style="margin:6px 0"><code>${{x.id}}</code><br/><span class="meta">${{x.status||''}} · ${{x.hist||''}}</span><br/>${{(x.reason||'').slice(0,120)}}</div>`).join('')}}
    </div></details>`;
}}

function loadStrategy() {{
  ensureChart();
  const s = cur();
  if (!s) return;
  // symbols
  symbolSel.innerHTML = '';
  Object.keys(s.candles || {{}}).forEach(sym => {{
    const o = document.createElement('option');
    o.value = sym; o.textContent = sym;
    symbolSel.appendChild(o);
  }});
  if (s.default_symbol && s.candles[s.default_symbol]) symbolSel.value = s.default_symbol;

  const m = s.metrics || {{}};
  metricsEl.innerHTML = `
    <div><strong>${{s.name}}</strong></div>
    <div class="meta">${{s.note || ''}}</div>
    <div style="margin-top:6px">
      <span class="pill">状态: ${{s.status}}</span>
      <span class="pill">周期: ${{s.timeframe}}</span>
      ${{m.return_pct!=null?`<span class="pill">收益: ${{m.return_pct}}%</span>`:''}}
      ${{m.max_dd_pct!=null?`<span class="pill">最大回撤: ${{m.max_dd_pct}}%</span>`:''}}
      ${{m.trades!=null?`<span class="pill">成交: ${{m.trades}}</span>`:''}}
      ${{m.ending_equity!=null?`<span class="pill">终值: ${{Number(m.ending_equity).toFixed(2)}}</span>`:''}}
      ${{m.final_equity!=null?`<span class="pill">终值: ${{Number(m.final_equity).toFixed(2)}}</span>`:''}}
      ${{m.profit_factor!=null?`<span class="pill">PF: ${{Number(m.profit_factor).toFixed(3)}}</span>`:''}}
    </div>`;
  loadSymbol();
}}

function loadSymbol() {{
  const s = cur();
  const sym = symbolSel.value;
  const candles = (s.candles || {{}})[sym] || [];
  candleSeries.setData(candles.map(c => ({{
    time: c.time, open: c.open, high: c.high, low: c.low, close: c.close
  }})));

  // equity overlay (account level)
  const eq = (s.equity || []).filter(p => p.time != null);
  equitySeries.setData(eq.map(p => ({{ time: p.time, value: p.equity }})));
  setEquityVisible(showEquity);

  const trades = (s.trades || []).filter(t => t.symbol === sym);
  const markers = [];
  trades.forEach(t => {{
    const long = t.direction === 'long';
    markers.push({{
      time: t.entry_time,
      position: long ? 'belowBar' : 'aboveBar',
      color: long ? '#26a69a' : '#ef5350',
      shape: long ? 'arrowUp' : 'arrowDown',
      text: long ? '开多' : '开空',
    }});
    markers.push({{
      time: t.exit_time,
      position: long ? 'aboveBar' : 'belowBar',
      color: '#f0b90b',
      shape: 'circle',
      text: '平',
    }});
  }});
  markers.sort((a,b)=>a.time-b.time);
  candleSeries.setMarkers(markers);

  // trade list
  tradesEl.innerHTML = '';
  let wins = 0;
  trades.forEach(t => {{
    const pnl = Number(t.net_pnl);
    if (pnl > 0) wins++;
    const div = document.createElement('div');
    div.className = 'trade';
    div.innerHTML = `
      <div style="display:flex;justify-content:space-between">
        <strong>#${{t.id}} <span class="${{t.direction==='long'?'long':'short'}}">${{t.direction}}</span></strong>
        <span class="${{pnl>=0?'pos':'neg'}}">${{Number.isFinite(pnl)?pnl.toFixed(4):'—'}}</span>
      </div>
      <div class="meta">入 ${{t.entry_iso}}</div>
      <div class="meta">出 ${{t.exit_iso}} ${{t.exit_reason||''}}</div>`;
    div.onclick = () => {{
      document.querySelectorAll('.trade').forEach(x=>x.classList.remove('on'));
      div.classList.add('on');
      const pad = 48 * 3600;
      chart.timeScale().setVisibleRange({{ from: t.entry_time - pad, to: t.exit_time + pad }});
    }};
    tradesEl.appendChild(div);
  }});
  statsEl.textContent = `${{sym}} · K线 ${{candles.length}} 根 · 本币成交 ${{trades.length}} · 胜 ${{wins}} · 左轴权益 / 右轴价格`;
  chart.timeScale().fitContent();
}}

strategySel.onchange = loadStrategy;
symbolSel.onchange = loadSymbol;
document.getElementById('fit').onclick = () => chart && chart.timeScale().fitContent();
document.getElementById('toggleEq').onclick = () => setEquityVisible(!showEquity);

renderNoData();
if ((DATA.strategies||[]).length) loadStrategy();
else {{
  document.getElementById('chartBox').innerHTML = '<p style="padding:20px;color:#787b86">没有可绑定行情的策略数据包。</p>';
}}
</script>
</body>
</html>
"""


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    strategies = []
    for builder in (build_ten_u, build_low_vol):
        try:
            s = builder(root)
        except Exception as exc:
            print(f"builder failed: {builder.__name__}: {exc}")
            s = None
        if s:
            strategies.append(s)
            print(f"OK {s['id']}: symbols={list(s['candles'])} trades={len(s['trades'])} equity={len(s['equity'])}")

    chartable = {s["id"] for s in strategies}
    no_chart = build_no_data_list(root, chartable)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "strategies": strategies,
        "no_chart": no_chart,
        "note": "Equity is account-level; candles are selected symbol price.",
    }
    html = html_page(payload)
    out = root / "docs" / "multi_strategy_kline_equity_dashboard.html"
    out2 = root / "reports" / "prod" / "multi_strategy_kline_equity_dashboard.html"
    out.write_text(html, encoding="utf-8")
    out2.parent.mkdir(parents=True, exist_ok=True)
    out2.write_text(html, encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size // 1024} KB)")
    print(f"chartable={len(strategies)} no_chart={len(no_chart)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
