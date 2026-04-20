from __future__ import annotations

import re
import unicodedata


def build_ascii_stem(
    value: str,
    *,
    fallback: str,
    max_length: int = 60,
    separator: str = "_",
) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").strip())
    without_marks = "".join(character for character in normalized if unicodedata.category(character) != "Mn")
    ascii_spaced = "".join(character if ord(character) < 128 else " " for character in without_marks)
    cleaned = re.sub(r"[^A-Za-z0-9]+", separator, ascii_spaced).strip(separator)
    if max_length > 0:
        cleaned = cleaned[:max_length].rstrip(separator)
    return cleaned or fallback