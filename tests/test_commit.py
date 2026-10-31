import shlex

from clean_release import approve, commit, machine, policy
from clean_release.cli import main
from clean_release.stage import STAGING, stage
from tests.conftest import (
    POLICY,
    TERM,
    commit_all,
    git,
    name_public,
    release,
    staged_and_approved,
    tag,
    write_policy,
)


def count(path, *rev):
    return int(git(path, "rev-list", "--count", *(rev or ["HEAD"])).strip())


def approved_tree(repo):
    return approve.read(repo / STAGING).tree


def test_lesson_4_a_stray_file_in_the_public_tree_refuses(repo, public, capsys):
    tag(repo, "1.0.1")
    assert release(repo, "1.0.1", capsys)[0] == 0
    (public / "README (conflicted copy).md").write_text("sync\n")
    tag(repo, "1.1.0")
    code, _, err = release(repo, "1.1.0", capsys)
    assert code == 1
    assert "uncommitted changes" in err and "README (conflicted copy).md" in err
    assert count(public) == 1


def test_lesson_5_a_dirty_tree_after_the_commit_is_reported(
    repo, public, monkeypatch, capsys
):
    real = commit._checkout

    def checkout(path, new):
        real(path, new)
        (path / "stray.txt").write_text("sync wrote this\n")

    monkeypatch.setattr(commit, "_checkout", checkout)
    tag(repo, "1.0.1")
    code, out, err = release(repo, "1.0.1", capsys)
    assert code == 1
    assert "stray.txt" in err and "commit and tag v1.0.1 were made" in err
    assert git(public, "cat-file", "-t", "v1.0.1").strip() == "tag"
    assert f"git -C {public} push origin main refs/tags/v1.0.1" in out


def test_lesson_10_the_public_directory_keeps_its_inode(repo, public, capsys):
    inode = public.stat().st_ino
    tag(repo, "1.0.1")
    assert release(repo, "1.0.1", capsys)[0] == 0
    assert public.stat().st_ino == inode
    tag(repo, "1.1.0")
    assert release(repo, "1.1.0", capsys)[0] == 0
    assert public.stat().st_ino == inode
    assert count(public) == 2


def test_lesson_11_committing_a_version_twice_refuses(repo, public, capsys):
    tag(repo, "1.0.1")
    assert release(repo, "1.0.1", capsys)[0] == 0
    code, _, err = release(repo, "1.0.1", capsys)
    assert code == 1 and "already" in err
    assert count(public) == 1
    assert git(public, "tag", "-l").split() == ["v1.0.1"]


def test_unapproved_refuses(repo, public, capsys):
    tag(repo, "1.0.1")
    stage(repo, "1.0.1")
    assert main(["commit"]) == 1
    assert "not approved; run `clean-release approve`" in capsys.readouterr().err
    assert not (public / ".git").exists()


def test_a_restaged_tree_refuses_naming_both(repo, public, capsys):
    tag(repo, "1.0.1")
    staged_and_approved(repo, "1.0.1", capsys)
    old = approved_tree(repo)
    tag(repo, "1.0.2")
    stage(repo, "1.0.2")
    new = git(repo / STAGING, "rev-parse", "HEAD^{tree}").strip()
    assert main(["commit"]) == 1
    err = capsys.readouterr().err
    assert old in err and new in err and old != new
    assert not (public / ".git").exists()


def test_approve_with_a_finding_approves_nothing(repo, public, capsys):
    tag(repo, "1.0.1", f"# repo\n\n{TERM}\n")
    stage(repo, "1.0.1")
    assert main(["approve"]) == 1
    assert "denylist term" in capsys.readouterr().out
    assert not approve.path(repo / STAGING).exists()


def test_the_first_commit(repo, public, capsys):
    tag(repo, "1.0.1")
    code, out, _ = release(repo, "1.0.1", capsys)
    assert code == 0, out
    assert count(public) == 1
    assert git(public, "rev-parse", "HEAD^{tree}").strip() == approved_tree(repo)
    log = git(public, "log", "-1", "--format=%an <%ae>|%cn <%ce>|%s")
    who = "Stager <stager@example.org>"
    assert log == f"{who}|{who}|repo 1.0.1\n"
    assert git(public, "cat-file", "-t", "v1.0.1").strip() == "tag"
    tagger = git(
        public, "for-each-ref", "--format=%(taggername) %(taggeremail)", "refs/tags"
    )
    assert tagger == f"{who}\n"
    assert git(public, "status", "--porcelain", "--untracked-files=all") == ""
    assert (public / "run.sh").stat().st_mode & 0o111
    assert f"git -C {public} remote add origin <URL>" in out
    assert f"git -C {public} push origin main refs/tags/v1.0.1" in out


def test_a_second_release_is_parented_on_the_first(repo, public, capsys):
    tag(repo, "1.0.1")
    assert release(repo, "1.0.1", capsys)[0] == 0
    git(repo, "rm", "-q", "run.sh")
    tag(repo, "1.1.0")
    assert release(repo, "1.1.0", capsys)[0] == 0
    first = git(public, "rev-parse", "v1.0.1^{commit}")
    assert git(public, "rev-parse", "HEAD^") == first
    assert not (public / "run.sh").exists()
    assert git(public, "status", "--porcelain", "--untracked-files=all") == ""


def test_a_missing_directory_refuses_with_the_mkdir(repo, public, capsys):
    public.rmdir()
    tag(repo, "1.0.1")
    code, _, err = release(repo, "1.0.1", capsys)
    assert code == 1 and f"mkdir -p {public}" in err
    assert not public.exists()


def test_a_non_empty_non_git_directory_refuses(repo, public, capsys):
    (public / "notes.txt").write_text("mine\n")
    tag(repo, "1.0.1")
    code, _, err = release(repo, "1.0.1", capsys)
    assert code == 1 and "neither a git repo nor empty" in err
    assert not (public / ".git").exists()


def test_a_head_past_the_last_tag_refuses(repo, public, capsys):
    tag(repo, "1.0.1")
    assert release(repo, "1.0.1", capsys)[0] == 0
    (public / "extra.txt").write_text("x\n")
    commit_all(public, "by hand")
    tag(repo, "1.1.0")
    code, _, err = release(repo, "1.1.0", capsys)
    assert code == 1 and "is not the last release v1.0.1" in err
    assert count(public) == 2


def test_a_repo_with_no_matching_tag_refuses(repo, public, capsys):
    git(public, "init", "-q", "-b", "main")
    (public / "x.txt").write_text("x\n")
    commit_all(public, "someone else's")
    tag(repo, "1.0.1")
    code, _, err = release(repo, "1.0.1", capsys)
    assert code == 1 and "no tag matching v{version}" in err
    assert count(public) == 1


def test_a_lower_version_refuses(repo, public, capsys):
    tag(repo, "1.1.0")
    assert release(repo, "1.1.0", capsys)[0] == 0
    code, _, err = release(repo, "1.0.0", capsys)
    assert code == 1 and "1.0.0 is not newer than the last release v1.1.0" in err
    assert count(public) == 1


def test_a_version_not_dotted_integers_refuses(repo, public, capsys):
    tag(repo, "1.0.1-rc1")
    code, _, err = release(repo, "1.0.1-rc1", capsys)
    assert code == 1 and "not dotted integers" in err
    assert not (public / ".git").exists()


def test_the_machine_config_names_the_public_tree_before_the_policy(
    repo, home, tmp_path
):
    write_policy(repo, POLICY.replace("[release]\n", '[release]\npublic = "~/pub"\n'))
    pol = policy.load(repo)
    assert commit.public_path(machine.load("repo"), pol) == home / "pub"
    name_public(home, tmp_path / "mine")
    assert commit.public_path(machine.load("repo"), pol) == tmp_path / "mine"
    assert commit.public_path(None, None) is None


def test_the_push_commands_survive_a_space_in_the_path(tmp_path):
    public = tmp_path / "public repo"
    public.mkdir()
    git(public, "init", "-q")
    add, push = commit._push(public, "main", "v1.0.1")
    assert shlex.split(add)[:3] == ["git", "-C", str(public)]
    assert shlex.split(push) == [
        "git",
        "-C",
        str(public),
        "push",
        "origin",
        "main",
        "refs/tags/v1.0.1",
    ]
