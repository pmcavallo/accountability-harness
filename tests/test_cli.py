"""The command line: report, verify and compare. Offline."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from accountability_harness import Harness, Scope  # noqa: E402
from accountability_harness.cli import main  # noqa: E402


def make_log(folder, calls=("read",)) -> Path:
    harness = Harness(Scope(name="s", allowed_tools={"read"}), log_dir=folder)
    for name in calls:
        harness.wrap(lambda: "ok", name=name)()
    return harness.finalize()


def test_report(tmp_path, capsys):
    log = make_log(tmp_path)
    assert main(["report", str(log)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Agent Accountability Report")
    assert "## Summary for the owner" in out


def test_verify_exit_codes(tmp_path, capsys):
    log = make_log(tmp_path)
    assert main(["verify", str(log)]) == 0
    assert "hash chain intact" in capsys.readouterr().out
    lines = log.read_text(encoding="utf-8").splitlines()
    log.write_text("\n".join(lines[:2] + lines[3:]) + "\n", encoding="utf-8")
    assert main(["verify", str(log)]) == 1
    assert "BROKEN" in capsys.readouterr().out
    legacy = tmp_path / "audit-old.jsonl"
    legacy.write_text('{"type": "run_meta"}\n', encoding="utf-8")
    assert main(["verify", str(legacy)]) == 2
    assert "not chained" in capsys.readouterr().out


def test_compare(tmp_path, capsys):
    make_log(tmp_path / "a")
    make_log(tmp_path / "b", calls=("read", "read"))
    assert main(["compare", str(tmp_path / "a"), str(tmp_path / "b")]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Behavior comparison")
    assert "| Tool calls per run (mean) | 1.00 | 2.00 |" in out


def test_runs_as_a_module(tmp_path):
    log = make_log(tmp_path)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    done = subprocess.run(
        [sys.executable, "-m", "accountability_harness", "verify", str(log)],
        capture_output=True, text=True, env=env,
    )
    assert done.returncode == 0 and "hash chain intact" in done.stdout


def test_the_entry_point_is_declared():
    assert 'accountability-harness = "accountability_harness.cli:main"' in (ROOT / "pyproject.toml").read_text()
