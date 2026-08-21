from __future__ import annotations


import re

_WINDOWS_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
}
_FORBIDDEN_CHARS_PATTERN = re.compile(r'[\/\\:*?"<>|\x00-\x1f]')


def validate_storage_name(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty")
    if cleaned in {".", ".."}:
        raise ValueError(f"{field_name} cannot be '.' or '..'")
    if cleaned.endswith(".") or cleaned.endswith(" "):
        raise ValueError(f"{field_name} cannot end with a dot or space")
    if _FORBIDDEN_CHARS_PATTERN.search(cleaned):
        raise ValueError(
            f"{field_name} cannot contain path separators or illegal characters: / \\ : * ? \" < > | or control characters"
        )
    base_stem = cleaned.split(".", 1)[0].lower()
    if base_stem in _WINDOWS_RESERVED_NAMES:
        raise ValueError(f"{field_name} cannot use reserved system device name: {cleaned}")
    return cleaned
