from pathlib import Path

from prod.bootstrap_server import seed_paper_registry
from prod.registry import is_paper_allowed
from ten_u_event_trend_contract_v2 import STRATEGY_ID


def test_seed_registry_creates_paper_prep(tmp_path: Path):
    reg = tmp_path / "reg.json"
    result = seed_paper_registry(reg)
    assert result["action"] == "seeded"
    assert is_paper_allowed(STRATEGY_ID, reg) is True
    # second call keeps existing
    again = seed_paper_registry(reg)
    assert again["action"] == "keep_existing"


def test_seed_registry_force(tmp_path: Path):
    reg = tmp_path / "reg.json"
    seed_paper_registry(reg)
    forced = seed_paper_registry(reg, force=True)
    assert forced["action"] == "seeded"
