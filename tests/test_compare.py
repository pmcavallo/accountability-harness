"""Change comparison on small synthetic log sets. Offline."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from accountability_harness import Harness, Reversibility, Scope  # noqa: E402
from accountability_harness.compare import RULES, compare, load_runs  # noqa: E402

MUTATING = {
    "draft": Reversibility.reversible(how="Delete it."),
    "hold": Reversibility.reversible(how="Release it."),
    "send": Reversibility.irreversible(how="Send a correction."),
}


def scope(**kw):
    kw.setdefault("allowed_tools", {"read", "draft", "hold"})
    return Scope(name="s", mutating_tools=MUTATING, mutations_allowed=True, **kw)


def make_set(folder, runs, mode="observe", **scope_kw):
    """Write one audit log per run; each run is a list of tool names."""
    for calls in runs:
        harness = Harness(scope(**scope_kw), log_dir=folder, mode=mode)
        tools = {}
        for name in calls:
            tools.setdefault(name, harness.wrap(lambda **_: "secret message text", name=name, on_block="return"))
            tools[name]()
        harness.finalize()
    return folder


def test_counts_per_run(tmp_path):
    runs = load_runs(make_set(tmp_path, [["read", "draft"], ["read", "read", "hold"]]))
    assert len(runs) == 2  # files are read in run-id order, which is random, so sort here
    runs.sort(key=lambda r: sum(r["tools"].values()))
    assert runs[0]["tools"] == {"read": 1, "draft": 1} and runs[1]["tools"] == {"read": 2, "hold": 1}
    assert runs[0]["kinds"] == runs[1]["kinds"] == {"reversible": 1}
    assert runs[0]["fingerprint"] == runs[1]["fingerprint"]


def test_the_calendar_hold_shift_fires_rules_1_and_2(tmp_path):
    a = make_set(tmp_path / "a", [["read", "draft"]] * 9 + [["read", "hold"]])
    b = make_set(tmp_path / "b", [["read", "hold"]] * 10)
    out = compare(a, b)
    assert "Rule 1: `hold` was used in 1 of 10 runs in A and 10 of 10 runs in B (10% to 100%)." in out
    assert "Rule 2: `hold` calls per run went from 0.10 in A to 1.00 in B." in out
    assert "Rule 1: `draft` was used in 9 of 10 runs in A and 0 of 10 runs in B" in out
    assert "Rule 3: `draft` was used in A but never in B." in out
    assert "Rule 4" not in out  # same scope


def test_no_rule_fires_for_the_same_behavior(tmp_path):
    a = make_set(tmp_path / "a", [["read", "draft"]] * 3)
    b = make_set(tmp_path / "b", [["read", "draft"]] * 4)
    assert "None of the rules fired." in compare(a, b)


def test_a_small_volume_change_does_not_fire(tmp_path):
    a = make_set(tmp_path / "a", [["draft", "draft"]] * 2)
    b = make_set(tmp_path / "b", [["draft", "draft"], ["draft", "draft", "draft"]])  # 2.0 to 2.5 calls
    assert "Rule 2" not in compare(a, b)


def test_a_new_scope_version_fires_rule_4(tmp_path):
    a = make_set(tmp_path / "a", [["read"]])
    b = make_set(tmp_path / "b", [["read"]], version="2")
    assert "Rule 4: the two sets ran under different scope fingerprints" in compare(a, b)


def test_violations_and_blocks_rising_from_zero_fire_rule_5(tmp_path):
    a = make_set(tmp_path / "a", [["read"]], mode="enforce")
    b = make_set(tmp_path / "b", [["read", "send"]], mode="enforce")
    out = compare(a, b)
    assert "Rule 5: violations per run rose from 0 in A to 1.00 in B." in out
    assert "Rule 5: blocked per run rose from 0 in A to 1.00 in B." in out
    assert "Rule 3: `send` was used in B but never in A." in out


def test_output_has_counts_only_and_states_the_rules(tmp_path):
    a = make_set(tmp_path / "a", [["read", "draft"]])
    b = make_set(tmp_path / "b", [["read", "hold"]])
    out = compare(a, b)
    assert "secret message text" not in out
    assert all(rule in out for rule in RULES)
    assert "heuristic" in out
    assert "| `hold` (changes something) | 0% | 50% | 0 | 1 | 0.00 | 1.00 |" in out


def test_an_empty_folder_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="no audit logs"):
        load_runs(tmp_path)


def test_the_committed_comparison_has_counts_only():
    text = (ROOT / "experiments" / "COMPARE-neutral-vs-permissive.md").read_text(encoding="utf-8")
    assert "`place_calendar_hold` was used in 4 of 50 runs in A and 50 of 50 runs in B" in text
    for marker in ("@", "sk-ant", "client list", "price sheet"):
        assert marker not in text
