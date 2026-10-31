"""The text graders: denylist terms and digests, and the generic patterns.

Pure functions over a path and its text, each returning findings. A
finding never carries the text it matched, so a hidden term cannot reach
a terminal or a session transcript.
"""

import hashlib
import itertools
import re
from dataclasses import dataclass

from clean_release.machine import Terms


@dataclass(frozen=True)
class Finding:
    """A leak in the export: where, and what kind; line is None for a whole path."""

    path: str
    line: int | None
    kind: str

    def __str__(self) -> str:
        at = self.path if self.line is None else f"{self.path}:{self.line}"
        return f"{at}: {self.kind}"


WORD = re.compile(r"[^\W_]+")
DOC_DOMAINS = ("example.com", "example.org", "example.net")
DOC_TLDS = ("example", "test", "invalid", "localhost")
PATTERNS = {
    "home-paths": re.compile(
        r"""(?x)
        /(?:Users|home)/(?!you\b)[A-Za-z0-9._-]+  # a POSIX home, bar the docs' /home/you
        | [A-Za-z]:\\Users\\[A-Za-z0-9._-]+       # a Windows home
        """
    ),
    "emails": re.compile(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
    ),
}
KINDS = {"home-paths": "home path", "emails": "email"}


def line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def digest(candidate: str) -> str:
    """The sha256 hex digest a terms file lists for candidate."""
    return hashlib.sha256(candidate.encode()).hexdigest()


def terms(path: str, text: str, denylist: Terms, where: str = "") -> list[Finding]:
    """Plain terms as case-insensitive substrings, digests over words and word pairs."""
    found = []
    low = text.lower()
    for term in denylist.plain:
        pos = low.find(term)
        while pos != -1:
            found.append(Finding(path, line(low, pos), f"denylist term{where}"))
            pos = low.find(term, pos + 1)
    for pos in _digest_hits(text, denylist.sha256):
        found.append(Finding(path, line(text, pos), f"denylist digest{where}"))
    return found


def digested(text: str, denylist: Terms) -> bool:
    """Whether text holds a word or word pair whose digest the denylist lists."""
    return bool(_digest_hits(text, denylist.sha256))


def digests_in(text: str) -> set[str]:
    """The digest of every word and word pair in text."""
    return {digest(c) for _, c in _candidates(text)}


def _digest_hits(text: str, sha256: frozenset[str]) -> list[int]:
    if not sha256:
        return []
    return [pos for pos, c in _candidates(text) if digest(c) in sha256]


def _candidates(text: str) -> list[tuple[int, str]]:
    words = [(m.start(), m.group().lower()) for m in WORD.finditer(text)]
    pairs = [(a[0], f"{a[1]} {b[1]}") for a, b in itertools.pairwise(words)]
    return words + pairs


def allowed_email(address: str, identity: str) -> bool:
    """Whether address is a documentation address, a noreply, or the identity's."""
    local, _, domain = address.lower().rpartition("@")
    return (
        address.lower() == identity.lower()
        or local == "noreply"
        or any(domain == d or domain.endswith("." + d) for d in DOC_DOMAINS)
        or domain.rsplit(".", 1)[-1] in DOC_TLDS
    )


def patterns(
    path: str, text: str, names: tuple[str, ...], identity: str
) -> list[Finding]:
    """The named generic patterns; identity is the email the machine config allows."""
    found = []
    for name in names:
        for m in PATTERNS[name].finditer(text):
            if name == "emails" and allowed_email(m.group(), identity):
                continue
            found.append(Finding(path, line(text, m.start()), KINDS[name]))
    return found
