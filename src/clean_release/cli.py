"""The clean-release command line; the only module that prints."""

import argparse
import sys
from pathlib import Path

from clean_release import (
    Refusal,
    __version__,
    approve,
    check,
    commit,
    diff,
    doctor,
    git,
    scanner,
    stage,
    starter,
    status,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clean-release",
        description="Carry a private repo to its public twin, "
        "one checked snapshot commit per version.",
    )
    p.add_argument("-V", "--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    sub.add_parser(
        "init", help="write a starter clean-release.toml classifying every tracked path"
    )
    s = sub.add_parser(
        "stage", help="build VERSION's export from its tag into the staging repo"
    )
    s.add_argument(
        "version", metavar="VERSION", help="the release version, such as 1.2.0"
    )
    sub.add_parser("check", help="grade the staged export; nonzero on any finding")
    sub.add_parser(
        "diff",
        help="show the staged export against the public repo: new files, removed, "
        "binaries, check results, the identity, then the full diff",
    )
    sub.add_parser("approve", help="run check and, on a pass, approve the staged tree")
    sub.add_parser(
        "commit",
        help="commit the approved tree to the public repo, tag it, print the push",
    )
    sub.add_parser(
        "status",
        help="show the last public version, the staged version, whether it is "
        "approved, and whether the public tree is clean",
    )
    sub.add_parser(
        "doctor",
        help="check the machine config, the terms files, the scanner and the public tree",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    p = parser()
    args = p.parse_args(argv)
    if args.command is None:
        p.print_help()
        return 0
    try:
        root = git.toplevel(Path.cwd())
        if args.command == "init":
            file, doc, wrote = starter.init(root)
            print(f"wrote {file}")
            print(f"{'wrote' if wrote else 'kept'} {doc}")
            absent = scanner.missing(scanner.DEFAULT)
            if absent:
                print(absent)
        elif args.command == "check":
            return _check(root)
        elif args.command == "doctor":
            return _doctor(root)
        elif args.command == "approve":
            return _approve(root)
        elif args.command == "commit":
            return _commit(root)
        elif args.command == "diff":
            return _diff(root)
        elif args.command == "status":
            return _status(root)
        else:
            done = stage.stage(root, args.version)
            print(f"staged {args.version} in {done.path}")
            print(f"tree {done.tree}")
            print(f"{done.shipped} path(s) shipped, {done.excluded} excluded")
    except Refusal as e:
        print(f"clean-release: {e}", file=sys.stderr)
        return 1
    return 0


def _check(root: Path) -> int:
    return _report(check.check(root))


def _approve(root: Path) -> int:
    result, approved = approve.approve(root)
    code = _report(result)
    if approved is not None:
        print(f"approved {approved.version}: tree {approved.tree}")
    return code


def _commit(root: Path) -> int:
    done = commit.commit(root)
    print(f"committed {done.version} to {done.path}: {done.commit}, tag {done.tag}")
    if done.dirty:
        listing = "\n  ".join(done.dirty)
        print(
            f"clean-release: the public tree is not clean after the commit; "
            f"commit and tag {done.tag} were made, clear these:\n  {listing}",
            file=sys.stderr,
        )
    print("push it when ready:")
    for line in done.push:
        print(f"  {line}")
    return 1 if done.dirty else 0


def _diff(root: Path) -> int:
    """Print diff in the draft's order; exit as check does."""
    d = diff.diff(root)
    against = "no public release yet"
    if d.public_tree:
        against = f"{d.last or 'HEAD'} (tree {d.public_tree})"
    print(f"staged {d.version} (tree {d.tree}) against {d.public}: {against}")
    for name, paths in (
        ("new", d.new),
        ("removed", d.removed),
        ("binaries", d.binaries),
    ):
        print(f"{name}: {len(paths)}")
        for p in paths:
            print(f"  {p}")
    code = _report(d.result)
    who = f"{d.identity.name} <{d.identity.email}>"
    print(f"identity: {who} (author, committer and tagger)")
    print(d.text, end="")
    return code


def _status(root: Path) -> int:
    s = status.status(root)
    print(f"public: {s.public if s.public else 'not set'}")
    print(f"last public version: {s.last}")
    print(f"staged: {s.staged}")
    print(f"approved: {s.approved}")
    print(f"public tree: {s.tree}")
    for line in s.dirty:
        print(f"  {line}")
    return 0


def _report(result: check.Result) -> int:
    """Print check's result; 1 on any finding."""
    print(f"scanner: {result.scanner}")
    for command in result.commands:
        print(f"verify: `{command}`")
    for finding in result.findings:
        print(finding)
    for failed in result.outputs:
        print(f"{failed.finding}:\n{failed.output}", file=sys.stderr)
    if result.findings:
        print(f"{len(result.findings)} finding(s) in tree {result.tree}")
        return 1
    print(f"check passed: tree {result.tree}, {result.paths} path(s)")
    return 0


def _doctor(root: Path) -> int:
    notes = doctor.doctor(root)
    for note in notes:
        print(f"{'ok' if note.ok else 'problem'}: {note.text}")
    problems = sum(not n.ok for n in notes)
    if problems:
        print(f"doctor: {problems} problem(s)")
        return 1
    print("doctor: all ok")
    return 0
