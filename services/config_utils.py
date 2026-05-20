from configparser import ConfigParser
from typing import List


def load_config(config_path: str = "config.cfg", local_config_path: str = "config.local.cfg") -> ConfigParser:
    """Load base config and optional local override config."""
    config = ConfigParser(interpolation=None)
    config.read([config_path, local_config_path], encoding="utf-8")
    return config


def parse_list_value(raw_value: str) -> List[str]:
    """Parse multi-line and/or comma-separated values into a clean list."""
    if not raw_value:
        return []

    values: List[str] = []
    for line in raw_value.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for item in stripped.split(","):
            item = item.strip()
            if item:
                values.append(item)
    return values
