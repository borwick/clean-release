"""`[verify]`: run each command in a copy of the export, no shell, in order."""

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from clean_release.scan import Finding

WHERE = "[verify]"


@dataclass(frozen=True)
class Failed:
    """A command that failed: its finding, and what it printed."""

    finding: Finding
    output: str


def run(commands: tuple[str, ...], export: Path) -> list[Failed]:
    """Run every command with export as its cwd; each that fails is returned."""
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    failed = []
    for cmd in commands:
        try:
            proc = subprocess.run(
                shlex.split(cmd),
                cwd=export,
                env=env,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            failed.append(Failed(Finding(WHERE, None, f"`{cmd}` not found"), ""))
            continue
        except OSError as e:
            kind = f"`{cmd}` could not run: {e.strerror}"
            failed.append(Failed(Finding(WHERE, None, kind), ""))
            continue
        if proc.returncode != 0:
            out = (proc.stdout + proc.stderr).decode(errors="replace")
            kind = f"`{cmd}` exited {proc.returncode}"
            failed.append(Failed(Finding(WHERE, None, kind), out))
    return failed
