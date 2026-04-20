from __future__ import annotations

import re
import unicodedata


MERMAID_FENCE_RE = re.compile(r"(```mermaid\s*\n)(.*?)(\n?```)", re.IGNORECASE | re.DOTALL)
_FLOW_EDGE_BREAK_PATTERNS = (
    re.compile(r"(\][ \t]{2,})([A-Za-z][A-Za-z0-9_]*\s*(?:-->|---|==>|-.->|-\.->))"),
    re.compile(r"(\)[ \t]{2,})([A-Za-z][A-Za-z0-9_]*\s*(?:-->|---|==>|-.->|-\.->))"),
    re.compile(r"(\}[ \t]{2,})([A-Za-z][A-Za-z0-9_]*\s*(?:-->|---|==>|-.->|-\.->))"),
)
_FLOW_NODE_LABEL_RE = re.compile(r'\b([A-Za-z][A-Za-z0-9_]*)\[(?!["`])([^\]\n]+)\]')

_ASCII_REPLACEMENTS = str.maketrans(
    {
        "’": "'",
        "‘": "'",
        '“': '"',
        '”': '"',
        "–": "-",
        "—": "-",
        "…": "...",
        "\u00a0": " ",
    }
)


def _normalize_directive_spacing(value: str) -> str:
    return (
        value
        .replace("date Format", "dateFormat")
        .replace("date format", "dateFormat")
        .replace("axis Format", "axisFormat")
        .replace("axis format", "axisFormat")
        .replace("tick Interval", "tickInterval")
        .replace("tick interval", "tickInterval")
        .replace("today Marker", "todayMarker")
        .replace("today marker", "todayMarker")
        .replace("weekend Fill", "weekendFill")
        .replace("weekend fill", "weekendFill")
        .replace("acc Title", "accTitle")
        .replace("acc title", "accTitle")
        .replace("acc Descr", "accDescr")
        .replace("acc descr", "accDescr")
    )


def contains_mermaid_fence(text: str) -> bool:
    return bool(MERMAID_FENCE_RE.search(text or ""))


def _detect_mermaid_diagram_type(code: str) -> str | None:
    for raw_line in (code or "").split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("%%"):
            continue
        if line.startswith("graph "):
            return "flowchart"
        token = line.split()[0]
        return token.lower()
    return None


def normalize_mermaid_code_syntax(code: str) -> str:
    normalized = (code or "").strip().replace("\r\n", "\n")
    if not normalized:
        return normalized

    for pattern in _FLOW_EDGE_BREAK_PATTERNS:
        normalized = pattern.sub(lambda match: f"{match.group(1).rstrip()}\n{match.group(2)}", normalized)

    diagram_type = _detect_mermaid_diagram_type(normalized)
    if diagram_type not in {"flowchart", "graph"}:
        return normalized

    normalized_lines: list[str] = []
    for line in normalized.split("\n"):
        def _quote_label(match: re.Match[str]) -> str:
            node_id, label = match.groups()
            if not any(character in label for character in "():"):
                return f"{node_id}[{label}]"
            escaped_label = label.replace("\\", "\\\\").replace('"', '\\"')
            return f'{node_id}["{escaped_label}"]'

        normalized_lines.append(_FLOW_NODE_LABEL_RE.sub(_quote_label, line))

    return "\n".join(normalized_lines)


def sanitize_mermaid_code_ascii(code: str) -> str:
    normalized = (code or "").replace("\r\n", "\n")
    sanitized_lines: list[str] = []

    for line in normalized.split("\n"):
        indent_match = re.match(r"^[ \t]*", line)
        indent = indent_match.group(0) if indent_match else ""
        body = line[len(indent):].translate(_ASCII_REPLACEMENTS)
        body = unicodedata.normalize("NFD", body)
        body = "".join(character for character in body if unicodedata.category(character) != "Mn")
        body = "".join(
            character
            for character in body
            if character in {"\t", "\n", "\r"} or 32 <= ord(character) <= 126
        )
        sanitized_lines.append(_normalize_directive_spacing(f"{indent}{body.rstrip()}"))

    return normalize_mermaid_code_syntax("\n".join(sanitized_lines).strip())


def sanitize_mermaid_blocks(text: str) -> str:
    if not text:
        return text

    def _replace(match: re.Match[str]) -> str:
        opening_fence, code, closing_fence = match.groups()
        sanitized = sanitize_mermaid_code_ascii(code)
        if sanitized:
            return f"{opening_fence}{sanitized}\n{closing_fence}"
        return f"{opening_fence}{closing_fence}"

    return MERMAID_FENCE_RE.sub(_replace, text)