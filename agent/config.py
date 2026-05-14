"""Config management — ~/.knowwind/wx/config.json"""

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".knowwind" / "wx" / "config.json"


def load() -> dict | None:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return None


def save(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))
