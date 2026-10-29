"""TOML read with refusals, shared by the policy and the machine config."""

import tomllib
from pathlib import Path

from clean_release import Refusal


def read(file: Path, fix: str) -> dict:
    """Load file as TOML; a missing file refuses with fix, bad TOML by its error."""
    try:
        return tomllib.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Refusal(f"{file} does not exist; {fix}") from None
    except tomllib.TOMLDecodeError as e:
        raise Refusal(f"{file} is not valid TOML: {e}") from None


def strings(table: object, key: str, where: str) -> list[str]:
    """table[key] as a list of strings, [] when absent; anything else refuses."""
    value = table.get(key, []) if isinstance(table, dict) else []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise Refusal(f"{where} {key} must be a list of strings")
    return list(value)
