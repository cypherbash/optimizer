"""Small JSON/YAML serialization boundary with no required dependency."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def dumps(data: Any, format_name: str = "yaml") -> str:
    if format_name == "json":
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if format_name != "yaml":
        raise ValueError(f"Unsupported format: {format_name}")
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        # JSON is valid YAML 1.2 and keeps the default path dependency-free.
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return str(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def loads(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ValueError("Non-JSON YAML requires the optional PyYAML dependency") from exc
        return yaml.safe_load(text)


def load_file(path: Path) -> Any:
    return loads(path.read_text(encoding="utf-8"))


def write_file(path: Path, data: Any, format_name: str | None = None) -> None:
    selected = format_name or ("json" if path.suffix.lower() == ".json" else "yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(data, selected), encoding="utf-8")
