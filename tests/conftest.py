"""A private repo in tmp_path, tagged v1.0.0, with HOME and the machine config of its own.

The terms file holds a made-up term, `TERM`. `public` adds an empty public
directory the machine config names, and `release` carries a version to it.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from clean_release.cli import main
from clean_release.stage import stage

TERM = "zorblax-quintavane"


def git(cwd: Path, *args: str) -> str:
    """Run git in cwd as a test identity; return stdout."""
    return subprocess.run(
        [
            "git",
            "-C",
            str(cwd),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.org",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def commit_all(root: Path, message: str = "commit") -> None:
    git(root, "add", "-A")
    git(root, "commit", "-q", "--no-gpg-sign", "-m", message)


def write_policy(root: Path, body: str) -> None:
    (root / "clean-release.toml").write_text(body)


def append_policy(root: Path, body: str) -> None:
    write_policy(root, (root / "clean-release.toml").read_text() + "\n" + body)


POLICY = """\
[release]
message = "repo {version}"

[paths]
include = ["src/**", "README.md", "run.sh"]
exclude = ["docs/**", ".gitignore"]
"""


@pytest.fixture
def home(tmp_path, monkeypatch):
    """HOME in tmp_path, holding a machine config whose defaults list one terms file."""
    home = tmp_path / "home"
    conf = home / ".config/clean-release"
    (conf / "terms").mkdir(parents=True)
    (conf / "terms/common.toml").write_text(f'plain = ["{TERM}"]\n')
    (conf / "config.toml").write_text(
        '[identity]\nname = "Stager"\nemail = "stager@example.org"\n\n'
        '[defaults]\nterms = ["~/.config/clean-release/terms/common.toml"]\n'
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    return home


@pytest.fixture
def repo(tmp_path, home, monkeypatch):
    """A private repo named `repo`, tagged v1.0.0, the cwd, with POLICY in its working tree."""
    root = tmp_path / "repo"
    (root / "src/pkg").mkdir(parents=True)
    (root / "docs").mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / ".gitignore").write_text("local/\n")
    (root / "README.md").write_text("# repo\n\nSee [the guide](docs/guide.md).\n")
    (root / "src/pkg/__init__.py").write_text("VALUE = 1\n")
    (root / "docs/guide.md").write_text("private notes\n")
    (root / "run.sh").write_text("#!/bin/sh\necho hi\n")
    (root / "run.sh").chmod(0o755)
    commit_all(root, "first")
    git(root, "tag", "v1.0.0")
    write_policy(root, POLICY)
    monkeypatch.chdir(root)
    return root


def path_without_scanners(tmp_path: Path, monkeypatch, *fakes: str) -> None:
    """PATH holding only git and an always-passing script for each name in fakes."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").symlink_to(shutil.which("git"))
    for name in fakes:
        (bin_dir / name).write_text("#!/bin/sh\nexit 0\n")
        (bin_dir / name).chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))


def token() -> str:
    """A made-up GitHub token, built here so no literal one lands in the repo.

    Joined, not `+`: Python folds `"a" + "b"` into one constant in the `.pyc`,
    and a scanner over `tests/` finds it there.
    """
    return "_".join(("ghp", "Zq7Xw2Lp9Rt4" * 3))


@pytest.fixture
def public(repo, home, tmp_path):
    """An empty public directory named by the machine config; citations off."""
    path = tmp_path / "public"
    path.mkdir()
    name_public(home, path)
    append_policy(repo, "[scan]\ncitations = false\n")
    return path


def name_public(home, path):
    config = home / ".config/clean-release/config.toml"
    config.write_text(config.read_text() + f'\n[repos.repo]\npublic = "{path}"\n')


def tag(repo, version, text=None):
    """Commit a README change, if any, and tag it."""
    (repo / "README.md").write_text(text or f"# repo {version}\n")
    commit_all(repo, version)
    git(repo, "tag", f"v{version}")


def staged_and_approved(repo, version, capsys):
    stage(repo, version)
    assert main(["approve"]) == 0, capsys.readouterr()
    capsys.readouterr()


def release(repo, version, capsys):
    """Stage, approve and commit version; return the exit code, stdout and stderr."""
    staged_and_approved(repo, version, capsys)
    code = main(["commit"])
    out = capsys.readouterr()
    return code, out.out, out.err
