"""The machine config, `~/.config/clean-release/config.toml`, and its terms files.

A repo with no terms file fails closed unless `[repos.<name>]` says `terms = []`. The schema
is `docs/data-structures/MACHINE-CONFIG.md`.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from clean_release import Refusal, tables

SHA256 = re.compile(r"[0-9a-f]{64}")
TERMS_KEYS = {"plain", "sha256"}


@dataclass(frozen=True)
class Identity:
    """Author, committer and tagger of every commit and tag clean-release makes."""

    name: str
    email: str

    def env(self) -> dict[str, str]:
        """The environment that makes git author, commit and tag as this identity."""
        return {
            "GIT_AUTHOR_NAME": self.name,
            "GIT_AUTHOR_EMAIL": self.email,
            "GIT_COMMITTER_NAME": self.name,
            "GIT_COMMITTER_EMAIL": self.email,
        }


@dataclass(frozen=True)
class Terms:
    """The denylist: plain terms lowercased, and sha256 digests of hidden ones."""

    plain: tuple[str, ...]
    sha256: frozenset[str]


@dataclass(frozen=True)
class Machine:
    """What the machine config says for one repo, and the terms files it read."""

    identity: Identity
    public: str | None
    terms: Terms
    terms_files: tuple[Path, ...] = ()


def config_path() -> Path:
    """Where the machine config lives; tests move it by setting HOME."""
    return Path.home() / ".config/clean-release/config.toml"


def load(repo: str) -> Machine:
    """Read the machine config for the repo named repo; anything missing refuses."""
    file = config_path()
    data = tables.read(file, f"write it with [identity] and [repos.{repo}] terms")
    identity = data.get("identity")
    if not isinstance(identity, dict) or not all(
        isinstance(identity.get(k), str) and identity[k] for k in ("name", "email")
    ):
        raise Refusal(f'{file} needs [identity] with name = "..." and email = "..."')

    section = data.get("repos", {}).get(repo, {})
    defaults = data.get("defaults", {})
    files = tables.strings(defaults, "terms", f"{file} [defaults]")
    files += tables.strings(section, "terms", f"{file} [repos.{repo}]")
    if not files and section.get("terms") != []:
        raise Refusal(
            f"{file} lists no terms file for {repo}: add [repos.{repo}] terms = "
            f'["<path>"] or [defaults] terms, or terms = [] under [repos.{repo}] to opt out'
        )

    paths = tuple(dict.fromkeys(Path(name).expanduser() for name in files))
    plain: list[str] = []
    digests: set[str] = set()
    for path in paths:
        p, d = read_terms(path)
        plain += p
        digests |= set(d)
    public = section.get("public")
    return Machine(
        Identity(identity["name"], identity["email"]),
        public if isinstance(public, str) else None,
        Terms(tuple(dict.fromkeys(plain)), frozenset(digests)),
        paths,
    )


def read_terms(file: Path) -> tuple[list[str], list[str]]:
    """One terms file's plain terms, lowercased, and digests, each in file order."""
    data = tables.read(file, "create it, or remove it from the machine config")
    unknown = sorted(set(data) - TERMS_KEYS)
    if unknown:
        raise Refusal(
            f"terms file {file} has unknown key(s) {', '.join(unknown)}; "
            "the keys are plain and sha256"
        )
    plain = tables.strings(data, "plain", f"terms file {file}")
    digests = tables.strings(data, "sha256", f"terms file {file}")
    bad = [d for d in digests if not SHA256.fullmatch(d)]
    if bad:
        raise Refusal(
            f"terms file {file}: {len(bad)} sha256 entr(ies) are not "
            "64 lowercase hex characters"
        )
    if not plain and not digests:
        raise Refusal(
            f"terms file {file} has no entries; list terms in it, "
            "or opt the repo out with terms = [] in the machine config"
        )
    return [t.lower() for t in plain if t], list(dict.fromkeys(digests))
