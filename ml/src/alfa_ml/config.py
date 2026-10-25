"""Загрузка конфигов из ml/config."""
import copy
import os
from functools import cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(os.environ.get("ALFA_ML_CONFIG_DIR", Path(__file__).resolve().parents[2] / "config"))


@cache
def _read(name: str) -> dict:
    with open(CONFIG_DIR / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(name: str) -> dict:
    """Конфиг по имени файла без расширения: scoring, generator."""
    return copy.deepcopy(_read(name))


def deep_merge(base: dict, override: dict) -> dict:
    """Новый словарь: base, в котором вложенные ключи заменены значениями из override."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged
