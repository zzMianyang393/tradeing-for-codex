#!/usr/bin/env python3.11
"""
10U → 500U 滚仓系统 - 最终启动脚本

用法:
  python3.11 start_trading.py --mode backtest    # 回测验证
  python3.11 start_trading.py --mode dry-run     # 模拟盘
  python3.11 start_trading.py --mode live        # 实盘 (需要API Key)
"""

import argparse
import json
import sys
from pathlib import Path
from dataclasses import replace, asdict

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import BacktestConfig, SymbolRisk
from market import load_market


def get_optimized_config() -> BacktestConfig:
    """返回优化后的配置 - 只保留盈利策略"""
    return BacktestConfig(
        start_equity=10.0,
        timeframe_minutes=15,
        taker_fee=0.00005,
        slippage=0.0003,
        
        # 核心风控
        risk_per_trade=0.20,
        max_margin_fraction=0.70,
        max_total_margin_fraction=0.60,
        max_positions=3,
        active_symbol_limit=8,
        
        # 防御模式
        defensive_equity_fraction=0.60,
        defensive_risk_multiplier=0.50,
        defensive_margin_fraction=0.30,
        
        # 盈利保护
        profit_lock_equity_fraction=1.30,
        profit_lock_risk_multiplier=0.65,
        profit_lock_margin_fraction=0.45,
        
        # 波动率
        volatility_target_atr_pct=0.025,
        volatility_risk_floor=0.60,
        volatility_risk_power=0.80,
        
        # 趋势策略 (唯一盈利的策略)
        stop_atr=2.5,
        take_profit_atr=3.0,
        trailing_atr=2.2,
        max_hold_bars=10,
        
        # 区间策略 (禁用 - 亏损)
        range_stop_atr=2.0,
        range_take_profit_atr=0.8,
        range_trailing_atr=1.5,
        range_max_hold_bars=4,
        
        # 禁用所有亏损策略
        enable_attack_module=False,
        enable_micro_momentum_module=False,
        enable_funding_module=False,
        enable_open_interest_module=False,
        enable_trade_flow_module=False,
        enable_order_book_module=False,
        enable_continuation_module=False,
        
        # 信号门槛
        min_score=2.0,
        
        # 冷却 (极短)
        cooldown_bars=8,
        loss_cooldown_bars=24,
        time_exit_loss_cooldown_bars=48,
        early_failure_bars=0,
        early_failure_min_mfe_pct=0,
        early_failure_max_mae_pct=0,
        early_failure_reasons=(),
        
        # 方向暂停 (宽松)
        direction_loss_pause_bars=96,
        direction_loss_pause_pct=15.0,
        
        # 反转保护 (宽松)
        short_rebound_lookback_bars=96,
        short_rebound_block_pct=0.02,
        long_flush_lookback_bars=96,
        long_flush_block_pct=-0.05,
        
        # 区间参数
        range_long_rsi_min=25.0,
        range_long_rsi_max=38.0,
        range_short_rsi_min=62.0,
        range_short_rsi_max=75.0,
        
        # Transition
        transition_long_enabled=True,
        transition_short_enabled=True,
        
        # 自适应趋势
        enable_adaptive_profiles=True,
        adaptive_trend_min_score=3.5,
        adaptive_trend_risk_per_trade=0.12,
        adaptive_trend_stop_atr=2.2,
        adaptive_trend_take_profit_atr=2.0,
        adaptive_trend_trailing_atr=2.0,
        adaptive_trend_max_hold_bars=8,
        adaptive_trend_allowed_regimes=('downtrend', 'uptrend', 'transition'),
        
        # 允许所有Regime
        enabled_regimes=('uptrend', 'downtrend', 'transition', 'range'),
        
        # Symbol选择器
        selector_lookback_bars=96*7,
        selector_momentum_weight=50.0,
        selector_volatility_weight=200.0,
        selector_trend_weight=0.12,
        selector_noise_penalty=5.0,
        selector_min_avg_quote=150_000.0,
        
        # 杠杆
        leverage_caps={
            "BTC-USDT-SWAP": SymbolRisk(max_leverage=50, min_notional=1.0),
            "ETH-USDT-SWAP": SymbolRisk(max_leverage=50, min_notional=1.0),
            "SOL-USDT-SWAP": SymbolRisk(max_leverage=40, min_notional=1.0),
            "BNB-USDT-SWAP": SymbolRisk(max_leverage=40, min_notional=1.0),
            "XRP-USDT-SWAP": SymbolRisk(max_leverage=30, min_notional=1.0),
            "DOGE-USDT-SWAP": SymbolRisk(max_leverage=30, min_notional=1.0),
            "ADA-USDT-SWAP": SymbolRisk(max_leverage=30, min_notional=1.0),
            "AVAX-USDT-SWAP": SymbolRisk(max_leverage=30, min_notional=1.0),
            "LINK-USDT-SWAP": SymbolRisk(max_leverage=25, min_notional=1.0),
            "NEAR-USDT-SWAP": SymbolRisk(max_leverage=25, min_notional=1.0),
            "SUI-USDT-SWAP": SymbolRisk(max_leverage=25, min_notional=1.0),
            "ARB-USDT-SWAP": SymbolRisk(max_leverage=25, min_notional=1.0),
            "OP-USDT-SWAP": SymbolRisk(max_leverage=25, min_notional=1.0),
        },
        
        # RiskManager (宽松)
        rm_enabled=True,
        rm_max_single_position_pct=0.85,
        rm_max_total_position_pct=0.90,
        rm_max_daily_loss_pct=999.0,  # 禁用累计日亏损检查
        rm_max_weekly_loss_pct=999.0, # 禁用累计周亏损检查
        rm_consecutive_loss_pause=8,
        rm_consecutive_loss_pause_bars=96,
        rm_volatility_halt_threshold=0.15,
        rm_min_liquidation_distance_pct=0.03,
        
        # 验证窗口
        windows_days=(365, 180, 90, 60, 30, 14, 7),
        min_bars=200,
    )


def run_backtest(config: BacktestConfig, days: int = 30):
    """运行回测"""
    from backtester import Backtester
    
    print(f"\n{'='*60}")
    print(f"回测: {days}天")
    print(f"{'='*60}\n")
    
    # 加载数据
    market = load_market(
        Path('data'), 
        config.timeframe_minutes,
        include_funding=config.enable_funding_module,
        include_open_interest=config.enable_open_interest_module,
        include_trade_flow=config.enable_trade_flow_module,
        include_order_book=config.enable_order_book_module,
    )
    
    print(f"加载了 {len(market)} 个币种")
    
    # 运行回测
    tester = Backtester(config)
    result = tester.run(market, days=days)
    
    if not result.get('available'):
        print(f"回测不可用: {result.get('reason', 'unknown')}")
        return result
    
    # 输出结果
    print(f"\n{'='*60}")
    print(f"回测结果")
    print(f"{'='*60}")
    print(f"起始资金:  {result['start_equity']:.2f}U")
    print(f"结束资金:  {result['end_equity']:.2f}U")
    print(f"盈亏:      {result['pnl']:+.4f}U")
    print(f"收益率:    {result['return_pct']:+.2f}%")
    print(f"交易次数:  {result['trades']}")
    print(f"胜率:      {result['win_rate']*100:.1f}%")
    print(f"最大回撤:  {result['max_drawdown_pct']:.2f}%")
    
    # 策略分解
    print(f"\n{'='*60}")
    print(f"策略分解")
    print(f"{'='*60}")
    for reason, data in sorted(result.get('by_reason', {}).items(), 
                                key=lambda x: x[1].get('pnl', 0), reverse=True):
        status = "✅" if data.get('pnl', 0) > 0 else "❌"
        print(f"{status} {reason:30s} {data['trades']:>3}笔 {data['win_rate']*100:>5.1f}% WR {data['pnl']:>+8.4f}U")
    
    # 保存报告
    report_path = Path('reports') / f'backtest_{days}d.json'
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n报告已保存: {report_path}")
    
    return result


def run_dry_run(config: BacktestConfig):
    """运行模拟盘"""
    from runner import TradingRunner
    from exchange import DryRunExchange
    from risk_manager import RiskManager
    from state_db import StateDB
    from executor import Executor
    
    print(f"\n{'='*60}")
    print(f"模拟盘模式")
    print(f"{'='*60}\n")
    
    # 创建组件
    db_path = Path('reports') / 'dry_run_state.db'
    exchange = DryRunExchange(equity=10.0)
    risk_manager = RiskManager(config)
    db = StateDB(db_path)
    executor = Executor(exchange, risk_manager, db, config, dry_run=True)
    
    # 创建Runner
    runner = TradingRunner(
        config=config,
        executor=executor,
        state_db=db,
        exchange=exchange,
        dry_run=True,
        data_dir=Path('data'),
    )
    
    # 加载数据
    market = runner.load_market_data()
    if not market:
        print("无法加载市场数据")
        return
    
    print(f"加载了 {len(market)} 个币种")
    
    # 运行一个周期
    report = runner.run_once()
    
    print(f"\n{'='*60}")
    print(f"模拟盘结果")
    print(f"{'='*60}")
    print(f"权益:       {report.equity:.2f}U")
    print(f"生成信号:   {report.signals_generated}")
    print(f"执行订单:   {report.executed_orders}")
    print(f"拒绝订单:   {report.orders_rejected}")
    print(f"平仓数量:   {report.closed_positions}")
    print(f"持仓数量:   {report.open_positions}")
    
    db.close()
    return report


def main():
    parser = argparse.ArgumentParser(description='10U → 500U 滚仓系统')
    parser.add_argument('--mode', choices=['backtest', 'dry-run', 'live'], 
                       default='backtest', help='运行模式')
    parser.add_argument('--days', type=int, default=30, help='回测天数')
    parser.add_argument('--equity', type=float, default=10.0, help='起始资金')
    
    args = parser.parse_args()
    
    # 获取配置
    config = get_optimized_config()
    config = replace(config, start_equity=args.equity)
    
    print(f"\n{'='*60}")
    print(f"10U → 500U 滚仓系统")
    print(f"{'='*60}")
    print(f"模式: {args.mode}")
    print(f"起始资金: {args.equity}U")
    print(f"{'='*60}\n")
    
    if args.mode == 'backtest':
        run_backtest(config, args.days)
    elif args.mode == 'dry-run':
        run_dry_run(config)
    elif args.mode == 'live':
        print("实盘模式需要配置API Key")
        print("请设置环境变量: OKX_API_KEY, OKX_SECRET, OKX_PASSPHRASE")
        print("或使用: python3.11 cli_runner.py --api-key XXX --secret XXX --passphrase XXX loop")


if __name__ == '__main__':
    main()
