"""The secrets scanner, run as a subprocess over a copy of the export.

Which one is `[scan] secrets`, a name in `SCANNERS`, per
decision `betterleaks-is-the-default-secrets-scanner`. No validation
flag is passed, so a scan never calls a live API; scanner config in the
environment is dropped, so only what ships in the export can quiet it.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from clean_release import Refusal
from clean_release.scan import Finding

SCANNERS = {
    "betterleaks": "brew install betterleaks (macOS), "
    "otherwise https://github.com/betterleaks/betterleaks",
    "gitleaks": "brew install gitleaks (macOS), "
    "otherwise https://github.com/gitleaks/gitleaks",
}
DEFAULT = "betterleaks"
CONFIG_ENV = (
    "BETTERLEAKS_CONFIG",
    "GITLEAKS_CONFIG",
    "BETTERLEAKS_CONFIG_TOML",
    "GITLEAKS_CONFIG_TOML",
)


def missing(name: str) -> str | None:
    """None when name is on PATH; else how to install it, or which other to use."""
    if shutil.which(name):
        return None
    message = f"`{name}` is not on PATH; install it: {SCANNERS[name]}"
    for other in SCANNERS:
        if other != name and shutil.which(other):
            message += f'; or set `[scan] secrets = "{other}"`'
    return message


def version(name: str) -> str:
    """name and the version it reports, or name alone if it reports none."""
    try:
        proc = subprocess.run(
            [name, "version"], check=False, capture_output=True, timeout=30
        )
    except OSError, subprocess.TimeoutExpired:
        return name
    out = proc.stdout.decode(errors="replace").strip()
    return f"{name} {out}" if proc.returncode == 0 and out else name


def argv(name: str, export: Path, report: Path) -> list[str]:
    """The one command line every scanner in `SCANNERS` takes."""
    return [
        name,
        "dir",
        str(export),
        "--no-banner",
        "--no-color",
        "--redact",
        "--exit-code",
        "0",
        "-f",
        "json",
        "-r",
        str(report),
        "-i",
        str(export),
    ]


def scan(name: str, export: Path) -> list[Finding]:
    """Run scanner name over export; each leak a finding, the secret never in it."""
    export = export.resolve()
    env = {k: v for k, v in os.environ.items() if k not in CONFIG_ENV}
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        proc = subprocess.run(
            argv(name, export, report), capture_output=True, env=env, check=False
        )
        if proc.returncode != 0:
            err = proc.stderr.decode(errors="replace").strip()
            raise Refusal(f"{name} failed with exit {proc.returncode}: {err}")
        try:
            leaks = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise Refusal(f"{name} wrote no readable report: {e}") from None
    try:
        return [
            Finding(
                os.path.relpath(Path(leak["File"]).resolve(), export),
                leak.get("StartLine"),
                f"secret ({leak['RuleID']})",
            )
            for leak in leaks
        ]
    except KeyError, TypeError, AttributeError:
        raise Refusal(
            f"{name}'s report is not a list of leaks with File and RuleID"
        ) from None
