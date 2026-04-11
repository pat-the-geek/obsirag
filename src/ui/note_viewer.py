from __future__ import annotations

import re

_FM_RE = re.compile(r"^\s*---\n.*?\n---\n?", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def strip_frontmatter(content: str) -> str:
    return _FM_RE.sub("", content, count=1)


def extract_note_outline(content: str) -> list[dict[str, int | str]]:
    cleaned = strip_frontmatter(content)
    outline: list[dict[str, int | str]] = []
    for line_number, line in enumerate(cleaned.splitlines(), start=1):
        match = _HEADING_RE.match(line.strip())
        if not match:
            continue
        outline.append({
            "level": len(match.group(1)),
            "title": match.group(2).strip(),
            "line": line_number,
        })
    return outline


def count_mermaid_blocks(content: str) -> int:
    return len(re.findall(r"```mermaid\s*\n.*?```", content, flags=re.DOTALL))


def make_note_anchor(line_number: int) -> str:
    return f"note-line-{max(1, int(line_number))}"


def inject_line_anchors(content: str, line_numbers: set[int]) -> str:
    cleaned = strip_frontmatter(content)
    if not line_numbers:
        return cleaned

    rendered_lines: list[str] = []
    in_fence = False
    for line_number, line in enumerate(cleaned.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_fence and line_number in line_numbers:
                rendered_lines.append(f'<span id="{make_note_anchor(line_number)}"></span>')
            rendered_lines.append(line)
            in_fence = not in_fence
            continue

        if not in_fence and line_number in line_numbers:
            rendered_lines.append(f'<span id="{make_note_anchor(line_number)}"></span>')
        rendered_lines.append(line)
    return "\n".join(rendered_lines)


def find_note_matches(content: str, query: str, max_results: int = 8) -> list[dict[str, str | int]]:
    cleaned = strip_frontmatter(content)
    search = query.strip().lower()
    if not search:
        return []

    matches: list[dict[str, str | int]] = []
    current_heading = "Introduction"
    for line_number, raw_line in enumerate(cleaned.splitlines(), start=1):
        line = raw_line.strip()
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            current_heading = heading_match.group(2).strip()
            if search in current_heading.lower():
                matches.append({
                    "section": current_heading,
                    "snippet": current_heading,
                    "line": line_number,
                })
            if len(matches) >= max_results:
                break
            continue

        if not line or search not in line.lower():
            continue

        matches.append({
            "section": current_heading,
            "snippet": _compact_snippet(line, search),
            "line": line_number,
        })
        if len(matches) >= max_results:
            break
    return matches


def _compact_snippet(line: str, query: str, radius: int = 90) -> str:
    lowered = line.lower()
    start = lowered.find(query)
    if start < 0:
        return line[: radius * 2]
    left = max(0, start - radius)
    right = min(len(line), start + len(query) + radius)
    snippet = line[left:right].strip()
    if left > 0:
        snippet = "... " + snippet
    if right < len(line):
        snippet = snippet + " ..."
    return snippet