import os
import yaml
from pathlib import Path
from typing import Any

_CONFIG: dict[str, Any] | None = None
_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _ROOT / "config.yaml"


def load_config() -> dict[str, Any]:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Config file not found at {_CONFIG_PATH}. Run setup.py first."
        )

    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        _CONFIG = yaml.safe_load(f)

    return _CONFIG


def get(key: str, default: Any = None) -> Any:
    config = load_config()
    keys = key.split(".")
    val = config
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return default
        if val is None:
            return default
    return val


def set(key: str, value: Any) -> None:
    config = load_config()
    keys = key.split(".")
    target = config
    for k in keys[:-1]:
        if k not in target:
            target[k] = {}
        target = target[k]
    target[keys[-1]] = value


def save() -> None:
    global _CONFIG
    if _CONFIG is None:
        return
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(_CONFIG, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def reload() -> dict[str, Any]:
    global _CONFIG
    _CONFIG = None
    return load_config()


def get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


SMTP_PASSWORD = get_env("SMTP_PASSWORD")
