"""
10U → 500U 滚仓执行计划

目标：30天内通过复利滚仓从10U增长到500U
策略：多策略并行 + 高杠杆 + 严格风控 + 阶段性降杠杆

核心数学：
- 50x in 30 days = 13.7% daily compound
- 15min bars → 96 bars/day
- 需要每笔平均回报 ≥ 2% 才能维持节奏
- 关键：赢的时候多赚，亏的时候少亏

执行节奏：
- 每15分钟扫描一次信号
- 最多3个持仓同时
- 快进快出(平均持仓1-4小时)
- 盈利后自动加仓(复利)
"""

import json
from pathlib import Path
from dataclasses import asdict, replace
from backtester import Backtester, run_report
from config import BacktestConfig
from market import load_market
from config_aggressive import (
    AGGRESSIVE_CONFIG, PHASE2_CONFIG, PHASE3_CONFIG,
    get_config_for_equity,
)


def run_backtest_phases(data_dir: str = "data") -> dict:
    """分阶段回测，验证滚仓可行性"""
    results = {}
    
    # Phase 1: 10U → 50U (aggressive)
    print("=" * 60)
    print("PHASE 1: 10U → 50U (激进模式, 10天)")
    print("=" * 60)
    r1 = run_report(
        Path(data_dir), 
        Path("reports/phase1_aggressive.json"),
        AGGRESSIVE_CONFIG
    )
    results["phase1"] = _summarize(r1, "10U → 50U")
    
    # Phase 2: 50U → 200U (moderate)
    print("\n" + "=" * 60)
    print("PHASE 2: 50U → 200U (适中模式, 10天)")
    print("=" * 60)
    r2 = run_report(
        Path(data_dir),
        Path("reports/phase2_moderate.json"),
        PHASE2_CONFIG
    )
    results["phase2"] = _summarize(r2, "50U → 200U")
    
    # Phase 3: 200U → 500U (conservative)
    print("\n" + "=" * 60)
    print("PHASE 3: 200U → 500U (稳健模式, 10天)")
    print("=" * 60)
    r3 = run_report(
        Path(data_dir),
        Path("reports/phase3_conservative.json"),
        PHASE3_CONFIG
    )
    results["phase3"] = _summarize(r3, "200U → 500U")
    
    # 汇总
    print("\n" + "=" * 60)
    print("汇总")
    print("=" * 60)
    for phase, data in results.items():
        print(f"{data['name']}: 起始{data['start']:.1f}U → 结束{data['end']:.4f}U "
              f"(回报{data['return_pct']:.2f}%, 胜率{data['win_rate']:.1f}%, "
              f"最大回撤{data['max_dd']:.1f}%)")
    
    return results


def _summarize(report: dict, name: str) -> dict:
    """从回测报告中提取关键指标"""
    windows = report.get("windows", {})
    # 取最短可用窗口(最接近实际交易)
    best_window = None
    for days in [7, 14, 30, 60, 90, 180, 365]:
        w = windows.get(str(days))
        if w and w.get("available"):
            best_window = w
            break
    
    if not best_window:
        return {"name": name, "start": 0, "end": 0, "return_pct": 0, 
                "win_rate": 0, "max_dd": 0, "trades": 0}
    
    return {
        "name": name,
        "start": best_window.get("start_equity", 0),
        "end": best_window.get("end_equity", 0),
        "pnl": best_window.get("pnl", 0),
        "return_pct": best_window.get("return_pct", 0),
        "win_rate": best_window.get("win_rate", 0) * 100,
        "max_dd": best_window.get("max_drawdown_pct", 0),
        "trades": best_window.get("trades", 0),
        "target_pass": best_window.get("target_pass", False),
    }


def daily_plan() -> str:
    """输出30天每日执行计划"""
    plan = []
    plan.append("=" * 70)
    plan.append("10U → 500U 滚仓执行计划 (30天)")
    plan.append("=" * 70)
    plan.append("")
    
    # Phase 1: Day 1-10
    plan.append("【Phase 1: Day 1-10】激进模式 (10U → 50U)")
    plan.append("-" * 50)
    plan.append("目标: 5x 回报 = 日均 17.5% 复利")
    plan.append("杠杆: 30-50x (主流币)")
    plan.append("单笔风险: 35% 本金")
    plan.append("最大持仓: 3个")
    plan.append("策略: 8个模块全开")
    plan.append("止损: ATR 1.2-2.0x (快速止损)")
    plan.append("止盈: ATR 1.5-2.0x (让利润跑)")
    plan.append("移动止损: 开仓后1.0-1.5x ATR 跟随")
    plan.append("冷却: 亏损后12小时暂停")
    plan.append("")
    plan.append("关键规则:")
    plan.append("  ✓ 每15分钟扫描一次信号")
    plan.append("  ✓ 盈利后下一笔自动加仓(复利)")
    plan.append("  ✓ 亏损后减仓(保护本金)")
    plan.append("  ✓ 单日亏损>25% 全天停止")
    plan.append("  ✓ 连亏4次 暂停12小时")
    plan.append("")
    
    # Phase 2: Day 11-20
    plan.append("【Phase 2: Day 11-20】适中模式 (50U → 200U)")
    plan.append("-" * 50)
    plan.append("目标: 4x 回报 = 日均 15% 复利")
    plan.append("杠杆: 25-40x")
    plan.append("单笔风险: 28% 本金")
    plan.append("最大持仓: 4个")
    plan.append("止损: ATR 1.5-2.0x")
    plan.append("止盈: ATR 1.8-2.2x")
    plan.append("冷却: 亏损后16小时暂停")
    plan.append("")
    plan.append("关键规则:")
    plan.append("  ✓ 提高信号门槛(只做高质量)")
    plan.append("  ✓ 更保守的仓位管理")
    plan.append("  ✓ 连亏3次暂停16小时")
    plan.append("  ✓ 单日亏损>20% 停止")
    plan.append("")
    
    # Phase 3: Day 21-30
    plan.append("【Phase 3: Day 21-30】稳健模式 (200U → 500U)")
    plan.append("-" * 50)
    plan.append("目标: 2.5x 回报 = 日均 9.6% 复利")
    plan.append("杠杆: 20-30x")
    plan.append("单笔风险: 22% 本金")
    plan.append("最大持仓: 3个")
    plan.append("止损: ATR 1.8-2.5x")
    plan.append("止盈: ATR 2.0-2.5x")
    plan.append("冷却: 亏损后24小时暂停")
    plan.append("")
    plan.append("关键规则:")
    plan.append("  ✓ 最高门槛(只做最佳信号)")
    plan.append("  ✓ 保护已有利润")
    plan.append("  ✓ 连亏3次暂停24小时")
    plan.append("  ✓ 单日亏损>15% 停止")
    plan.append("")
    
    # Risk Management
    plan.append("【风控总则】")
    plan.append("-" * 50)
    plan.append("1. 每笔亏损不超过当时本金的15%")
    plan.append("2. 日亏损不超过当时本金的25%")
    plan.append("3. 周亏损不超过当时本金的40%")
    plan.append("4. 总回撤超过50% 自动降级到保守模式")
    plan.append("5. 每天结束记录余额，对比目标进度")
    plan.append("6. 连续3天亏损 停止交易，重新分析")
    plan.append("7. 永远不要加仓亏损的头寸")
    plan.append("8. 盈利时让利润跑(移动止损)")
    plan.append("9. 亏损时快速承认(硬止损)")
    plan.append("10. 不要追涨杀跌")
    plan.append("")
    
    # Daily Tracking
    plan.append("【每日追踪表】")
    plan.append("-" * 50)
    plan.append(f"{'Day':>4} {'Start':>8} {'End':>8} {'PnL':>8} {'Trades':>6} {'WR':>6} {'Status'}")
    plan.append("-" * 50)
    for day in range(1, 31):
        phase = "激进" if day <= 10 else ("适中" if day <= 20 else "稳健")
        plan.append(f"{day:>4} {'---':>8} {'---':>8} {'---':>8} {'---':>6} {'---':>6} {phase}")
    plan.append("")
    
    # Milestone Targets
    plan.append("【里程碑目标】")
    plan.append("-" * 50)
    milestones = [
        (1, 13.7, "11.4U"),
        (3, 49.3, "14.9U"),
        (5, 100.5, "20.1U"),
        (7, 166.0, "26.6U"),
        (10, 298.0, "39.8U"),
        (15, 1000.0, "110U"),
        (20, 3360.0, "336U"),
        (25, 11300.0, "1130U"),
        (30, 500.0, "500U"),
    ]
    for day, _, target in milestones:
        if day <= 30:
            plan.append(f"  Day {day:>2}: 目标 {target}")
    plan.append("")
    plan.append("注: 以上是理想复利曲线，实际会有波动")
    plan.append("    关键是保持正期望值的交易系统运转")
    
    return "\n".join(plan)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "plan":
        print(daily_plan())
    elif len(sys.argv) > 1 and sys.argv[1] == "backtest":
        run_backtest_phases(sys.argv[2] if len(sys.argv) > 2 else "data")
    else:
        print("Usage:")
        print("  python execute_plan.py plan       - 显示30天执行计划")
        print("  python execute_plan.py backtest   - 运行分阶段回测")
