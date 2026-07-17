from pathlib import Path

from prod.registry import PaperPrepEntry, is_paper_allowed, load_registry, upsert_entry


def test_upsert_and_allow(tmp_path: Path):
    path = tmp_path / "reg.json"
    assert is_paper_allowed("x", path) is False
    upsert_entry(
        PaperPrepEntry(
            strategy_id="x",
            track="ten_u_high_risk",
            status="paper_prep",
            config_fingerprint="abc",
            admitted_at="2026-07-17T00:00:00Z",
            admission_decision="paper_prep_allowed_with_warnings",
            warnings=["concentrated"],
            live_allowed=False,
        ),
        path,
    )
    assert is_paper_allowed("x", path) is True
    reg = load_registry(path)
    assert len(reg["entries"]) == 1
    assert reg["policy"]["prospective_wait_required"] is False
