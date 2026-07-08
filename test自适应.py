"""测试自适应配置"""
from backtester import run_report
from pathlib import Path

import sys
sys.path.insert(0, '.')
from config自适应 import ADAPTIVE_CONFIG as config

print("=" * 60)
print("自适应配置回测 (Regime-Aware)")
print("=" * 60)
print(f"风险/笔: {config.risk_per_trade*100}%")
print(f"趋势止损: {config.stop_atr} ATR, 止盈: {config.take_profit_atr} ATR")
print(f"区间止损: {config.range_stop_atr} ATR, 止盈: {config.range_take_profit_atr} ATR")
print(f"冷却: {config.cooldown_bars} bars, 亏损冷却: {config.loss_cooldown_bars} bars")
print()

report = run_report(Path('data'), Path('reports/adaptive.json'), config)

print(f"{'窗口':>5} {'交易':>5} {'胜':>3} {'负':>3} {'胜率':>6} {'净PnL':>9} {'回报%':>8} {'回撤%':>8}")
print("-" * 55)
for days, result in report["windows"].items():
    if not result.get("available"):
        print(f"{days:>3}d  不可用")
        continue
    t = result['trades']
    w = result['wins']
    wr = result['win_rate'] * 100
    pnl = result['pnl']
    ret = result['return_pct']
    dd = result['max_drawdown_pct']
    print(f"{days:>3}d  {t:>5} {w:>3} {t-w:>3} {wr:>5.1f}% {pnl:>+9.4f} {ret:>+7.3f}% {dd:>7.2f}%")

print()
print("交易明细:")
for days, result in report["windows"].items():
    if result.get('trades_detail'):
        print(f"\n--- {days}d ---")
        for td in result['trades_detail']:
            emoji = '✅' if td['pnl'] > 0 else '❌'
            print(f"  {emoji} {td['symbol']} {td['direction']} {td['reason']} pnl={td['pnl']:+.4f} ({td['pnl_pct_equity']:+.1f}%)")

print()
print("=" * 60)
print("Regime策略映射:")
from config自适应 import REGIME_STRATEGY_MAP
for regime, strategies in REGIME_STRATEGY_MAP.items():
    print(f"  {regime:>10}: {', '.join(strategies)}")
