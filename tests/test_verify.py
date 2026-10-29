import json
import shlex
import sys

from clean_release.cli import main
from clean_release.stage import STAGING, stage
from tests.conftest import append_policy, git

PY = shlex.quote(sys.executable)


def staged_with(repo, *commands):
    """Stage v1.0.0 with citations off and commands as `[verify]`."""
    listed = ", ".join(json.dumps(c) for c in commands)
    append_policy(
        repo, f"[scan]\ncitations = false\n\n[verify]\ncommands = [{listed}]\n"
    )
    stage(repo, "1.0.0")


def test_a_failing_command_fails_check(repo, capsys):
    staged_with(repo, f"{PY} -c \"import sys; print('boom'); sys.exit(3)\"")
    assert main(["check"]) == 1
    out, err = capsys.readouterr()
    assert "[verify]: `" in out and "exited 3" in out
    assert "boom" in err


def test_a_passing_command_runs_in_a_copy(repo, capsys, monkeypatch):
    (repo / "notes.txt").write_text("untracked and private\n")
    monkeypatch.setenv("VIRTUAL_ENV", str(repo / ".venv"))
    script = (
        "import os, pathlib as p; p.Path('made.txt').write_text('x'); "
        "assert p.Path('README.md').exists(); "
        "assert not p.Path('notes.txt').exists(); "
        "assert 'VIRTUAL_ENV' not in os.environ"
    )
    staged_with(repo, f'{PY} -c "{script}"')
    assert main(["check"]) == 0
    assert f'verify: `{PY} -c "{script}"`' in capsys.readouterr().out
    assert not (repo / STAGING / "made.txt").exists()
    assert git(repo / STAGING, "status", "--porcelain") == ""


def test_an_unknown_command_is_a_finding(repo, capsys):
    staged_with(repo, "no-such-command-for-clean-release --flag")
    assert main(["check"]) == 1
    out = capsys.readouterr().out
    assert "[verify]: `no-such-command-for-clean-release --flag` not found" in out
