"""Allow development scripts to run before editable installation."""

from __future__ import annotations

import sys
from pathlib import Path


def run(command: str) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from token_optimizer.cli import main

    raise SystemExit(main([command, *sys.argv[1:]]))
