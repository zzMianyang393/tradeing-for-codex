import unittest

from portfolio import PortfolioConfig, select_portfolio_signals, strategy_family
from strategy import Signal


class PortfolioTests(unittest.TestCase):
    def test_strategy_family_uses_reason_prefix(self):
        self.assertEqual("trade_flow", strategy_family("trade_flow_breakout_long"))
        self.assertEqual("order_book", strategy_family("order_book_imbalance_long"))
        self.assertEqual("range", strategy_family("range_revert_long"))

    def test_same_symbol_direction_signals_vote_into_one_decision(self):
        decisions = select_portfolio_signals(
            [
                Signal("BTC-USDT-SWAP", 1, 3.0, "range", "range_revert_long"),
                Signal("BTC-USDT-SWAP", 1, 4.0, "trade_flow", "trade_flow_breakout_long"),
            ],
            PortfolioConfig(vote_boost=0.20),
        )

        self.assertEqual(1, len(decisions))
        self.assertEqual("BTC-USDT-SWAP", decisions[0].signal.symbol)
        self.assertEqual(2, decisions[0].votes)
        self.assertEqual(["range_revert_long", "trade_flow_breakout_long"], decisions[0].reasons)
        self.assertGreater(decisions[0].adjusted_score, decisions[0].normalized_score)

    def test_opposite_direction_duplicates_keep_stronger_direction(self):
        decisions = select_portfolio_signals(
            [
                Signal("BTC-USDT-SWAP", 1, 3.0, "range", "range_revert_long"),
                Signal("BTC-USDT-SWAP", -1, 4.0, "trend", "trend_short"),
            ],
            PortfolioConfig(),
        )

        self.assertEqual(1, len(decisions))
        self.assertEqual(-1, decisions[0].signal.direction)

    def test_strategy_budget_blocks_over_budget_family(self):
        decisions = select_portfolio_signals(
            [Signal("BTC-USDT-SWAP", 1, 4.0, "trade_flow", "trade_flow_breakout_long")],
            PortfolioConfig(strategy_risk_budgets={"trade_flow": 0.20}),
            current_strategy_exposure={"trade_flow": 0.20},
        )

        self.assertEqual([], decisions)

    def test_correlated_assets_are_downweighted_after_first_selection(self):
        decisions = select_portfolio_signals(
            [
                Signal("BTC-USDT-SWAP", 1, 4.0, "range", "range_revert_long"),
                Signal("ETH-USDT-SWAP", 1, 3.9, "range", "range_revert_long"),
            ],
            PortfolioConfig(correlation_groups=(("BTC-USDT-SWAP", "ETH-USDT-SWAP"),), correlation_penalty=0.5),
        )

        self.assertEqual(2, len(decisions))
        self.assertEqual("BTC-USDT-SWAP", decisions[0].signal.symbol)
        self.assertEqual("ETH-USDT-SWAP", decisions[1].signal.symbol)
        self.assertLess(decisions[1].adjusted_score, decisions[1].normalized_score)


if __name__ == "__main__":
    unittest.main()
