"""Build TradingView-style candlestick HTML with trade markers (10U focus)."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path


SYMBOL_FILES = {
    "RAVE-USDT-SWAP": "RAVE_1h_full.csv",
    "LAB-USDT-SWAP": "LAB_1h_full.csv",
    "ETH-USDT-SWAP": "ETH_1h_full.csv",
}


def parse_ts(value: str) -> int:
    """Return unix seconds UTC."""
    text = value.replace("Z", "+00:00")
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def load_candles(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                ts_ms = int(row["timestamp_ms"])
                rows.append(
                    {
                        "time": ts_ms // 1000,
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row.get("volume_quote") or row.get("volume_base") or 0),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
    rows.sort(key=lambda x: x["time"])
    return rows


def load_ten_u_trades(root: Path) -> list[dict]:
    path = root / "reports/ten_u_event_trend_informal_full_history_v2.json"
    if not path.exists():
        return []
    trades = json.loads(path.read_text(encoding="utf-8")).get("trades") or []
    out = []
    for i, t in enumerate(trades):
        try:
            entry = parse_ts(str(t["entry"]))
            exit_ = parse_ts(str(t["exit"]))
        except Exception:
            continue
        out.append(
            {
                "id": i + 1,
                "symbol": t.get("symbol"),
                "direction": t.get("direction"),
                "entry_time": entry,
                "exit_time": exit_,
                "entry_iso": str(t.get("entry")),
                "exit_iso": str(t.get("exit")),
                "exit_reason": t.get("exit_reason"),
                "net_pnl": t.get("net_pnl"),
                "equity_after": t.get("equity_after"),
            }
        )
    return out


def load_sealed_trades(root: Path) -> list[dict]:
    path = root / "reports/ten_u_event_trend_screen_v2.json"
    if not path.exists():
        return []
    acc = json.loads(path.read_text(encoding="utf-8")).get("account") or {}
    details = acc.get("trades_detail") or []
    out = []
    for i, t in enumerate(details):
        try:
            entry = int(t["entry_ts"]) // 1000 if t.get("entry_ts") else None
            exit_ = int(t["exit_ts"]) // 1000 if t.get("exit_ts") else None
        except Exception:
            continue
        if entry is None or exit_ is None:
            continue
        out.append(
            {
                "id": f"S{i+1}",
                "symbol": t.get("symbol"),
                "direction": t.get("direction"),
                "entry_time": entry,
                "exit_time": exit_,
                "entry_iso": datetime.fromtimestamp(entry, tz=timezone.utc).isoformat(),
                "exit_iso": datetime.fromtimestamp(exit_, tz=timezone.utc).isoformat(),
                "exit_reason": t.get("exit_reason"),
                "net_pnl": t.get("net_pnl"),
                "equity_after": t.get("equity_after"),
                "entry_price": t.get("entry_price"),
                "exit_price": t.get("exit_price"),
            }
        )
    return out


def build_html(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>10U 策略 K 线回放（TradingView 风格）</title>
  <script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
  <style>
    :root {{
      --bg: #0b0e11;
      --panel: #131722;
      --border: #1e222d;
      --text: #d1d4dc;
      --muted: #787b86;
      --green: #26a69a;
      --red: #ef5350;
      --blue: #2962ff;
      --accent: #f0b90b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg); color: var(--text);
    }}
    header {{
      padding: 12px 16px; border-bottom: 1px solid var(--border);
      display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
      background: var(--panel);
    }}
    header h1 {{ font-size: 16px; margin: 0; font-weight: 600; }}
    header .sub {{ color: var(--muted); font-size: 12px; width: 100%; }}
    .toolbar {{
      display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
      padding: 10px 16px; border-bottom: 1px solid var(--border); background: #0f1318;
    }}
    label {{ font-size: 12px; color: var(--muted); }}
    select, button {{
      background: #1c212b; color: var(--text); border: 1px solid var(--border);
      border-radius: 6px; padding: 6px 10px; font-size: 13px;
    }}
    button {{ cursor: pointer; }}
    button:hover {{ border-color: var(--blue); }}
    button.active {{ background: #1a2a4a; border-color: var(--blue); color: #8ab4ff; }}
    .layout {{ display: grid; grid-template-columns: 1fr 320px; height: calc(100vh - 110px); }}
    @media (max-width: 960px) {{
      .layout {{ grid-template-columns: 1fr; height: auto; }}
      #tradeList {{ max-height: 280px; }}
    }}
    #chartWrap {{ display: flex; flex-direction: column; min-height: 520px; border-right: 1px solid var(--border); }}
    #candleChart {{ flex: 1; min-height: 380px; }}
    #volumeChart {{ height: 120px; border-top: 1px solid var(--border); }}
    #tradeList {{
      overflow: auto; background: var(--panel); padding: 0;
    }}
    .trade {{
      padding: 10px 12px; border-bottom: 1px solid var(--border); cursor: pointer;
      font-size: 12px; line-height: 1.45;
    }}
    .trade:hover, .trade.selected {{ background: #1a2030; }}
    .trade .row1 {{ display: flex; justify-content: space-between; gap: 8px; }}
    .long {{ color: var(--green); }}
    .short {{ color: var(--red); }}
    .pnl-pos {{ color: var(--green); }}
    .pnl-neg {{ color: var(--red); }}
    .meta {{ color: var(--muted); font-size: 11px; }}
    .legend {{
      padding: 6px 16px; font-size: 11px; color: var(--muted);
      border-bottom: 1px solid var(--border);
    }}
    .legend span {{ margin-right: 12px; }}
    .dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:4px; }}
  </style>
</head>
<body>
  <header>
    <h1>10U Event Trend — K 线交易回放</h1>
    <div class="sub">TradingView 风格蜡烛图（1H）· 箭头=入场 / 叉=出场 · 数据来自本地 OKX 1H CSV + 非正式全量成交</div>
  </header>
  <div class="toolbar">
    <label>币种
      <select id="symbol"></select>
    </label>
    <label>成交集
      <select id="dataset">
        <option value="informal">全量非正式（23 笔）</option>
        <option value="sealed">密封窗（3 笔）</option>
        <option value="all">合并显示</option>
      </select>
    </label>
    <button type="button" id="btnAll">显示该币全部成交</button>
    <button type="button" id="btnFit">自适应全图</button>
    <span class="meta" id="stats"></span>
  </div>
  <div class="legend">
    <span><i class="dot" style="background:#26a69a"></i>阳线</span>
    <span><i class="dot" style="background:#ef5350"></i>阴线</span>
    <span>▲ 多头开仓 · ▼ 空头开仓 · ✕ 平仓</span>
    <span>点击右侧成交 → 自动缩放到该笔区间</span>
  </div>
  <div class="layout">
    <div id="chartWrap">
      <div id="candleChart"></div>
      <div id="volumeChart"></div>
    </div>
    <div id="tradeList"></div>
  </div>

<script>
const DATA = {data};

const symbolSel = document.getElementById('symbol');
const datasetSel = document.getElementById('dataset');
const tradeList = document.getElementById('tradeList');
const statsEl = document.getElementById('stats');

Object.keys(DATA.candles).forEach(sym => {{
  const o = document.createElement('option');
  o.value = sym; o.textContent = sym;
  symbolSel.appendChild(o);
}});

const candleEl = document.getElementById('candleChart');
const volumeEl = document.getElementById('volumeChart');

const chart = LightweightCharts.createChart(candleEl, {{
  layout: {{
    background: {{ type: 'solid', color: '#0b0e11' }},
    textColor: '#d1d4dc',
  }},
  grid: {{
    vertLines: {{ color: '#1e222d' }},
    horzLines: {{ color: '#1e222d' }},
  }},
  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  rightPriceScale: {{ borderColor: '#1e222d' }},
  timeScale: {{ borderColor: '#1e222d', timeVisible: true, secondsVisible: false }},
}});

const candleSeries = chart.addCandlestickSeries({{
  upColor: '#26a69a',
  downColor: '#ef5350',
  borderUpColor: '#26a69a',
  borderDownColor: '#ef5350',
  wickUpColor: '#26a69a',
  wickDownColor: '#ef5350',
}});

const volumeChart = LightweightCharts.createChart(volumeEl, {{
  layout: {{
    background: {{ type: 'solid', color: '#0b0e11' }},
    textColor: '#787b86',
  }},
  grid: {{
    vertLines: {{ color: '#1e222d' }},
    horzLines: {{ color: '#1e222d' }},
  }},
  rightPriceScale: {{ borderColor: '#1e222d' }},
  timeScale: {{ borderColor: '#1e222d', visible: false }},
}});

const volumeSeries = volumeChart.addHistogramSeries({{
  priceFormat: {{ type: 'volume' }},
  priceScaleId: '',
}});
volumeChart.priceScale('').applyOptions({{ scaleMargins: {{ top: 0.1, bottom: 0 }} }});

// sync time scales
chart.timeScale().subscribeVisibleLogicalRangeChange(range => {{
  if (range) volumeChart.timeScale().setVisibleLogicalRange(range);
}});
volumeChart.timeScale().subscribeVisibleLogicalRangeChange(range => {{
  if (range) chart.timeScale().setVisibleLogicalRange(range);
}});

function resize() {{
  const w = candleEl.clientWidth;
  const h = Math.max(360, candleEl.clientHeight || 420);
  chart.applyOptions({{ width: w, height: h }});
  volumeChart.applyOptions({{ width: w, height: 120 }});
}}
window.addEventListener('resize', resize);

function tradesFor(symbol, dataset) {{
  let list = [];
  if (dataset === 'informal' || dataset === 'all') list = list.concat(DATA.trades_informal || []);
  if (dataset === 'sealed' || dataset === 'all') list = list.concat(DATA.trades_sealed || []);
  return list.filter(t => t.symbol === symbol);
}}

function renderList(symbol) {{
  const trades = tradesFor(symbol, datasetSel.value);
  tradeList.innerHTML = '';
  if (!trades.length) {{
    tradeList.innerHTML = '<div class="trade meta">该币在此成交集中无交易</div>';
    statsEl.textContent = symbol + ' · 0 笔';
    return trades;
  }}
  let wins = 0;
  trades.forEach((t, idx) => {{
    if (Number(t.net_pnl) > 0) wins++;
    const div = document.createElement('div');
    div.className = 'trade';
    div.dataset.idx = String(idx);
    const pnlCls = Number(t.net_pnl) >= 0 ? 'pnl-pos' : 'pnl-neg';
    const dirCls = t.direction === 'long' ? 'long' : 'short';
    div.innerHTML = `
      <div class="row1">
        <strong>#${{t.id}} <span class="${{dirCls}}">${{t.direction}}</span></strong>
        <span class="${{pnlCls}}">${{Number(t.net_pnl).toFixed(4)}} U</span>
      </div>
      <div class="meta">入 ${{t.entry_iso}}</div>
      <div class="meta">出 ${{t.exit_iso}} · ${{t.exit_reason || ''}}</div>
      <div class="meta">权益→ ${{t.equity_after != null ? Number(t.equity_after).toFixed(2) : '—'}}</div>`;
    div.addEventListener('click', () => {{
      document.querySelectorAll('.trade').forEach(el => el.classList.remove('selected'));
      div.classList.add('selected');
      focusTrade(t);
    }});
    tradeList.appendChild(div);
  }});
  statsEl.textContent = `${{symbol}} · ${{trades.length}} 笔 · 胜 ${{wins}}`;
  return trades;
}}

function setMarkers(trades) {{
  const markers = [];
  trades.forEach(t => {{
    const long = t.direction === 'long';
    markers.push({{
      time: t.entry_time,
      position: long ? 'belowBar' : 'aboveBar',
      color: long ? '#26a69a' : '#ef5350',
      shape: long ? 'arrowUp' : 'arrowDown',
      text: long ? '多开' : '空开',
    }});
    markers.push({{
      time: t.exit_time,
      position: long ? 'aboveBar' : 'belowBar',
      color: '#f0b90b',
      shape: 'circle',
      text: '平',
    }});
  }});
  markers.sort((a, b) => a.time - b.time);
  candleSeries.setMarkers(markers);
}}

function focusTrade(t) {{
  const pad = 36 * 3600; // 36 hours padding in seconds for 1H bars
  const from = t.entry_time - pad;
  const to = t.exit_time + pad;
  chart.timeScale().setVisibleRange({{ from, to }});
}}

function loadSymbol() {{
  const symbol = symbolSel.value;
  const candles = DATA.candles[symbol] || [];
  candleSeries.setData(candles.map(c => ({{
    time: c.time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  }})));
  volumeSeries.setData(candles.map(c => ({{
    time: c.time,
    value: c.volume,
    color: c.close >= c.open ? 'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)',
  }})));
  const trades = renderList(symbol);
  setMarkers(trades);
  chart.timeScale().fitContent();
  resize();
}}

document.getElementById('btnFit').onclick = () => chart.timeScale().fitContent();
document.getElementById('btnAll').onclick = () => {{
  const symbol = symbolSel.value;
  const trades = tradesFor(symbol, datasetSel.value);
  setMarkers(trades);
  chart.timeScale().fitContent();
}};
symbolSel.onchange = loadSymbol;
datasetSel.onchange = loadSymbol;

// default: pick first symbol that has trades
const informal = DATA.trades_informal || [];
const prefer = ['RAVE-USDT-SWAP', 'LAB-USDT-SWAP', 'ETH-USDT-SWAP'];
for (const s of prefer) {{
  if (informal.some(t => t.symbol === s)) {{ symbolSel.value = s; break; }}
}}
loadSymbol();
</script>
</body>
</html>
"""


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data" / "event_trend_v1"
    candles: dict[str, list] = {}
    for symbol, filename in SYMBOL_FILES.items():
        path = data_dir / filename
        if path.exists():
            candles[symbol] = load_candles(path)
            print(f"loaded {symbol}: {len(candles[symbol])} bars")
        else:
            print(f"missing {path}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "timeframe": "1H",
        "candles": candles,
        "trades_informal": load_ten_u_trades(root),
        "trades_sealed": load_sealed_trades(root),
        "note": "10U informal full-history trades + sealed screen trades on OKX 1H candles",
    }
    html = build_html(payload)
    out1 = root / "docs" / "ten_u_kline_trade_dashboard.html"
    out2 = root / "reports" / "prod" / "ten_u_kline_trade_dashboard.html"
    out1.parent.mkdir(parents=True, exist_ok=True)
    out2.parent.mkdir(parents=True, exist_ok=True)
    out1.write_text(html, encoding="utf-8")
    out2.write_text(html, encoding="utf-8")
    print(f"Wrote {out1} ({out1.stat().st_size // 1024} KB)")
    print(f"Wrote {out2}")
    print(
        f"trades informal={len(payload['trades_informal'])} sealed={len(payload['trades_sealed'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
