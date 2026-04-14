from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ai.rag import RAGPipeline


class AnswerPrompting:
    def __init__(self, owner: "RAGPipeline") -> None:
        self._owner = owner

    def build_context(
        self,
        chunks: list[dict],
        query: str,
        intent: str,
        char_budget: int | None = None,
    ) -> str:
        cfg = self._owner._get_settings()
        if not chunks:
            return "Aucune note trouvée dans le coffre pour cette requête."

        chunks = self._owner._prepare_context_chunks(chunks, query, intent)
        chunks = self._dedupe_context_chunks(chunks)
        seen_notes = self.group_chunks_by_note(chunks[: cfg.max_context_chunks])
        self.enrich_seen_notes_with_linked_chunks(seen_notes)
        return self.render_context_from_seen_notes(seen_notes, char_budget)

    @staticmethod
    def _dedupe_context_chunks(chunks: list[dict]) -> list[dict]:
        """Réduit les redondances évidentes pour compacter le contexte envoyé au modèle.

        Règles légères et stables:
        - supprime les doublons exacts par `chunk_id`
        - supprime les quasi-doublons de texte au sein d'une même note
          (normalisation simple + préfixe de signature)
        """
        deduped: list[dict] = []
        seen_ids: set[str] = set()
        seen_text_signatures: set[tuple[str, str]] = set()

        for chunk in chunks:
            chunk_id = str(chunk.get("chunk_id") or "").strip()
            if chunk_id and chunk_id in seen_ids:
                continue

            metadata = chunk.get("metadata") or {}
            file_path = str(metadata.get("file_path") or "")
            text = str(chunk.get("text") or "")
            normalized = " ".join(text.lower().split())
            signature = normalized[:220]
            text_key = (file_path, signature)

            if signature and text_key in seen_text_signatures:
                continue

            if chunk_id:
                seen_ids.add(chunk_id)
            if signature:
                seen_text_signatures.add(text_key)
            deduped.append(chunk)

        return deduped

    @staticmethod
    def group_chunks_by_note(chunks: list[dict]) -> dict[str, list[dict]]:
        seen_notes: dict[str, list[dict]] = {}
        for chunk in chunks:
            file_path = chunk["metadata"].get("file_path", "")
            seen_notes.setdefault(file_path, []).append(chunk)
        return seen_notes

    @staticmethod
    def build_title_to_file_index(seen_notes: dict[str, list[dict]]) -> dict[str, str]:
        title_to_fp: dict[str, str] = {}
        for file_path, note_chunks in seen_notes.items():
            title = note_chunks[0]["metadata"].get("note_title", "")
            if title:
                lowered = title.lower()
                title_to_fp[lowered] = file_path
                title_to_fp[lowered[:30]] = file_path
        return title_to_fp

    def collect_linked_targets(self, seen_notes: dict[str, list[dict]]) -> set[str]:
        title_to_fp = self.build_title_to_file_index(seen_notes)
        linked_targets: set[str] = set()
        for note_chunks in seen_notes.values():
            wikilinks_raw = note_chunks[0]["metadata"].get("wikilinks", "")
            for wikilink in (wikilinks_raw or "").split(","):
                wikilink = wikilink.strip()
                if not wikilink:
                    continue
                lowered = wikilink.lower()
                resolved = title_to_fp.get(lowered) or title_to_fp.get(lowered[:30])
                if resolved and resolved not in seen_notes:
                    linked_targets.add(resolved)
                elif not resolved:
                    linked_targets.add(f"__title__:{wikilink}")
        return linked_targets

    def load_linked_chunks(self, linked_target: str) -> list[dict]:
        if linked_target.startswith("__title__:"):
            return self._owner._get_linked_chunks_by_note_title(linked_target[len("__title__:"):], limit=2)
        return self._owner._get_linked_chunks_by_file_path(linked_target, limit=2)

    def enrich_seen_notes_with_linked_chunks(self, seen_notes: dict[str, list[dict]]) -> None:
        cfg = self._owner._get_settings()
        linked_targets = self.collect_linked_targets(seen_notes)
        if not linked_targets:
            return
        linked_budget = max(1, cfg.max_context_chunks // 2)
        selected_targets = list(linked_targets)[:linked_budget]
        file_path_targets = [target for target in selected_targets if not target.startswith("__title__:")]
        title_targets = [target for target in selected_targets if target.startswith("__title__:")]

        bulk_chunks_by_path = self._owner._get_linked_chunks_by_file_paths(file_path_targets, limit_per_path=2)
        for file_path, linked_chunks in bulk_chunks_by_path.items():
            for chunk in linked_chunks:
                resolved_path = chunk["metadata"].get("file_path", file_path)
                if resolved_path not in seen_notes:
                    seen_notes[resolved_path] = [chunk]

        for linked_target in title_targets:
            linked_chunks = self.load_linked_chunks(linked_target)
            for chunk in linked_chunks:
                file_path = chunk["metadata"].get("file_path", linked_target)
                if file_path not in seen_notes:
                    seen_notes[file_path] = [chunk]

    def render_context_from_seen_notes(
        self,
        seen_notes: dict[str, list[dict]],
        char_budget: int | None,
    ) -> str:
        cfg = self._owner._get_settings()
        parts: list[str] = []
        budget = char_budget if char_budget is not None else cfg.max_context_chars
        seen_line_signatures: set[str] = set()
        effective_max_chunk_chars = cfg.max_chunk_chars
        if len(seen_notes) >= 5:
            effective_max_chunk_chars = max(180, int(cfg.max_chunk_chars * 0.75))

        for file_path, note_chunks in seen_notes.items():
            if budget <= 0:
                break
            title = note_chunks[0]["metadata"].get("note_title", file_path)
            date_mod = note_chunks[0]["metadata"].get("date_modified", "")[:10]
            header = f"### [{title}] ({date_mod})"
            parts.append(header)
            budget -= len(header)

            for chunk in note_chunks:
                if budget <= 0:
                    break
                section = chunk["metadata"].get("section_title", "")
                text = chunk["text"][:effective_max_chunk_chars]
                if len(chunk["text"]) > effective_max_chunk_chars:
                    text += "…"
                line = (f"**{section}** — {text}") if section else text
                signature = self._line_signature(line)
                if signature and signature in seen_line_signatures:
                    continue
                if signature:
                    seen_line_signatures.add(signature)
                if len(line) <= budget:
                    parts.append(line)
                    budget -= len(line)
                else:
                    parts.append(line[:budget] + "…")
                    budget = 0
            parts.append("")

        return "\n".join(parts)

    @staticmethod
    def _line_signature(line: str) -> str:
        normalized = " ".join(line.lower().split())
        if not normalized:
            return ""
        tokens = [token for token in normalized.split(" ") if len(token) > 2]
        if not tokens:
            return normalized[:120]
        return " ".join(tokens[:18])

    def build_messages(
        self,
        query: str,
        context: str,
        history: list[dict[str, str]],
        *,
        intent: str = "general",
        force_study_answer: bool = False,
        resolved_query: str | None = None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": self._owner._system_prompt}]
        messages.extend(history[-8:])

        intent_hint = self.build_intent_hint(query, intent, force_study_answer=force_study_answer)
        question_block = f"**Question :** {query}"
        if resolved_query and resolved_query != query:
            question_block += f"\n**Question résolue dans le fil :** {resolved_query}"

        user_content = (
            f"**Extraits du coffre Obsidian :**\n\n{context}{intent_hint}\n\n"
            f"---\n{question_block}"
        )
        messages.append({"role": "user", "content": user_content})
        return messages

    def build_intent_hint(self, query: str, intent: str, *, force_study_answer: bool) -> str:
        use_study_prompt = self._owner._should_use_study_prompt(intent, query)
        if use_study_prompt:
            intent_hint = self.build_study_intent_hint(query)
            if force_study_answer:
                intent_hint += (
                    "- Deuxième tentative obligatoire : les extraits ci-dessus contiennent déjà assez de matière pour répondre partiellement.\n"
                    "- Tu dois produire une synthèse depuis le coffre, même si le lien causal complet n'est pas formulé mot pour mot.\n"
                    "- Mentionne les limites ou incertitudes, mais ne réponds pas par le hard sentinel.\n"
                    "- Si le lien direct n'est pas prouvé, fournis quand même les apprentissages disponibles sur chaque thème avant d'énoncer cette limite.\n"
                    "- Conserve impérativement les trois intertitres demandés.\n"
                )
            return intent_hint
        if self._owner._should_use_single_subject_prompt(intent, query):
            return self.build_single_subject_intent_hint(query)
        return ""

    def build_study_intent_hint(self, query: str) -> str:
        theme_a, theme_b = self._owner._derive_study_themes(query)
        return (
            "\n\n**Consigne de travail :**\n"
            "- La question demande une synthèse d'étude à partir de plusieurs notes liées.\n"
            "- Si les extraits contiennent des éléments substantiels sur les thèmes demandés, produis une synthèse utile depuis le coffre.\n"
            "- Tu peux rapprocher prudemment plusieurs notes pour dégager des apprentissages, à condition de signaler ce qui est explicite et ce qui relève d'une interprétation prudente.\n"
            "- N'utilise la réponse exacte \"Cette information n'est pas dans ton coffre.\" que s'il n'y a vraiment aucun matériau substantiel pour construire une synthèse partielle.\n"
            "- La réponse doit être structurée avec EXACTEMENT ces trois intertitres Markdown de niveau 3 :\n"
            f"  ### Ce que disent mes notes sur {theme_a}\n"
            f"  ### Ce que disent mes notes sur {theme_b}\n"
            "  ### Ce que je peux conclure\n"
            "- Sous chaque intertitre, fais des phrases courtes et factuelles, en citant les titres de notes utiles entre [crochets].\n"
            "- Si le lien direct n'est pas explicite, remplis quand même les deux premières sections avec les apprentissages disponibles, puis explicite la limite dans la troisième.\n"
        )

    def build_single_subject_intent_hint(self, query: str) -> str:
        primary_theme = self._owner._derive_primary_theme(query)
        return (
            "\n\n**Consigne de travail :**\n"
            f"- La question porte sur un seul sujet principal : {primary_theme}.\n"
            f"- Réponds d'abord et surtout sur {primary_theme}.\n"
            "- Donne un aperçu descriptif utile à partir des notes: nature du sujet, rôle, dates, étapes ou faits saillants, uniquement si ces éléments figurent dans les extraits.\n"
            "- La réponse doit être structurée avec EXACTEMENT ces deux intertitres Markdown de niveau 3 :\n"
            f"  ### Aperçu de {primary_theme}\n"
            "  ### Détails utiles\n"
            "- Sous chaque intertitre, écris un ou deux courts paragraphes clairs.\n"
            "- N'élargis pas la réponse à des thèmes voisins, à des suites possibles, ou à des conséquences futures, sauf si la question le demande explicitement.\n"
            "- Si les notes mentionnent des sujets proches, tu peux les citer brièvement uniquement pour situer le sujet demandé, sans en faire un second axe de réponse.\n"
            "- N'invente aucun prolongement non écrit dans les extraits.\n"
            "- N'utilise la phrase exacte \"Cette information n'est pas dans ton coffre.\" que s'il n'y a vraiment aucune matière sur le sujet demandé.\n"
            "- Cite les titres de notes utiles entre [crochets].\n"
        )