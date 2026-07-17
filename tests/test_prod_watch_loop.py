from pathlib import Path

from prod.watch_loop import run_watch_loop


def test_watch_loop_finite_with_stub_pipeline(tmp_path: Path):
    sleeps: list[float] = []
    n = {"i": 0}

    def pipeline():
        n["i"] += 1
        return {"formal_status": "ok", "iteration_internal": n["i"]}

    out = tmp_path / "watch.json"
    report = run_watch_loop(
        iterations=3,
        interval_seconds=1.5,
        data_dir=tmp_path,
        manifest_path=tmp_path / "m.json",
        report_path=out,
        sleep_fn=lambda s: sleeps.append(s),
        pipeline_fn=pipeline,
    )
    assert report["formal_status"] == "ok"
    assert len(report["cycles"]) == 3
    assert sleeps == [1.5, 1.5]
    assert out.exists()


def test_watch_loop_lock_busy(tmp_path: Path):
    def pipeline():
        raise TimeoutError("runtime lock busy")

    report = run_watch_loop(
        iterations=1,
        interval_seconds=0,
        data_dir=tmp_path,
        manifest_path=tmp_path / "m.json",
        report_path=tmp_path / "w.json",
        pipeline_fn=pipeline,
    )
    assert report["cycles"][0]["formal_status"] == "lock_busy"
