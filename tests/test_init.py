import tomllib

import pytest

from clean_release import policy
from clean_release.cli import main
from clean_release.starter import DISCLOSURE, LINKS, excludes, render
from tests.conftest import commit_all, path_without_scanners


@pytest.fixture
def fresh(repo):
    """The fixture repo without its uncommitted policy file."""
    (repo / "clean-release.toml").unlink()
    return repo


def test_lesson_6_init_carries_a_links_rewrite(fresh):
    (fresh / "README.md").write_text(
        "[a](docs/a.md) [b](LICENSE) [c](https://x.example) [d](#top) [e](mailto:x@y.z)\n"
    )
    commit_all(fresh, "readme")
    assert main(["init"]) == 0
    data = tomllib.loads((fresh / "clean-release.toml").read_text())
    assert data["rewrite"] == [
        {
            "path": "README.md",
            "pattern": LINKS,
            "replace": "](https://github.com/OWNER/REPO/blob/main/\\g<target>)",
            "expect": 2,
        }
    ]


def test_starter_classifies_every_path(fresh):
    (fresh / "sub").mkdir()
    (fresh / "sub/CLAUDE.md").write_text("rules\n")
    (fresh / ".claude").mkdir()
    (fresh / ".claude/other.json").write_text("{}\n")
    commit_all(fresh, "agent files")
    assert main(["init"]) == 0
    data = tomllib.loads((fresh / "clean-release.toml").read_text())
    assert data["release"] == {
        "tag": "v{version}",
        "message": "repo {version}",
        "unclassified": "error",
        "disclosure": "docs/ai-disclosure.md",
    }
    assert data["paths"] == {
        "include": [],
        "exclude": [".gitignore", "README.md", "docs/**", "run.sh", "src/**"],
    }
    assert data["scan"] == {
        "patterns": ["home-paths", "emails"],
        "binaries": [],
        "citations": True,
        "citable": [],
        "secrets": "betterleaks",
    }
    assert data["verify"] == {"commands": []}
    loaded = policy.load(fresh)
    assert loaded.scan == policy.Scan() and loaded.verify == policy.Verify()


def test_no_relative_links_writes_no_rule():
    text = render("r", ["README.md"], "see [x](https://x.example)\n")
    data = tomllib.loads(text)
    assert "rewrite" not in data
    assert "no relative links" in text


def test_strings_round_trip():
    odd = 'quote" back\\ tab\t del\x7f emoji \U0001f600'
    assert (
        tomllib.loads(render(odd, [], None))["release"]["message"] == odd + " {version}"
    )


def test_existing_policy_refuses(repo, capsys):
    assert main(["init"]) == 1
    assert "already exists" in capsys.readouterr().err


def test_init_without_the_scanner_prints_the_hint(fresh, tmp_path, monkeypatch, capsys):
    path_without_scanners(tmp_path, monkeypatch)
    assert main(["init"]) == 0
    out = capsys.readouterr().out
    assert "wrote " in out and "brew install betterleaks" in out


def test_excludes_escape_glob_characters():
    paths = ["a[b].md", "x*y/z.txt", "plain.txt"]
    globs = excludes(paths)
    assert globs == ["a[[]b].md", "plain.txt", "x[*]y/**"]
    assert policy.matches("a[b].md", globs) and not policy.matches("ab.md", globs)


def test_init_writes_the_disclosure_document(fresh, capsys):
    assert main(["init"]) == 0
    doc = fresh / DISCLOSURE
    assert f"wrote {doc}" in capsys.readouterr().out
    text = doc.read_text()
    assert "`repo` was written with Claude Code" in text
    assert "OWNER" in text and "MODELS" in text and "Co-Authored-By" in text
    assert "@" not in text and "LICENSE" not in text
    assert policy.load(fresh).disclosure == DISCLOSURE


def test_init_keeps_an_existing_disclosure_document(fresh, capsys):
    mine = b"# Mine\r\n\nwritten by hand\n"
    (fresh / DISCLOSURE).write_bytes(mine)
    assert main(["init"]) == 0
    assert f"kept {fresh / DISCLOSURE}" in capsys.readouterr().out
    assert (fresh / DISCLOSURE).read_bytes() == mine
