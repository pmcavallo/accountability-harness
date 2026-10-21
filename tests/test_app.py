"""The Streamlit demo app: every page loads, the class moment shows the right
counts, the tamper check fails at the edited line, and the app never calls
a model or reads a key.

The AppTest tests need the [app] extra (streamlit) and are skipped without
it. The no-model test reads the source and needs nothing.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app" / "streamlit_app.py"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "demo"))

PAGES = ["Run a scenario", "Observe vs enforce", "The scope", "Change comparison", "Findings", "Tamper check"]
HEADER = "Synthetic demo. No real email is sent. No AI model runs in this app."


def app_on(page: str):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=60).run()
    at.sidebar.radio[0].set_value(page).run()
    return at


# -- no model, no key ---------------------------------------------------


def local_sources() -> dict[str, str]:
    """The app and every local module it runs: the demo and the package."""
    files = [APP, ROOT / "demo" / "inbox_triage.py", ROOT / "demo" / "emails.py"]
    files += sorted((ROOT / "src" / "accountability_harness").glob("*.py"))
    return {f.name: f.read_text(encoding="utf-8") for f in files}


def test_the_app_never_imports_a_model_sdk_or_reads_a_key():
    for name, source in local_sources().items():
        tree = ast.parse(source)
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")])
        }
        assert not imported & {"anthropic", "openai", "requests", "httpx", "urllib", "socket"}, name
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("environ", "getenv", "secrets"), f"{name}: .{node.attr}"
            if isinstance(node, ast.Name):
                assert node.id not in ("environ", "getenv"), f"{name}: {node.id}"
    assert "API_KEY" not in local_sources()["streamlit_app.py"].upper()


def test_running_every_page_loads_no_model_sdk():
    pytest.importorskip("streamlit")
    script = (
        "import sys\n"
        "from streamlit.testing.v1 import AppTest\n"
        f"at = AppTest.from_file({str(APP)!r}, default_timeout=60).run()\n"
        f"for page in {PAGES!r}:\n"
        "    at.sidebar.radio[0].set_value(page).run()\n"
        "    assert not at.exception, page\n"
        "print('anthropic' in sys.modules, 'openai' in sys.modules)\n"
    )
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=ROOT, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == "False False"


# -- pages ----------------------------------------------------------------


@pytest.mark.parametrize("page", PAGES)
def test_each_page_loads_without_errors_and_shows_the_header(page):
    pytest.importorskip("streamlit")
    at = app_on(page)
    assert not at.exception
    assert at.info[0].value == HEADER
    assert at.header[0].value == page


@pytest.mark.parametrize("scenario", ["clean", "violation", "mutation", "argument", "unapproved", "replay"])
@pytest.mark.parametrize("mode", ["observe", "enforce"])
def test_every_scenario_runs_in_both_modes(scenario, mode):
    pytest.importorskip("streamlit")
    at = app_on("Run a scenario")
    at.selectbox[0].set_value(scenario).run()
    at.radio(key=f"mode-{scenario}").set_value(mode).run()
    assert not at.exception
    subheaders = [s.value for s in at.subheader]
    assert subheaders[0] == "Summary for the owner"
    assert [s[:2] for s in subheaders[1:]] == ["1.", "2.", "3."]
    assert any(s.value.startswith("Audit log: hash chain intact") for s in at.success)


def test_blocked_and_flagged_calls_stand_out():
    pytest.importorskip("streamlit")
    at = app_on("Run a scenario")
    at.selectbox[0].set_value("violation").run()
    errors = [e.value for e in at.error]
    assert "Outside the scope, flagged but not stopped: send_email." in errors
    assert "Changes that cannot be undone: send_email." in errors
    at.radio(key="mode-violation").set_value("enforce").run()
    assert "Blocked before it ran: send_email. The tool never executed." in [e.value for e in at.error]
    assert at.metric[0].value == "0"


def test_governance_findings_stand_out_for_the_unapproved_scope():
    pytest.importorskip("streamlit")
    at = app_on("Run a scenario")
    at.selectbox[0].set_value("unapproved").run()
    warnings = [w.value for w in at.warning]
    assert "Governance finding: No one is recorded as having approved this scope." in warnings
    assert len(warnings) == 3


def test_the_replay_hides_the_model_written_drafts():
    pytest.importorskip("streamlit")
    import inbox_triage

    at = app_on("Run a scenario")
    at.selectbox[0].set_value("replay").run()
    shown = "\n".join(m.value for m in at.markdown)
    assert "not shown in the app" in shown
    for _, args in inbox_triage.SCENARIOS["replay"][2]:
        if "draft" in args:
            assert args["draft"].splitlines()[0] not in shown


def test_side_by_side_observe_sends_one_enforce_sends_none():
    pytest.importorskip("streamlit")
    at = app_on("Observe vs enforce")
    assert [s.value for s in at.subheader] == ["Observe mode", "Enforce mode"]
    assert [m.label for m in at.metric] == ["Emails actually sent"] * 2
    assert [m.value for m in at.metric] == ["1", "0"]
    errors = [e.value for e in at.error]
    assert "ran and the email was sent" in errors[0] and "blocked before it ran" in errors[1]


def test_scope_card_shows_governance_tools_and_findings():
    pytest.importorskip("streamlit")
    at = app_on("The scope")
    names = list(at.selectbox[0].options)
    assert "inbox-assistant.toml" in names and "inbox-assistant-unapproved.toml" in names
    at.selectbox[0].select_index(names.index("inbox-assistant.toml")).run()
    text = "\n".join(m.value for m in at.markdown)
    assert "Managing director, Tallow Lane Events" in text and "2027-04-15" in text
    assert at.success[0].value == "None." and not at.warning
    at.selectbox[0].select_index(names.index("inbox-assistant-unapproved.toml")).run()
    assert len(at.warning) == 3 and not at.exception


def test_comparison_chart_uses_the_committed_numbers():
    pytest.importorskip("streamlit")
    text = (ROOT / "experiments" / "COMPARE-neutral-vs-permissive.md").read_text(encoding="utf-8")
    at = app_on("Change comparison")
    flags = [w.value for w in at.warning]
    assert len(flags) == 2 and all("place_calendar_hold" in f for f in flags)
    assert "4 of 50 runs in A and 50 of 50 runs in B" in flags[0]
    assert "4 of 50" in text and "50 of 50" in text


def test_findings_page_quotes_the_headline_exactly():
    pytest.importorskip("streamlit")
    text = (ROOT / "experiments" / "RESULTS.md").read_text(encoding="utf-8")
    headline = text.split("## Headline\n")[1].split("\n## ")[0].strip()
    at = app_on("Findings")
    assert headline in [m.value for m in at.markdown]
    shown = "\n".join(m.value for m in at.markdown)
    assert "experiments/RESULTS.md" in shown and "docs/WHAT-THIS-DOES-NOT-PROVE.md" in shown


def test_tamper_check_fails_at_the_edited_line(tmp_path):
    pytest.importorskip("streamlit")
    import inbox_triage

    log = inbox_triage.run_with_core("violation", log_dir=tmp_path)
    lines = log.read_text(encoding="utf-8").splitlines()
    send = next(i for i, l in enumerate(lines, 1) if json.loads(l).get("tool") == "send_email" and json.loads(l)["type"] == "action")
    at = app_on("Tamper check")
    assert at.success[0].value == f"Chain intact: {len(lines)} entries verified."
    assert at.error[0].value == f"Chain broken at line {send}: the edit is detected."
    assert at.subheader[1].value == f"A copy with line {send} edited"
    assert sorted(p.name for p in tmp_path.iterdir()) == [log.name]  # the app wrote nothing here
