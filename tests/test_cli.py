import pytest

from clean_release import __version__
from clean_release.cli import main


def test_version(capsys):
    with pytest.raises(SystemExit) as raised:
        main(["--version"])
    assert raised.value.code == 0
    assert capsys.readouterr().out.strip() == __version__


def test_bare_run_succeeds():
    assert main([]) == 0


def test_help_lists_commands(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert all(
        c in out
        for c in (
            "init",
            "stage",
            "check",
            "diff",
            "approve",
            "commit",
            "status",
            "doctor",
        )
    )


def test_stage_help_shows_version(capsys):
    with pytest.raises(SystemExit):
        main(["stage", "--help"])
    assert "VERSION" in capsys.readouterr().out


def test_outside_a_repo_refuses(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert main(["stage", "1.0.0"]) == 1
    assert capsys.readouterr().err.startswith("clean-release: ")
