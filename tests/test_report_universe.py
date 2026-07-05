import csv
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from backtester import run_report
from config import BacktestConfig


def _write_bars(path: Path, start_price: float) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for i in range(300):
            ts = 1_704_067_200_000 + i * 15 * 60_000
            price = start_price + i * 0.01
            writer.writerow([ts, price, price + 1, price - 1, price + 0.1, 10])


class ReportUniverseTests(unittest.TestCase):
    def test_long_window_preferred_symbols_do_not_filter_report_market(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            _write_bars(data_dir / "AAA_15m.csv", 100.0)
            _write_bars(data_dir / "BBB_15m.csv", 200.0)
            report_path = data_dir / "report.json"
            cfg = replace(
                BacktestConfig(),
                long_window_preferred_symbols=("AAA-USDT-SWAP",),
                windows_days=(),
            )

            report = run_report(data_dir, report_path, cfg)

            self.assertEqual(["AAA-USDT-SWAP", "BBB-USDT-SWAP"], report["symbols"])

    def test_run_report_writes_requested_window_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            _write_bars(data_dir / "AAA_15m.csv", 100.0)
            report_path = data_dir / "report.json"
            cfg = replace(
                BacktestConfig(),
                windows_days=(1,),
                min_bars=10,
                long_window_days=365,
            )

            report = run_report(data_dir, report_path, cfg)

            self.assertIn("1", report["windows"])


if __name__ == "__main__":
    unittest.main()
