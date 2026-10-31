import re
import subprocess

import pytest

from clean_release import Refusal
from clean_release.cli import main
from clean_release.stage import STAGING, stage
from tests.conftest import TERM, commit_all, git, write_policy


def staged_tree(root):
    """{path: mode} of the staging repo's HEAD^{tree}."""
    out = git(root / STAGING, "ls-tree", "-r", "HEAD")
    return {line.split("\t")[1]: line.split()[0] for line in out.splitlines()}


def commits(root):
    return int(git(root / STAGING, "rev-list", "--count", "HEAD").strip())


def test_the_export_is_written(repo, capsys):
    assert main(["stage", "1.0.0"]) == 0
    assert staged_tree(repo) == {
        "README.md": "100644",
        "run.sh": "100755",
        "src/pkg/__init__.py": "100644",
    }
    staging = repo / STAGING
    assert (staging / "src/pkg/__init__.py").read_text() == "VALUE = 1\n"
    assert not (staging / "docs").exists()
    assert git(staging, "status", "--porcelain") == ""
    out = capsys.readouterr().out
    assert "3 path(s) shipped, 2 excluded" in out
    tree = git(staging, "rev-parse", "HEAD^{tree}").strip()
    assert f"tree {tree}" in out


def test_commit_carries_identity_and_tag(repo):
    done = stage(repo, "1.0.0")
    tag_sha = git(repo, "rev-parse", "v1.0.0^{commit}").strip()
    log = git(done.path, "log", "-1", "--format=%an <%ae>|%cn|%s")
    assert log == f"Stager <stager@example.org>|Stager|stage 1.0.0 {tag_sha}\n"


def test_only_the_tag_ships(repo):
    (repo / "src/pkg/__init__.py").write_text("VALUE = 2\n")
    (repo / "src/pkg/untracked.py").write_text("x = 1\n")
    stage(repo, "1.0.0")
    assert "src/pkg/untracked.py" not in staged_tree(repo)
    assert (repo / STAGING / "src/pkg/__init__.py").read_text() == "VALUE = 1\n"


def test_a_dropped_file_goes(repo):
    stage(repo, "1.0.0")
    git(repo, "rm", "-q", "run.sh")
    commit_all(repo, "drop run.sh")
    git(repo, "tag", "v1.1.0")
    stage(repo, "1.1.0")
    assert "run.sh" not in staged_tree(repo)
    assert not (repo / STAGING / "run.sh").exists()
    assert commits(repo) == 2


def test_missing_tag_refuses(repo):
    with pytest.raises(Refusal, match=re.escape("no tag v9.9.9")):
        stage(repo, "9.9.9")


def test_unignored_local_refuses(repo):
    (repo / ".gitignore").write_text("")
    with pytest.raises(Refusal, match="not ignored"):
        stage(repo, "1.0.0")
    assert not (repo / STAGING).exists()


def test_rewrite_applies(repo):
    write_policy(
        repo,
        (repo / "clean-release.toml").read_text()
        + "\n[[rewrite]]\npath = \"README.md\"\npattern = '\\]\\((docs/[^)]+)\\)'\n"
        "replace = '](https://example.org/\\1)'\nexpect = 1\n",
    )
    stage(repo, "1.0.0")
    readme = (repo / STAGING / "README.md").read_text()
    assert "](https://example.org/docs/guide.md)" in readme


def test_lesson_1_a_term_in_the_policy_does_not_reach_the_export(repo):
    (repo / "sub").mkdir()
    (repo / "sub/CLAUDE.md").write_text("private rules\n")
    write_policy(
        repo,
        f'# {TERM}\n[release]\nmessage = "repo {{version}}"\n[paths]\ninclude = ["**"]\n',
    )
    commit_all(repo, "policy and sub/CLAUDE.md")
    git(repo, "tag", "v1.0.1")
    assert TERM in git(repo, "show", "v1.0.1:clean-release.toml")
    stage(repo, "1.0.1")
    tree = staged_tree(repo)
    assert "clean-release.toml" not in tree and "sub/CLAUDE.md" not in tree
    assert "README.md" in tree
    found = subprocess.run(
        ["git", "-C", str(repo / STAGING), "grep", "-i", "-e", TERM, "HEAD"],
        capture_output=True,
        check=False,
    )
    assert found.returncode == 1 and found.stdout == b""


def test_lesson_8_a_rule_matching_zero_times_refuses(repo, capsys):
    stage(repo, "1.0.0")
    write_policy(
        repo,
        (repo / "clean-release.toml").read_text()
        + '\n[[rewrite]]\npath = "README.md"\npattern = "no such text"\n'
        'replace = "x"\nexpect = 1\n',
    )
    assert main(["stage", "1.0.0"]) == 1
    err = capsys.readouterr().err
    assert "[[rewrite]] 1 on README.md" in err and "matched 0 time(s)" in err
    assert commits(repo) == 1
