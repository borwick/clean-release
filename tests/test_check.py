import hashlib
import os
import re

from clean_release.cli import main
from clean_release.stage import stage
from tests.conftest import (
    POLICY,
    TERM,
    append_policy,
    commit_all,
    git,
    path_without_scanners,
    token,
    write_policy,
)

NO_CITATIONS = "[scan]\ncitations = false\n"


def stage_release(root, version, policy_extra=""):
    """Commit the tree, tag it, add policy_extra to the policy, and stage it."""
    commit_all(root, version)
    git(root, "tag", f"v{version}")
    if policy_extra:
        append_policy(root, policy_extra)
    stage(root, version)


def run(capsys):
    code = main(["check"])
    return code, capsys.readouterr().out


def test_clean_tree_passes(repo, capsys):
    (repo / "README.md").write_text("# repo\n")
    stage_release(repo, "1.0.1")
    code, out = run(capsys)
    tree = git(repo / "local/clean-release", "rev-parse", "HEAD^{tree}").strip()
    assert code == 0
    assert f"check passed: tree {tree}, 3 path(s)" in out
    assert re.search(r"^scanner: betterleaks \S+$", out, re.MULTILINE)


def test_lesson_2_a_rewrite_that_hides_a_term_still_fails(repo, capsys):
    (repo / "README.md").write_text(f"# repo\n\n{TERM}\n")
    rule = (
        '[[rewrite]]\npath = "README.md"\npattern = "{}"\nreplace = "x"\nexpect = 1\n'
    )
    stage_release(repo, "1.0.1", NO_CITATIONS + rule.format(TERM))
    code, out = run(capsys)
    assert code == 1
    assert "README.md:3: denylist term in the rewrite source" in out
    assert "README.md:3: denylist term\n" not in out


def test_lesson_3_a_term_in_a_rewritten_file_fails(repo, capsys):
    rule = (
        '[[rewrite]]\npath = "README.md"\npattern = "# repo"\n'
        f'replace = "# {TERM}"\nexpect = 1\n'
    )
    append_policy(repo, NO_CITATIONS + rule)
    stage(repo, "1.0.0")
    code, out = run(capsys)
    assert code == 1
    assert "README.md:1: denylist term\n" in out
    assert "rewrite source" not in out


def test_lesson_7_a_shipped_doc_naming_an_excluded_claude_md_fails(repo, capsys):
    (repo / "sub").mkdir()
    (repo / "sub/CLAUDE.md").write_text("rules\n")
    (repo / "README.md").write_text("# repo\n\nThe rules are in sub/CLAUDE.md.\n")
    stage_release(repo, "1.0.1")
    code, out = run(capsys)
    assert code == 1
    assert "README.md:3: cites sub/CLAUDE.md which did not ship" in out
    append_policy(repo, NO_CITATIONS)
    assert run(capsys)[0] == 0


def test_citations_of_a_link_and_a_directory(repo, capsys):
    (repo / "src/pkg/notes.md").write_text("See [g](../../docs/guide.md) and docs/.\n")
    stage_release(repo, "1.0.1")
    code, out = run(capsys)
    assert code == 1
    assert "src/pkg/notes.md:1: cites docs/guide.md which did not ship" in out
    assert "src/pkg/notes.md:1: cites docs/ which did not ship" in out
    assert "README.md:3: cites docs/guide.md which did not ship" in out


def test_citable_paths_are_not_flagged(repo, capsys):
    (repo / "sub").mkdir()
    (repo / "sub/CLAUDE.md").write_text("rules\n")
    (repo / "src/pkg/notes.md").write_text(
        "Set clean-release.toml, see sub/CLAUDE.md,\n"
        "[g](../../docs/guide.md) and docs/.\n"
    )
    citable = '[scan]\ncitable = ["clean-release.toml", "docs/**"]\n'
    stage_release(repo, "1.0.1", citable)
    code, out = run(capsys)
    cites = [line for line in out.splitlines() if " cites " in line]
    assert code == 1
    assert cites == ["src/pkg/notes.md:1: cites sub/CLAUDE.md which did not ship"]


def test_unlisted_binary_fails_and_passes_once_listed(repo, capsys):
    (repo / "src/pkg/logo.png").write_bytes(b"\x89PNG\0\0data")
    stage_release(repo, "1.0.1", NO_CITATIONS)
    code, out = run(capsys)
    assert code == 1
    assert "src/pkg/logo.png: binary not in [scan] binaries" in out
    write_policy(
        repo,
        (repo / "clean-release.toml")
        .read_text()
        .replace("citations = false", 'citations = false\nbinaries = ["**/*.png"]'),
    )
    assert run(capsys)[0] == 0


def test_symlinks_out_of_the_tree_fail(repo, capsys):
    os.symlink(os.sep + "etc", repo / "src/abs")
    os.symlink("../../x", repo / "src/up")
    os.symlink("pkg/__init__.py", repo / "src/inside")
    stage_release(repo, "1.0.1", NO_CITATIONS)
    code, out = run(capsys)
    assert code == 1
    assert "src/abs: symlink out of the tree" in out
    assert "src/up: symlink out of the tree" in out
    assert "src/inside" not in out


def test_gitlink_fails(repo, capsys):
    sha = git(repo, "rev-parse", "HEAD").strip()
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{sha},src/sub")
    git(repo, "commit", "-q", "--no-gpg-sign", "-m", "submodule")
    git(repo, "tag", "v1.0.1")
    append_policy(repo, NO_CITATIONS)
    stage(repo, "1.0.1")
    code, out = run(capsys)
    assert code == 1
    assert "src/sub: submodule" in out


def test_lfs_pointer_fails(repo, capsys):
    (repo / "src/big.bin").write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:00\nsize 1\n"
    )
    stage_release(repo, "1.0.1", NO_CITATIONS)
    code, out = run(capsys)
    assert code == 1
    assert "src/big.bin: LFS pointer" in out


def test_digests_of_a_word_and_a_pair_fail_without_printing_them(repo, home, capsys):
    word, pair = "flumphwick", "grelna tovish"
    digests = [hashlib.sha256(w.encode()).hexdigest() for w in (word, pair)]
    (home / ".config/clean-release/terms/common.toml").write_text(
        f'sha256 = ["{digests[0]}", "{digests[1]}"]\n'
    )
    (repo / "README.md").write_text(f"# repo\n\n{word.title()}\nGrelna  Tovish\n")
    stage_release(repo, "1.0.1", NO_CITATIONS)
    code, out = run(capsys)
    assert code == 1
    assert "README.md:3: denylist digest" in out
    assert "README.md:4: denylist digest" in out
    assert word not in out.lower() and "grelna" not in out.lower()


def test_a_digested_word_in_a_path_name_is_not_printed(repo, home, capsys):
    word = "flumphwick"
    digest = hashlib.sha256(word.encode()).hexdigest()
    (home / ".config/clean-release/terms/common.toml").write_text(
        f'sha256 = ["{digest}"]\n'
    )
    (repo / f"src/{word}.py").write_text("x = 1\n")
    (repo / "README.md").write_text(f"# repo\n\nsee src/{word}.py\n")
    stage_release(repo, "1.0.1", "[scan]\ncitations = true\n")
    code, out = run(capsys)
    assert code == 1
    assert "denylist digest" in out and "<tag path " in out
    assert word not in out.lower()


def test_a_term_in_a_path_name_fails(repo, capsys):
    (repo / f"src/{TERM}.py").write_text("x = 1\n")
    stage_release(repo, "1.0.1", NO_CITATIONS)
    code, out = run(capsys)
    assert code == 1
    assert f"src/{TERM}.py: denylist term\n" in out


def test_a_policy_changed_after_stage_fails(repo, capsys):
    append_policy(repo, NO_CITATIONS)
    stage(repo, "1.0.0")
    moved = POLICY.replace(', "run.sh"]', "]").replace(
        "exclude = [", 'exclude = ["run.sh", '
    )
    write_policy(repo, moved + NO_CITATIONS)
    code, out = run(capsys)
    assert code == 1
    assert "run.sh: staged but not shipped by the policy; re-run stage" in out


def test_no_staging_repo_refuses(repo, capsys):
    assert main(["check"]) == 1
    assert "run `clean-release stage" in capsys.readouterr().err


def test_a_home_path_fails(repo, capsys):
    (repo / "src/pkg/conf.py").write_text(f'P = "{os.sep}home{os.sep}alice/x"\n')
    stage_release(repo, "1.0.1", NO_CITATIONS)
    code, out = run(capsys)
    assert code == 1
    assert "src/pkg/conf.py:1: home path" in out


def test_emails_fail_except_identity_and_documentation(repo, home, capsys):
    me = "me" + "@" + "mydomain.dev"
    leak = "bob" + "@" + "corp.io"
    (home / ".config/clean-release/config.toml").write_text(
        f'[identity]\nname = "Me"\nemail = "{me}"\n\n'
        '[defaults]\nterms = ["~/.config/clean-release/terms/common.toml"]\n'
    )
    (repo / "src/pkg/who.py").write_text(
        f'A = "{me.upper()}"\nB = "x@example.org"\nC = "{leak}"\n'
    )
    stage_release(repo, "1.0.1", NO_CITATIONS)
    code, out = run(capsys)
    assert code == 1
    assert "src/pkg/who.py:3: email" in out
    assert "who.py:1" not in out and "who.py:2" not in out


def test_a_planted_secret_fails_without_printing_it(repo, capsys, monkeypatch):
    (repo / "src/pkg/conf.py").write_text(f'X = 1\nT = "{token()}"\n')
    stage_release(repo, "1.0.1", NO_CITATIONS)
    monkeypatch.setenv("BETTERLEAKS_CONFIG", str(repo / "no-such.toml"))
    code, out = run(capsys)
    assert code == 1
    assert "src/pkg/conf.py:2: secret (github-pat)" in out
    assert token() not in out


def test_a_missing_scanner_refuses_with_the_hint(repo, tmp_path, monkeypatch, capsys):
    path_without_scanners(tmp_path, monkeypatch)
    assert main(["check"]) == 1
    err = capsys.readouterr().err
    assert "`betterleaks` is not on PATH" in err
    assert "brew install betterleaks" in err
    assert "https://github.com/betterleaks/betterleaks" in err
    assert "secrets =" not in err


def test_a_missing_scanner_names_another_on_path(repo, tmp_path, monkeypatch, capsys):
    path_without_scanners(tmp_path, monkeypatch, "gitleaks")
    assert main(["check"]) == 1
    assert '`[scan] secrets = "gitleaks"`' in capsys.readouterr().err


def test_a_rewrite_edited_after_stage_fails(repo, capsys):
    (repo / "README.md").write_text("# repo\n\nold words\n")
    rule = (
        '[[rewrite]]\npath = "README.md"\npattern = "old"\nreplace = "{}"\nexpect = 1\n'
    )
    stage_release(repo, "1.0.1", NO_CITATIONS + rule.format("new"))
    text = (repo / "clean-release.toml").read_text()
    (repo / "clean-release.toml").write_text(
        text.replace('replace = "new"', 'replace = "newer"')
    )
    code, out = run(capsys)
    assert code == 1
    assert (
        "README.md: staged content differs from the policy's export; re-run stage"
        in out
    )


def test_lesson_9_a_missing_disclosure_document_fails(repo, capsys):
    (repo / "AI.md").write_text("# How this was written\n")
    named = POLICY.replace("[release]\n", '[release]\ndisclosure = "AI.md"\n')
    excluded = named.replace('exclude = ["docs/**"', 'exclude = ["AI.md", "docs/**"')
    write_policy(repo, excluded + NO_CITATIONS)
    stage_release(repo, "1.0.1")
    code, out = run(capsys)
    assert code == 1
    assert (
        "AI.md: the disclosure document named in [release] disclosure "
        "is not in the export; include it in [paths]\n"
    ) in out
    write_policy(repo, named.replace('"run.sh"]', '"run.sh", "AI.md"]') + NO_CITATIONS)
    stage(repo, "1.0.1")
    code, out = run(capsys)
    assert code == 0, out
