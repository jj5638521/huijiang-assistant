"""Utilities for name normalization."""
from __future__ import annotations

import re
from typing import Mapping, TypeVar

T = TypeVar("T")


def name_key(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return cleaned
    cleaned = cleaned.replace("（", "(").replace("）", ")")
    match = re.match(r"^(.*?)\s*\([^()]*\)\s*$", cleaned)
    if match:
        return match.group(1).strip()
    return cleaned


def normalize_name_map(mapping: Mapping[str, T]) -> dict[str, T]:
    return {name_key(key): value for key, value in mapping.items()}
