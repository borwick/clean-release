"""`clean-release.toml`: load and validate it, and classify paths.

The file is read from the private repo's working tree, never from a tag:
the tag's name comes from it. The schema is
`docs/data-structures/POLICY.md`.
"""

import re
import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from clean_release import Refusal, scan, scanner, tables

FILENAME = "clean-release.toml"

# Matched at any depth, except local/, a roots root directory.
NEVER_SHIP = (
    "**/CLAUDE.md",
    "**/.claude/**",
    "**/.env*",
    "**/IDEAS.md",
    "**/*.org",
    "**/clean-release.toml",
    "local/**",
)

TABLES = {"release", "paths", "rewrite", "scan", "verify"}
RELEASE_KEYS = {"tag", "message", "public", "unclassified", "disclosure"}
PATHS_KEYS = {"include", "exclude"}
REWRITE_KEYS = {"path", "pattern", "replace", "expect"}
SCAN_KEYS = {"patterns", "binaries", "citations", "citable", "secrets"}
VERIFY_KEYS = {"commands"}


@dataclass(frozen=True)
class Rewrite:
    """One `[[rewrite]]` rule: `pattern` must match `expect` times in `path`."""

    path: str
    pattern: re.Pattern[str]
    replace: str
    expect: int


@dataclass(frozen=True)
class Scan:
    """`[scan]`; each key is in `docs/data-structures/POLICY.md`."""

    patterns: tuple[str, ...] = tuple(scan.PATTERNS)
    binaries: tuple[str, ...] = ()
    citations: bool = True
    citable: tuple[str, ...] = ()
    secrets: str = scanner.DEFAULT


@dataclass(frozen=True)
class Verify:
    """`[verify]`: the commands run, in order, in a copy of the export."""

    commands: tuple[str, ...] = ()


@dataclass(frozen=True)
class Policy:
    """A validated `clean-release.toml`."""

    tag: str
    message: str
    public: str | None
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    rewrites: tuple[Rewrite, ...]
    scan: Scan
    verify: Verify
    disclosure: str | None = None


def matches(path: str, globs: tuple[str, ...]) -> bool:
    """Whether any glob matches the whole path."""
    return any(PurePosixPath(path).full_match(g) for g in globs)


def never_ships(path: str) -> bool:
    """Whether the built-in never-ship list holds path."""
    return matches(path, NEVER_SHIP)


def classify(policy: Policy, paths: list[str]) -> tuple[list[str], list[str]]:
    """Split paths into (shipped, excluded); any unclassified path refuses, all named."""
    shipped, excluded, unclassified = [], [], []
    for path in paths:
        if never_ships(path) or matches(path, policy.exclude):
            excluded.append(path)
        elif matches(path, policy.include):
            shipped.append(path)
        else:
            unclassified.append(path)
    if unclassified:
        listing = "\n  ".join(unclassified)
        raise Refusal(
            f"{len(unclassified)} path(s) match neither include nor exclude in "
            f"{FILENAME}; add each to [paths]:\n  {listing}"
        )
    return shipped, excluded


def load(root: Path) -> Policy:
    """Read `<root>/clean-release.toml`; a missing or invalid file refuses by name."""
    file = root / FILENAME
    data = tables.read(file, "run `clean-release init`")
    _known(data, TABLES, FILENAME)
    release = _table(data, "release")
    _known(release, RELEASE_KEYS, "[release]")
    paths = _table(data, "paths")
    _known(paths, PATHS_KEYS, "[paths]")

    tag = _string(release, "tag", "[release]", default="v{version}")
    if "{version}" not in tag:
        raise Refusal(
            f'[release] tag = "{tag}" must contain {{version}}, as "v{{version}}"'
        )
    unclassified = _string(release, "unclassified", "[release]", default="error")
    if unclassified != "error":
        raise Refusal(
            f'[release] unclassified = "{unclassified}"; the only value is "error"'
        )

    return Policy(
        tag=tag,
        message=_string(release, "message", "[release]"),
        public=_string(release, "public", "[release]", default=None),
        include=tuple(tables.strings(paths, "include", "[paths]")),
        exclude=tuple(tables.strings(paths, "exclude", "[paths]")),
        rewrites=_rewrites(data.get("rewrite", [])),
        scan=_scan(_table(data, "scan")),
        verify=_verify(_table(data, "verify")),
        disclosure=_string(release, "disclosure", "[release]", default=None),
    )


def _scan(table: dict) -> Scan:
    _known(table, SCAN_KEYS, "[scan]")
    names = Scan.patterns
    if "patterns" in table:
        names = tuple(tables.strings(table, "patterns", "[scan]"))
    unknown = sorted(set(names) - set(scan.PATTERNS))
    if unknown:
        raise Refusal(
            f"[scan] patterns has unknown name(s) {', '.join(unknown)}; "
            f"the names are {', '.join(scan.PATTERNS)}"
        )
    citations = table.get("citations", True)
    if not isinstance(citations, bool):
        raise Refusal(f"[scan] citations = {citations!r} must be true or false")
    secrets = table.get("secrets", scanner.DEFAULT)
    if not isinstance(secrets, str) or secrets not in scanner.SCANNERS:
        raise Refusal(
            f"[scan] secrets = {secrets!r}; the scanners are "
            f"{', '.join(scanner.SCANNERS)}"
        )
    return Scan(
        patterns=names,
        binaries=tuple(tables.strings(table, "binaries", "[scan]")),
        citations=citations,
        citable=tuple(tables.strings(table, "citable", "[scan]")),
        secrets=secrets,
    )


def _verify(table: dict) -> Verify:
    _known(table, VERIFY_KEYS, "[verify]")
    commands = tables.strings(table, "commands", "[verify]")
    for cmd in commands:
        try:
            argv = shlex.split(cmd)
        except ValueError as e:
            raise Refusal(f"[verify] command {cmd!r} does not parse: {e}") from None
        if not argv:
            raise Refusal(f"[verify] command {cmd!r} is empty; name a program")
    return Verify(tuple(commands))


def _rewrites(rules: object) -> tuple[Rewrite, ...]:
    if not isinstance(rules, list) or not all(isinstance(r, dict) for r in rules):
        raise Refusal("rewrite must be an array of tables, each written [[rewrite]]")
    out = []
    for i, rule in enumerate(rules, 1):
        where = f"[[rewrite]] {i}"
        _known(rule, REWRITE_KEYS, where)
        expect = rule.get("expect")
        if isinstance(expect, bool) or not isinstance(expect, int) or expect < 1:
            raise Refusal(
                f"{where}: expect = {expect!r}; it must be the number of matches, 1 or more"
            )
        pattern = _string(rule, "pattern", where)
        try:
            compiled = re.compile(pattern)
        except re.error as e:
            raise Refusal(
                f"{where}: pattern {pattern!r} does not compile: {e}"
            ) from None
        out.append(
            Rewrite(
                _string(rule, "path", where),
                compiled,
                _string(rule, "replace", where),
                expect,
            )
        )
    return tuple(out)


def _known(table: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise Refusal(
            f"{where} has unknown key(s) {', '.join(unknown)}; "
            f"the keys are {', '.join(sorted(allowed))}"
        )


def _table(data: dict, key: str) -> dict:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise Refusal(f"{key} in {FILENAME} must be a table, written [{key}]")
    return value


_REQUIRED = object()


def _string(table: dict, key: str, where: str, default: object = _REQUIRED):
    if key not in table:
        if default is _REQUIRED:
            raise Refusal(f"{where} needs {key}, a string")
        return default
    value = table[key]
    if not isinstance(value, str):
        raise Refusal(f"{where} {key} = {value!r} must be a string")
    return value
