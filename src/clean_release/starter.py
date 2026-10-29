"""`init`: write a starter `clean-release.toml` that classifies every tracked path.

Every top-level entry at HEAD is excluded until the owner moves it to
`include`. A README with relative links gets a rewrite making them
absolute (lesson 6: relative links 404 on PyPI). `[release] disclosure`
names a starter disclosure document, written to `docs/ai-disclosure.md` when absent
(lesson 9: the squash drops the `Co-Authored-By` trailers).
"""

import glob
import json
import re
from pathlib import Path

from clean_release import Refusal, git, policy

README = "README.md"
LINKS = r"\]\((?!https?://|#|mailto:)([^)]+)\)"
LINKS_REPLACE = r"](https://github.com/OWNER/REPO/blob/main/\1)"
DISCLOSURE = "docs/ai-disclosure.md"

# Modeled on fileplan's own; OWNER, MODELS and the level are the owner's to set.
# It cites no path and holds no address, so it passes `check` as written.
DISCLOSURE_TEXT = """\
# How this was written

`REPO` was written with Claude Code.

## the level

**AI-generated with human prompting and review.** That is one of the four
levels in the W3C AI content disclosure vocabulary. Change it if another
fits better.

## who did what

OWNER directed the work, made the design calls, and reviewed every change
before it landed. Claude Code wrote the code, the tests and the documents.
The models were MODELS.

## why the git history does not say it

Claude Code writes a `Co-Authored-By` trailer into each commit it makes.
The public history is one snapshot commit per release, squashed from the
private one, and those trailers did not survive it. This page is where that
record lives now.

## no endorsement

Anthropic did not build `REPO`, does not sponsor it, and does not endorse
it. Claude Code is Anthropic's tool, and it was used here the way any tool
is used.
"""


def toml_string(s: str) -> str:
    """s as a TOML basic string: JSON's escapes are TOML's, bar DEL."""
    return json.dumps(s, ensure_ascii=False).replace("\x7f", "\\u007f")


def tracked(root: Path) -> list[str]:
    """Every path tracked at HEAD."""
    if not git.ok(root, "rev-parse", "--verify", "-q", "HEAD"):
        raise Refusal(
            f"{root} has no commits; commit first, then run `clean-release init`"
        )
    out = git.run(root, "ls-tree", "-r", "-z", "--name-only", "--full-tree", "HEAD")
    return [p for p in out.decode().split("\0") if p]


def excludes(paths: list[str]) -> list[str]:
    """One glob per top-level entry, its name escaped, leaving out those wholly
    on the never-ship list."""
    tops: dict[str, list[str]] = {}
    for path in paths:
        tops.setdefault(path.split("/", 1)[0], []).append(path)
    out = []
    for top, under in sorted(tops.items()):
        if all(policy.never_ships(p) for p in under):
            continue
        name = glob.escape(top)
        out.append(name if under == [top] else f"{name}/**")
    return out


def render(repo: str, paths: list[str], readme: str | None) -> str:
    """The starter policy's text."""
    lines = [
        "# clean-release policy; docs/data-structures/POLICY.md in clean-release.",
        "# Every path starts excluded: move what ships to include.",
        "",
        "[release]",
        'tag = "v{version}"',
        f"message = {toml_string(repo + ' {version}')}",
        'unclassified = "error"',
        "# The AI disclosure document: edit it, commit it, and include it in",
        "# [paths]; `check` fails a release without it.",
        f"disclosure = {toml_string(DISCLOSURE)}",
        "",
        "[paths]",
        "include = []",
        "exclude = [",
        *(f"    {toml_string(g)}," for g in excludes(paths)),
        "]",
        "",
        "[scan]",
        "# Generic patterns graded on every shipped file.",
        'patterns = ["home-paths", "emails"]',
        "# Globs of the binary files allowed to ship.",
        "binaries = []",
        "# Fail a shipped file that names a path that did not ship.",
        "citations = true",
        '# Globs of unshipped paths a shipped file may name, such as ["clean-release.toml"].',
        "citable = []",
        '# The secrets scanner on PATH: "betterleaks" or "gitleaks".',
        'secrets = "betterleaks"',
        "",
        "[verify]",
        '# Run in a copy of the export, such as ["uv run --locked pytest -q"].',
        "commands = []",
    ]
    if readme is not None:
        count = len(re.findall(LINKS, readme))
        if count:
            lines += [
                "",
                "# Relative links 404 on PyPI: make them absolute.",
                "# Set OWNER/REPO to the public repo's URL.",
                "[[rewrite]]",
                f"path = {toml_string(README)}",
                f"pattern = '{LINKS}'",
                f"replace = '{LINKS_REPLACE}'",
                f"expect = {count}",
            ]
        else:
            lines += ["", f"# {README} has no relative links, so no rewrite is needed."]
    return "\n".join(lines) + "\n"


def init(root: Path) -> tuple[Path, Path, bool]:
    """Write `<root>/clean-release.toml`, an existing file refusing, then the
    disclosure document when absent; return both paths and whether it was written."""
    paths = tracked(root)
    readme = None
    if README in paths:
        blob = git.run(root, "cat-file", "blob", f"HEAD:{README}")
        readme = blob.decode("utf-8", errors="replace")
    text = render(root.name, paths, readme)
    file = root / policy.FILENAME
    try:
        with file.open("x", encoding="utf-8") as f:
            f.write(text)
    except FileExistsError:
        raise Refusal(
            f"{file} already exists; edit it, or move it aside to start again"
        ) from None
    doc = root / DISCLOSURE
    doc.parent.mkdir(parents=True, exist_ok=True)
    try:
        with doc.open("x", encoding="utf-8") as f:
            f.write(DISCLOSURE_TEXT.replace("REPO", root.name))
    except FileExistsError:
        return file, doc, False
    return file, doc, True
