from __future__ import annotations


def build_navigation_turn_title(turn: int, preview: str) -> str:
    return f"**Tour {turn}** · {preview}"


def build_navigation_meta(source_count: int | None, primary_source_title: str | None) -> str:
    parts: list[str] = []
    if source_count:
        parts.append(f"{source_count} source(s)")
    if primary_source_title:
        parts.append(f"source: {primary_source_title}")
    return " · ".join(parts)


def build_saved_conversation_title(title: str) -> str:
    return f"**{title}**"


def build_saved_conversation_meta(month: str, file_path: str) -> str:
    return f"{month} · {file_path}"


def build_generation_summary_caption(ttft: float, total: float) -> str:
    return f"TTFT {ttft:.1f}s · total {total:.1f}s"


def build_web_sources_markdown(results: list[dict]) -> str:
    return "\n".join(
        f"- [{result.get('title', result.get('href', ''))}]({result.get('href', '')})"
        for result in results
    )