"""The core must work, and fail clearly, when LangChain is not installed."""

import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

# Runs in a fresh interpreter where importing langchain_core fails, as it
# would if the package were not installed.
SCRIPT = r"""
import sys
sys.modules["langchain_core"] = None
sys.path.insert(0, sys.argv[1])

from accountability_harness import Harness, Scope, render_report

harness = Harness(Scope(name="t", allowed_tools={"read_data"}), log_dir=sys.argv[2])
harness.wrap(lambda: "x", name="read_data")()
report = render_report(harness.finalize())
assert "read_data" in report and "VIOLATION" not in report
assert not any(m.startswith("langchain") for m in sys.modules if sys.modules[m] is not None)

try:
    from accountability_harness import AccountabilityHandler
except ImportError as exc:
    print("IMPORT_ERROR:", exc)
"""


def test_core_runs_without_langchain(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(SRC), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "pip install accountability-harness[langchain]" in result.stdout


def test_core_modules_do_not_import_langchain():
    package = SRC / "accountability_harness"
    for module in ("__init__.py", "core.py", "scope.py", "audit.py", "report.py"):
        source = (package / module).read_text(encoding="utf-8")
        assert "import langchain" not in source and "from langchain" not in source, module
