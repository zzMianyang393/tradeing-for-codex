# 组合策略常见失真风险与工程测试断言清单 (G16)

**文档状态**：仅新建  
**文档路径**：`docs/combo_strategy_bias_risk_review_2026-07-13.md`  
**基准约束**：  
- `approved_for_paper = []`  
- `safe_to_enable_trading = false`  
- **纪律红线**：严禁通过过度参数拟合或反向调权制造组合表面高收益，所有失真风险必须在工程测试中实现硬性阻断。

---

## 一、组合策略 8 大失真风险深度剖析

当我们将多个弱期望特征（Weak Features/Signals）组合成一个综合策略时，往往会遭遇一系列非线性叠加的统计学与工程学陷阱，导致回测曲线极其亮丽，但实盘/模拟盘表现迅速崩盘：

### 1. 多重检验与数据挖掘偏差 (Multiple Testing / Data Snooping)
- **风险原理**：当研究员尝试过多的特征组合、参数或分配权重时，即使每个特征本身是随机噪声，根据概率，最终也能筛选出一个“完美通过 365天 验证”的组合权重。这种高收益完全是数据挖掘噪音的产物。
- **失真表现**：IS 曲线极度平滑，但 OOS 净值直接横盘或崩盘。

### 2. 特征共线性 (Collinearity)
- **风险原理**：许多趋势或动量指标（如 Donchian 突破、均线交叉、MACD）本质上都是价格的一阶或二阶时滞线性组合，具有极强的正相关性。
- **失真表现**：共线性会导致组合在牛市行情中发生**同向信号严重共振**，变相放大了交易杠杆与多头头寸暴露；而在震荡市中则同时触发假突破，导致多次重复止损。

### 3. 单月贡献集中度偏差 (Concentration Bias)
- **风险原理**：组合策略的总收益被极少数极端宏观月度（例如 2024-11）所主导。在这些特殊月份，全市场单边暴涨，几乎所有多头特征都赚取了超额红利。
- **失真表现**：如果刨除该单月收益，策略其余 11 个月均处于亏损或横盘状态，但总期望值依然为正，掩盖了策略在常规市场环境下的真实无能。

### 4. OOS 结果反向泄漏与二次过拟合 (Backtesting Leakage / OOS Overfitting)
- **风险原理**：在回测结束后，研究员看到 OOS 表现不好，转头调整 IS 的特征权重或阈值，再次进行回测。这使得 OOS 空间退化为 IS 的一部分，造成了严重的“研究员前视偏差”。
- **失真表现**：OOS 的表现呈现“回测次数越多，OOS 曲线越漂亮，但实盘衰减越严重”的恶性特征。

### 5. 静态币种与幸存者偏差 (Survivorship Bias)
- **风险原理**：在组合层回测中，如果使用静态的“当前主流币种集合”进行回测，会忽略那些已经退市或流动性枯竭的币种。
- **失真表现**：回测中只包含了一直存活至今的强势币，强行拉高了历史轮动策略的整体收益。

### 6. 摩擦成本多重叠加 (Friction Overlap)
- **风险原理**：单策略通常只计算一腿或两腿费用。但在组合中，多个特征交织产生的多腿开仓、换月、期现对冲等动作，会导致实际交易腿数倍增，硬性成本大幅拉高。
- **失真表现**：忽略了多腿并发执行时的实际滑点和 taker 手续费损耗（两腿 $0.16\%$，四腿 $0.32\%$）。

### 7. 信号冲突与换手率倍增 (Turnover Amplification / Signal Whiplash)
- **风险原理**：当特征 A 投票做多，而特征 B 投票做空时，如果系统采用简易的方向求和，可能会频繁触发“多单平仓并反向开空”，导致持仓时间极短，换手率飙升。
- **失真表现**：手续费消耗极快，实际净平均单次收益（Net Expectancy per Trade）低于 $0.16\%$ 地板。

### 8. 误将风控过滤器当作 Alpha 信号 (Veto as Alpha)
- **风险原理**：某些特征（如低波动率收缩、 weekends no-trade）其物理逻辑是“通过拦截高危时段来减少亏损”，属于典型的过滤器。如果将其改写为方向性做空/做多信号参与组合投票，会扭曲其物理基础。
- **失真表现**：过滤器产生的方向性信号往往胜率极低，增加了不必要的交易频次和成本。

---

## 二、后续工程可测试规则与断言设计 (Code Assertions)

为了防止后续研究流于调参，在编写组合回测引擎（如 `combo_backtester.py`）或验证脚本时，**必须硬性实现以下断言（Assertions）和防御检测逻辑**：

### 1. 权重确定前视与二次拟合阻断
- **工程规则**：权重生成函数（Weight Generator）的参数传递必须严格隔离。
- **单元测试断言**：
  ```python
  # 验证权重生成器不接受任何含有 OOS 时间戳的数据
  def test_weight_generation_isolation(self):
      oos_data = get_market_data(start_date=OOS_START, end_date=OOS_END)
      with self.assertRaises(AssertionError):
          # 传入 OOS 数据进行权重计算必须触发断言错误
          generate_combo_weights(data=oos_data, mode="train_weights")
  ```

### 2. 特征共线性拦截 (Collinearity Veto)
- **工程规则**：在计算特征相关性矩阵时，任何强相关的特征对必须被剔除一个。
- **单元测试断言**：
  ```python
  # 相关性上限硬编码为 0.70
  def test_feature_collinearity_limit(self):
      corr_matrix = calculate_correlation_matrix(combo_features)
      # 排除对角线的 1.0 之后，最大相关性必须小于 0.70
      max_corr = get_max_non_diagonal_correlation(corr_matrix)
      assert max_corr < 0.70, f"Collinearity limit exceeded: {max_corr} >= 0.70"
  ```

### 3. 单月贡献集中度惩罚 (Concentration Penalty)
- **工程规则**：单月收益贡献占比超过限额时，对策略总夏普比率和期望值实施乘数惩罚。
- **单元测试断言**：
  ```python
  def test_concentration_limit(self):
      monthly_returns = get_monthly_returns(backtest_report)
      total_return = sum(monthly_returns)
      max_single_month_return = max(monthly_returns)
      # 单月贡献率上限 25%
      concentration_ratio = max_single_month_return / total_return if total_return > 0 else 0.0
      assert concentration_ratio <= 0.25, f"Concentration ratio too high: {concentration_ratio} > 0.25"
  ```

### 4. 动态币种池点对点时间对齐 (Point-in-Time Universe Selection)
- **工程规则**：禁止在回测中使用静态代币列表，币种池必须是回测时间轴上“前一日流动性排序后”的动态选择。
- **单元测试断言**：
  ```python
  def test_point_in_time_universe(self):
      # 验证在历史特定步，可交易的币种必须完全等于该历史时刻实际处于活跃状态的币种
      for step in test_steps:
          active_pool = get_active_universe_at_timestamp(step.timestamp)
          # 禁止交易已下架或未来才上架的币种
          assert "FUTURE_COIN" not in active_pool
  ```

### 5. 信号 whiplash 与最低交易期望拦截 (Net Expectancy Floor)
- **工程规则**：如果组合总换手率过高，导致单次交易扣费后的净均值无法越过 $0.16\%$ 地板，必须判定策略无效。
- **单元测试断言**：
  ```python
  def test_net_expectancy_floor(self):
      pnl_stats = calculate_trade_statistics(backtest_report)
      # 单次往返扣成本后的净 PnL 均值必须 >= 0.16%
      assert pnl_stats["net_expectancy_pct"] >= 0.16, (
          f"Turnover too high, net expectancy per trade is too thin: "
          f"{pnl_stats['net_expectancy_pct']}% < 0.16%"
      )
  ```

### 6. 过滤器功能属性断言 (Veto-Only Assertion)
- **工程规则**：凡是标注为 `risk_filter_candidate` 的特征，只允许用作逻辑 `AND` 中的 Veto 拦截（即与方向信号相乘为 0），其本身的值必须不带正负多空方向。
- **单元测试断言**：
  ```python
  def test_filter_candidate_is_veto_only(self):
      for feature in combo_features:
          if feature.role == "risk_filter_candidate":
              # 过滤器的值只允许是 [0, 1]（表示是否允许交易），禁止产生 [-1, 1] 的方向偏好
              assert set(feature.values).issubset({0, 1}), (
                  f"Filter {feature.id} contains directional values: {set(feature.values)}"
              )
  ```
