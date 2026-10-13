import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_scripted_demo_runs():
    out = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "scripted_run.py")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "done, and the alerts cleared" in out
    assert "evidence not found in any tool answer: 'upstream payments returned 500'" in out
