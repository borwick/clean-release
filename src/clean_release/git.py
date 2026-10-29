"""git as a subprocess: run it, and read trees and blobs from a commit."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from clean_release import Refusal


def run(
    cwd: Path,
    *args: str,
    input: bytes | None = None,
    env: dict[str, str] | None = None,
) -> bytes:
    """Run `git -C cwd args`, returning stdout; a failure refuses with git's stderr."""
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        input=input,
        capture_output=True,
        check=False,
        env=None if env is None else os.environ | env,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace").strip()
        raise Refusal(f"git {' '.join(args)} failed in {cwd}: {err}")
    return proc.stdout


def ok(cwd: Path, *args: str) -> bool:
    """Whether `git -C cwd args` exits 0, its output discarded."""
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, check=False
    )
    return proc.returncode == 0


def toplevel(cwd: Path) -> Path:
    """The root of the git repo holding cwd; outside one, refuse."""
    if not ok(cwd, "rev-parse", "--show-toplevel"):
        raise Refusal(
            f"{cwd} is not in a git repo; run clean-release in the private repo"
        )
    return Path(run(cwd, "rev-parse", "--show-toplevel").decode().strip())


@dataclass(frozen=True)
class Entry:
    """One `git ls-tree -r` line: mode, type (blob or commit), object SHA, path."""

    mode: str
    type: str
    sha: str
    path: str


def ls_tree(root: Path, rev: str) -> list[Entry]:
    """Every entry of rev's tree, recursively, gitlinks kept."""
    out = run(root, "ls-tree", "-r", "-z", "--full-tree", rev)
    entries = []
    for record in out.decode().split("\0"):
        if record:
            meta, path = record.split("\t", 1)
            mode, kind, sha = meta.split(" ")
            entries.append(Entry(mode, kind, sha, path))
    return entries


def read_blobs(root: Path, shas: list[str]) -> dict[str, bytes]:
    """The content of each blob SHA, through one `git cat-file --batch`."""
    wanted = list(dict.fromkeys(shas))
    if not wanted:
        return {}
    out = run(
        root, "cat-file", "--batch", input="".join(f"{s}\n" for s in wanted).encode()
    )
    blobs, pos = {}, 0
    for sha in wanted:
        end = out.index(b"\n", pos)
        header = out[pos:end].decode().split(" ")
        if len(header) != 3:
            raise Refusal(f"git cat-file could not read {sha}: {' '.join(header)}")
        size = int(header[2])
        blobs[sha] = out[end + 1 : end + 1 + size]
        pos = end + 1 + size + 1
    return blobs


def write_tree(repo: Path, entries: list[Entry], files: dict[str, bytes]) -> str:
    """Write each blob and a tree of entries into repo's objects; return the tree SHA.

    Built in a scratch index, so modes are kept and no `.gitignore` drops a file.
    """
    lines = []
    for e in entries:
        sha = e.sha
        if e.type == "blob":
            sha = run(repo, "hash-object", "-w", "--stdin", input=files[e.path])
            sha = sha.decode().strip()
        lines.append(f"{e.mode} {sha}\t{e.path}\0")
    git_dir = Path(run(repo, "rev-parse", "--absolute-git-dir").decode().strip())
    index = git_dir / "clean-release-write.index"
    index.unlink(missing_ok=True)
    env = {"GIT_INDEX_FILE": str(index)}
    try:
        run(
            repo,
            "update-index",
            "-z",
            "--index-info",
            input="".join(lines).encode(),
            env=env,
        )
        return run(repo, "write-tree", env=env).decode().strip()
    finally:
        index.unlink(missing_ok=True)
