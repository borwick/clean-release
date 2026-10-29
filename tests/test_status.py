from clean_release.cli import main
from clean_release.stage import stage
from tests.conftest import release, tag


def status(capsys):
    assert main(["status"]) == 0
    return capsys.readouterr().out


def test_status_over_one_public_release(repo, public, capsys):
    tag(repo, "1.0.1")
    assert release(repo, "1.0.1", capsys)[0] == 0
    tag(repo, "1.1.0")
    stage(repo, "1.1.0")
    out = status(capsys)
    assert f"public: {public}\n" in out
    assert "last public version: 1.0.1\n" in out
    assert "staged: 1.1.0 (tree " in out
    assert "approved: no (the approval is for 1.0.1, tree " in out
    assert "public tree: clean\n" in out

    assert main(["approve"]) == 0
    capsys.readouterr()
    assert "approved: yes\n" in status(capsys)

    (public / "stray.txt").write_text("sync\n")
    assert "public tree: 1 uncommitted\n  ?? stray.txt\n" in status(capsys)


def test_status_with_nothing_staged_and_no_public_release(repo, public, capsys):
    out = status(capsys)
    assert "last public version: none\n" in out
    assert "staged: none (no staging repo" in out
    assert "approved: no\n" in out
    assert "public tree: empty\n" in out
