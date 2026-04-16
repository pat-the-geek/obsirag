from __future__ import annotations

import pytest

from src.ui.chat_sessions import (
    create_new_thread,
    create_thread_from_messages,
    ensure_chat_state,
    get_current_thread,
    list_thread_summaries,
    resolve_active_thread_messages,
    switch_thread,
    update_current_thread,
)


@pytest.mark.unit
class TestChatSessions:
    def test_update_current_thread_persists_messages_draft_and_title_from_user_message(self):
        state = ensure_chat_state(None)

        updated = update_current_thread(
            state,
            messages=[{"role": "user", "content": "Comment structurer un graphe de notes ?"}],
            draft="suite",
        )

        current = get_current_thread(updated)

        assert current["draft"] == "suite"
        assert current["messages"][0]["content"] == "Comment structurer un graphe de notes ?"
        assert current["title"].startswith("Comment structurer un graphe de notes")

    def test_create_switch_and_summarize_threads_keeps_current_flag(self):
        state = create_thread_from_messages(
            None,
            messages=[
                {"role": "user", "content": "Premier sujet"},
                {"role": "assistant", "content": "Réponse A"},
            ],
        )
        first_thread_id = get_current_thread(state)["id"]

        state = create_new_thread(state, title="Deuxième fil")
        second_thread_id = get_current_thread(state)["id"]
        state = update_current_thread(state, messages=[{"role": "user", "content": "Sujet B"}])
        state = switch_thread(state, first_thread_id)

        summaries = list_thread_summaries(state)

        assert any(summary["id"] == first_thread_id and summary["is_current"] for summary in summaries)
        assert any(summary["id"] == second_thread_id and not summary["is_current"] for summary in summaries)
        assert any(summary["preview"] == "Réponse A" for summary in summaries)

    def test_update_current_thread_keeps_last_generation_stats(self):
        state = ensure_chat_state(None)

        updated = update_current_thread(
            state,
            messages=[{"role": "assistant", "content": "Réponse"}],
            last_gen_stats={"tokens": 42, "tps": 12.5},
        )

        current = get_current_thread(updated)

        assert current["last_gen_stats"] == {"tokens": 42, "tps": 12.5}

    def test_resolve_active_thread_messages_keeps_visible_history_when_persisted_copy_is_stale(self):
        persisted = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Ancienne réponse"},
        ]
        visible = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Réponse affichée complète"},
        ]

        chosen = resolve_active_thread_messages(
            thread_messages=persisted,
            current_messages=visible,
        )

        assert chosen == visible

    def test_resolve_active_thread_messages_prefers_persisted_history_when_it_is_richer(self):
        persisted = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Réponse 1"},
            {"role": "user", "content": "Question 2"},
        ]
        visible = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Réponse 1"},
        ]

        chosen = resolve_active_thread_messages(
            thread_messages=persisted,
            current_messages=visible,
        )

        assert chosen == persisted
