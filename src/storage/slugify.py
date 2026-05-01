"""Utility to build filesystem-safe ASCII stems from arbitrary text."""

import re
import unicodedata


def build_ascii_stem(
    text: str,
    *,
    fallback: str = "item",
    max_length: int = 60,
    separator: str = "-",
) -> str:
    """Return an ASCII-safe stem derived from *text*.

    Steps:
    1. Decompose unicode characters (NFD) and keep only ASCII bytes so that
       accented latin letters are preserved as their base letter while
       non-latin scripts (CJK, Arabic, …) are dropped entirely.
    2. Replace every run of characters that are not alphanumeric or the chosen
       *separator* with a single *separator*.
    3. Strip leading/trailing separators.
    4. Collapse consecutive separators into one.
    5. Truncate to *max_length* (trimming a trailing separator if necessary).
    6. If the result is empty, return *fallback*.
    """
    # Step 1: Replace runs of non-ASCII characters with the separator so that
    # boundaries between latin and non-latin scripts produce a separator, then
    # NFD-decompose the remaining text and drop any residual non-ASCII bytes
    # (e.g. combining diacritics from accented latin letters).
    pre = re.sub(r"[^\x00-\x7F]+", separator, text)
    nfd = unicodedata.normalize("NFD", pre)
    ascii_bytes = nfd.encode("ascii", errors="ignore")
    ascii_text = ascii_bytes.decode("ascii")

    # Step 2: replace non-word characters with the separator
    sep = re.escape(separator)
    slug = re.sub(r"[^A-Za-z0-9" + sep + r"]+", separator, ascii_text)

    # Step 3 & 4: strip and collapse consecutive separators
    slug = re.sub(sep + r"+", separator, slug).strip(separator)

    # Step 5: truncate
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip(separator)

    # Step 6: fallback
    return slug if slug else fallback
