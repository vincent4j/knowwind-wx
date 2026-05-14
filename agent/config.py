"""Config management — ~/.knowwind/wx/config.json"""

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".knowwind" / "wx" / "config.json"
_OLD_CONFIG_PATH = Path.home() / ".knowwind" / "config.json"


def _migrate_old_config() -> None:
    """将旧路径 (~/.knowwind/config.json) 迁移到新路径"""
    if not CONFIG_PATH.exists() and _OLD_CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(_OLD_CONFIG_PATH.read_text())


def load() -> dict | None:
    _migrate_old_config()
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return None

def save(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))
