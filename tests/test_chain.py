"""The hash-chained audit log: tamper-evident, not tamper-proof."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from accountability_harness import Harness, Scope, render_report, verify  # noqa: E402
from accountability_harness.audit import GENESIS  # noqa: E402


def run_log(tmp_path) -> Path:
    harness = Harness(Scope(name="t", allowed_tools={"read"}), log_dir=tmp_path)
    read = harness.wrap(lambda n: f"item {n}", name="read")
    for n in range(3):
        read(n)
    return harness.finalize()


def lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def rewrite(path, new_lines):
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def test_intact_chain(tmp_path):
    log = run_log(tmp_path)
    entries = [json.loads(line) for line in lines(log)]
    assert entries[0]["prev_hash"] == GENESIS
    assert all(b["prev_hash"] == a["hash"] for a, b in zip(entries, entries[1:]))
    assert verify(log) == ("intact", len(entries))
    assert "- **Audit log:** hash chain intact across" in render_report(log)


def test_an_edited_line_breaks_the_chain_at_that_line(tmp_path):
    log = run_log(tmp_path)
    content = lines(log)
    content[3] = content[3].replace("item 1", "item 9")  # the second action's result
    assert "item 9" in content[3]  # the edit really changed the line
    rewrite(log, content)
    assert verify(log) == ("broken", 4)
    assert "hash chain BROKEN" in render_report(log) and "line 4" in render_report(log)


def test_a_deleted_line_breaks_the_chain_at_the_next_line(tmp_path):
    log = run_log(tmp_path)
    content = lines(log)
    del content[3]
    rewrite(log, content)
    assert verify(log) == ("broken", 4)


def test_reordered_lines_break_the_chain(tmp_path):
    log = run_log(tmp_path)
    content = lines(log)
    content[3], content[4] = content[4], content[3]
    rewrite(log, content)
    assert verify(log) == ("broken", 4)


def test_a_line_that_is_no_longer_json_breaks_the_chain(tmp_path):
    log = run_log(tmp_path)
    content = lines(log)
    content[2] = content[2][:-5]
    rewrite(log, content)
    assert verify(log) == ("broken", 3)


def test_an_unchained_legacy_log_reports_not_chained(tmp_path):
    legacy = tmp_path / "audit-old.jsonl"
    legacy.write_text(
        '{"type": "run_meta", "agent_name": "a", "run_id": "r"}\n'
        '{"type": "scope", "scope": {"name": "s", "allowed_tools": []}}\n',
        encoding="utf-8",
    )
    assert verify(legacy) == ("not chained", 0)
    report = render_report(legacy)
    assert "not chained: this log was written by an older version" in report


def test_what_the_chain_cannot_detect_is_stated(tmp_path):
    """Cutting lines from the end leaves a valid shorter chain; the report says so."""
    log = run_log(tmp_path)
    rewrite(log, lines(log)[:-1])
    assert verify(log)[0] == "intact"
    assert "lines cut from the end" in render_report(log)


def test_verify_text_checks_a_log_held_in_memory(tmp_path):
    from accountability_harness.audit import verify_text

    log = run_log(tmp_path)
    text = log.read_text(encoding="utf-8")
    assert verify_text(text) == verify(log)
    lines = text.splitlines()
    lines[2] = lines[2].replace('"seq": 1', '"seq": 9')
    assert verify_text("\n".join(lines)) == ("broken", 3)
    assert log.read_text(encoding="utf-8") == text  # the file on disk is untouched
