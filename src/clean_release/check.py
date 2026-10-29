"""`check`: grade the staged tree, the staging repo's `HEAD^{tree}`, read from objects.

The current policy rebuilds the tag's export, and any path, mode or
content the stage holds differently is a finding; the text graders run over
every staged blob and path, the denylist also over each rewrite's source
at the tag, and the refusals and the citations check over the tree. Then
the secrets scanner and `[verify]` run in a temporary copy of the tree.
"""

import os
import posixpath
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from clean_release import Refusal, git, machine, policy, scan, scanner, stage, verify
from clean_release.git import Entry
from clean_release.scan import Finding

LFS = b"version https://git-lfs.github.com/spec/"
LINK = re.compile(r"\]\(([^)\s]+)")


@dataclass(frozen=True)
class Result:
    """The tree graded, its path count, every finding sorted, failed commands' output,
    and what ran in the copy: the scanner with its version, each `[verify]` command."""

    tree: str
    paths: int
    findings: list[Finding]
    outputs: tuple[verify.Failed, ...] = ()
    scanner: str = ""
    commands: tuple[str, ...] = ()


def check(root: Path) -> Result:
    """Grade the private repo at root's last stage."""
    pol = policy.load(root)
    absent = scanner.missing(pol.scan.secrets)
    if absent:
        raise Refusal(absent)
    mach = machine.load(root.name)
    head = stage.staged(root)
    entries = git.ls_tree(head.path, "HEAD")
    blobs = git.read_blobs(head.path, [e.sha for e in entries if e.type == "blob"])
    want = stage.build(root, pol, head.tag)
    at_tag = want.at_tag
    shipped = [e.path for e in want.entries]

    found = _drift(want, entries, blobs)
    found += _whole(policy.FILENAME, pol.message, mach.terms, " in [release] message")
    found += _rewrite_sources(root, pol, at_tag, mach.terms)
    found += _disclosure(pol.disclosure, entries)
    texts = {}
    for e in entries:
        found += _whole(e.path, e.path, mach.terms)
        if e.mode == "160000":
            found.append(Finding(e.path, None, "submodule"))
            continue
        data = blobs[e.sha]
        text = data.decode("utf-8", errors="replace")
        found += scan.terms(e.path, text, mach.terms)
        found += scan.patterns(e.path, text, pol.scan.patterns, mach.identity.email)
        if e.mode == "120000":
            if _outside(e.path, text):
                found.append(Finding(e.path, None, "symlink out of the tree"))
        elif data.startswith(LFS):
            found.append(Finding(e.path, None, "LFS pointer"))
        elif b"\0" in data[:8000]:
            if not policy.matches(e.path, pol.scan.binaries):
                found.append(Finding(e.path, None, "binary not in [scan] binaries"))
        else:
            texts[e.path] = text
    if pol.scan.citations:
        tag_paths = [e.path for e in at_tag]
        found += _citations(tag_paths, shipped, texts, pol.scan.citable)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "export"
        _copy(entries, blobs, copy)
        found += scanner.scan(pol.scan.secrets, copy)
        failed = verify.run(pol.verify.commands, copy)
    found += [f.finding for f in failed]
    hidden = {
        p: f"<tag path {i}>"
        for i, p in enumerate((e.path for e in at_tag), 1)
        if scan.digested(p, mach.terms)
    }
    found = [_redact(f, hidden) for f in found]
    return Result(
        head.tree,
        len(entries),
        sorted(set(found), key=_order),
        tuple(failed),
        scanner.version(pol.scan.secrets),
        pol.verify.commands,
    )


def _redact(f: Finding, hidden: dict[str, str]) -> Finding:
    """f with each path that holds a digested word replaced by its place at the tag."""
    path, kind = hidden.get(f.path, f.path), f.kind
    for name, mark in hidden.items():
        kind = kind.replace(name, mark)
    return Finding(path, f.line, kind)


def _copy(entries: list[Entry], blobs: dict[str, bytes], dest: Path) -> None:
    """Write the tree as files under dest: modes kept, gitlinks skipped."""
    dest.mkdir()
    for e in entries:
        if e.mode == "160000":
            continue
        file = dest / e.path
        file.parent.mkdir(parents=True, exist_ok=True)
        if e.mode == "120000":
            os.symlink(os.fsdecode(blobs[e.sha]), file)
        else:
            file.write_bytes(blobs[e.sha])
            file.chmod(0o755 if e.mode == "100755" else 0o644)


def _whole(path: str, text: str, terms: machine.Terms, where: str = "") -> list:
    """The denylist over text that is not a file, such as a path name: no line."""
    return [Finding(path, None, f.kind) for f in scan.terms(path, text, terms, where)]


def _order(f: Finding) -> tuple:
    return (f.path, f.line or 0, f.kind)


def _drift(
    want: stage.Export, entries: list[Entry], blobs: dict[str, bytes]
) -> list[Finding]:
    """A staged tree that no longer matches the current policy's export of the tag."""
    staged = {e.path: e for e in entries}
    out = [
        Finding(p, None, "staged but not shipped by the policy; re-run stage")
        for p in staged.keys() - {e.path for e in want.entries}
    ]
    for e in want.entries:
        got = staged.get(e.path)
        if got is None:
            kind = "shipped by the policy but not staged; re-run stage"
        elif got.mode != e.mode or (
            want.files[e.path] != blobs[got.sha]
            if e.type == "blob"
            else got.sha != e.sha
        ):
            kind = "staged content differs from the policy's export; re-run stage"
        else:
            continue
        out.append(Finding(e.path, None, kind))
    return out


def _disclosure(path: str | None, entries: list[Entry]) -> list[Finding]:
    """Lesson 9: the document `[release] disclosure` names must ship as a regular file."""
    if path is None or any(
        e.path == path and e.mode in ("100644", "100755") for e in entries
    ):
        return []
    return [
        Finding(
            path,
            None,
            "the disclosure document named in [release] disclosure is not in "
            "the export; include it in [paths]",
        )
    ]


def _rewrite_sources(
    root: Path, pol: policy.Policy, at_tag: list[Entry], terms: machine.Terms
) -> list[Finding]:
    """The denylist over each rewritten path's blob at the tag, before the rewrite."""
    shas = {e.path: e.sha for e in at_tag if e.type == "blob"}
    paths = [r.path for r in pol.rewrites if r.path in shas]
    blobs = git.read_blobs(root, [shas[p] for p in paths])
    found = []
    for path in dict.fromkeys(paths):
        text = blobs[shas[path]].decode("utf-8", errors="replace")
        found += scan.terms(path, text, terms, " in the rewrite source")
    return found


def _outside(path: str, target: str) -> bool:
    """Whether a symlink at path with target points out of the tree."""
    if target.startswith("/"):
        return True
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
    return resolved == ".." or resolved.startswith("../")


def _citations(
    tag_paths: list[str],
    shipped: list[str],
    texts: dict[str, str],
    citable: tuple[str, ...],
) -> list[Finding]:
    """Shipped text naming a path or directory that did not ship, unless citable.

    A file is citable when a glob matches it, a directory when every tag
    path under it is citable; `full_match` alone would not match `docs/`.
    """
    kept = set(shipped)
    files = {p for p in tag_paths if p not in kept}
    dirs = {d for p in tag_paths for d in _parents(p)}
    dirs -= {d for p in shipped for d in _parents(p)}
    allowed = {p for p in files if policy.matches(p, citable)}
    files -= allowed
    dirs = {d for d in dirs if any(p.startswith(d + "/") for p in files)}
    if not files and not dirs:
        return []
    names = sorted(files, key=len, reverse=True)
    names += [d + "/" for d in sorted(dirs, key=len, reverse=True)]
    bare = re.compile(
        r"(?<![\w./-])(" + "|".join(map(re.escape, names)) + r")(?![\w/-])"
    )
    found = []
    for path, text in texts.items():
        for m in bare.finditer(text):
            found.append(_cites(path, text, m.start(), m[1]))
        for m in LINK.finditer(text):
            target = _resolve(path, m[1])
            if target in files or target in dirs:
                found.append(_cites(path, text, m.start(), target))
    return found


def _cites(path: str, text: str, pos: int, cited: str) -> Finding:
    return Finding(path, scan.line(text, pos), f"cites {cited} which did not ship")


def _parents(path: str) -> list[str]:
    parts = path.split("/")[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def _resolve(citer: str, target: str) -> str | None:
    """A link target as a repo path, relative to the citing file; None if external."""
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target):
        return None
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    joined = posixpath.join(posixpath.dirname(citer), target)
    return posixpath.normpath(joined)
