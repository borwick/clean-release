from clean_release.cli import main
from clean_release.stage import stage
from tests.conftest import commit_all, git, release, tag

BINARY = b"\x89PNG\r\n\x1a\n\0\0\0binary"


def one_release_then_changes(repo, capsys):
    """v1.0.1 in the public repo; then 1.1.0 staged with each kind of change."""
    tag(repo, "1.0.1")
    assert release(repo, "1.0.1", capsys)[0] == 0
    policy = repo / "clean-release.toml"
    policy.write_text(
        policy.read_text().replace(
            "citations = false\n", 'citations = false\nbinaries = ["src/pkg/*.bin"]\n'
        )
    )
    (repo / "src/pkg/new.py").write_text("NEW = 1\n")
    (repo / "src/pkg/logo.bin").write_bytes(BINARY)
    git(repo, "rm", "-q", "run.sh")
    commit_all(repo, "changes")
    tag(repo, "1.1.0")
    stage(repo, "1.1.0")


def public_state(public):
    return (
        git(public, "count-objects", "-v"),
        git(public, "status", "--porcelain", "--untracked-files=all"),
    )


def test_diff_over_one_public_release(repo, public, capsys):
    one_release_then_changes(repo, capsys)
    before = public_state(public)
    code = main(["diff"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert out.startswith("staged 1.1.0 (tree ")
    assert f"against {public}: v1.0.1 (tree " in out.splitlines()[0]
    assert "new: 2\n  src/pkg/logo.bin\n  src/pkg/new.py\n" in out
    assert "removed: 1\n  run.sh\n" in out
    assert "binaries: 1\n  src/pkg/logo.bin\n" in out
    assert "identity: Stager <stager@example.org> (author, committer and tagger)" in out
    assert "-# repo 1.0.1\n+# repo 1.1.0\n" in out
    marks = [
        "new:",
        "removed:",
        "binaries:",
        "check passed",
        "identity:",
        "diff --git",
    ]
    places = [out.index(m) for m in marks]
    assert places == sorted(places)
    assert public_state(public) == before


def test_diff_before_any_public_release(repo, public, capsys):
    tag(repo, "1.0.1")
    stage(repo, "1.0.1")
    assert main(["diff"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].endswith(f"against {public}: no public release yet")
    assert "new: 3\n" in out and "removed: 0\n" in out
    assert not (public / ".git").exists()


def test_diff_with_no_public_named_refuses(repo, capsys):
    tag(repo, "1.0.1")
    stage(repo, "1.0.1")
    assert main(["diff"]) == 1
    assert "no public tree: set [repos.repo] public" in capsys.readouterr().err
