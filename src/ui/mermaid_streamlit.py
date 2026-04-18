from __future__ import annotations

import re


MERMAID_SPLIT_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)


def validate_mermaid(code: str) -> str:
    """Validate Mermaid code used by the Streamlit chat flow without mutating it."""
    normalized = code.strip().replace("\r\n", "\n")
    if not normalized:
        raise ValueError("Code Mermaid vide")
    invalid = [character for character in normalized if ord(character) not in {9, 10, 13} and not 32 <= ord(character) <= 126]
    if invalid:
        raise ValueError("Caracteres non ASCII detectes")
    return normalized


def build_streamlit_chat_blocks(text: str) -> list[tuple[str, str]]:
    """Prepare render blocks for chat responses containing Mermaid fences."""
    if not MERMAID_SPLIT_RE.search(text):
        return [("text", text)]

    segments = MERMAID_SPLIT_RE.split(text)
    blocks: list[tuple[str, str]] = []
    text_accum: list[str] = []
    for index, segment in enumerate(segments):
        if index % 2 == 0:
            text_accum.append(segment)
            continue

        if text_accum:
            joined_text = "\n".join(text_accum)
            if joined_text:
                blocks.append(("text", joined_text))
            text_accum = []

        raw_mermaid = segment.strip()
        try:
            validated = validate_mermaid(raw_mermaid)
        except ValueError:
            blocks.append(("mermaid_code", raw_mermaid))
        else:
            blocks.append(("mermaid", validated))

    if text_accum:
        joined_text = "\n".join(text_accum)
        if joined_text:
            blocks.append(("text", joined_text))

    return blocks