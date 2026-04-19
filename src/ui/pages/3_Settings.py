"""
Page Paramètres — Configuration, statistiques, consommation de tokens.
"""
import subprocess
import sys
from datetime import datetime, UTC
from pathlib import Path

import streamlit as st

from src.config import settings
from src.ui.runtime_state_store import load_processing_status, read_operational_log_tail
from src.ui.telemetry_store import (
    append_fallback_snapshot,
    compute_chroma_trend_alerts,
    compute_fallback_alert_window,
    load_latest_json,
    load_runtime_metrics_last_update,
    load_runtime_metrics_payload,
    load_token_usage_payload,
    save_json,
)
from src.ui.services_cache import get_services
from src.ui.theme import inject_theme, render_theme_toggle
from src.ui.side_menu import render_mobile_main_menu, render_side_menu

_icon = str(Path(__file__).parent.parent / "static" / "favicon-32x32.png")


def _format_metric_number(value: float | int) -> str:
    if isinstance(value, float):
        return f"{value:,.3f}"
    return f"{value:,}"


def _parse_iso_ts(value: str) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _format_age_hours(hours: float) -> str:
    if hours < 0:
        return "inconnu"
    if hours < 1:
        return f"{hours * 60:.0f} min"
    return f"{hours:.1f} h"


# Icône et config page
st.set_page_config(page_title="Paramètres — ObsiRAG", page_icon=_icon, layout="wide", initial_sidebar_state="expanded")

inject_theme()
render_mobile_main_menu()
# Ajout à l'historique navigation
HISTO_KEY = "obsirag_historique"
st.session_state.setdefault(HISTO_KEY, [])
if not st.session_state[HISTO_KEY] or st.session_state[HISTO_KEY][-1] != "Paramètres":
    st.session_state[HISTO_KEY].append("Paramètres")
render_side_menu()
svc = get_services()

render_theme_toggle()
st.title("⚙️ Paramètres & Statistiques")

tab_config, tab_tokens, tab_runtime_metrics, tab_index, tab_danger = st.tabs(
    ["🔧 Configuration", "📊 Tokens IA", "📈 Métriques runtime", "📂 Index", "⚠️ Données"]
)

# ---- Configuration ----
with tab_config:
    st.markdown("### Modèle de génération (MLX-LM)")
    c1, c2 = st.columns(2)
    c1.text_input("Modèle MLX", value=settings.mlx_chat_model, disabled=True)
    llm_ok = svc.llm.is_available()
    c2.markdown("")  # espaceur
    st.markdown(f"**Statut :** {'🟢 Modèle chargé' if llm_ok else '🔴 Modèle non disponible'}")

    st.divider()
    st.markdown("### Chemins")

    col1, col2 = st.columns(2)
    col1.text_input("Coffre (lecture)", value=settings.vault_path, disabled=True)
    col2.text_input("Données système locales", value=settings.app_data_dir, disabled=True)

    st.caption(
        "📁 **Dans le coffre** (visibles dans Obsidian) : "
        f"`obsirag/insights/`, `obsirag/synthesis/`  \n"
        "� **Données système** (hors iCloud) : ChromaDB, index, stats, requêtes"
    )

    st.divider()
    st.markdown("### RAG & Contexte")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Chunks max / réponse", settings.max_context_chunks)
    c2.metric("Chars max contexte", f"{settings.max_context_chars:,}")
    c3.metric("Chars max / chunk", settings.max_chunk_chars)
    c4.metric("Résultats recherche", settings.search_top_k)

    st.divider()
    st.markdown("### Auto-apprentissage")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Activé", "Oui" if settings.autolearn_enabled else "Non")
    c2.metric("Intervalle", f"{settings.autolearn_interval_minutes} min")
    c3.metric("Notes / cycle", settings.autolearn_max_notes_per_run)
    c4.metric("Plage horaire", f"{settings.autolearn_active_hour_start:02d}h – {settings.autolearn_active_hour_end:02d}h")
    c5.metric("Bulk max notes", settings.autolearn_bulk_max_notes if settings.autolearn_bulk_max_notes > 0 else "∞")

    st.divider()
    st.markdown("### Modèles IA locaux")
    c1, c2 = st.columns(2)
    c1.text_input("Embedding", value=settings.embedding_model, disabled=True)
    c2.text_input("NER (spaCy)", value=settings.ner_model, disabled=True)

# ---- Statistiques tokens ----
with tab_tokens:
    st.markdown("### Consommation de tokens par appel LLM")

    token_file = settings.token_stats_file
    data = load_token_usage_payload(token_file)
    if not data:
        st.info("Aucune donnée de tokens encore enregistrée.")
    else:
        cumul = data.get("cumulative", {})

        c1, c2, c3 = st.columns(3)
        c1.metric("Tokens prompt (total)", f"{cumul.get('prompt', 0):,}")
        c2.metric("Tokens completion (total)", f"{cumul.get('completion', 0):,}")
        c3.metric("Appels LLM (total)", f"{cumul.get('calls', 0):,}")

        st.divider()
        st.markdown("#### Détail par jour et par opération")

        days = sorted([k for k in data.keys() if k != "cumulative"], reverse=True)
        for day in days[:14]:
            with st.expander(f"📅 {day}"):
                day_data = data[day]
                rows = []
                for op, stats in day_data.items():
                    rows.append({
                        "Opération": op,
                        "Prompt": stats.get("prompt", 0),
                        "Completion": stats.get("completion", 0),
                        "Total": stats.get("prompt", 0) + stats.get("completion", 0),
                        "Appels": stats.get("calls", 0),
                    })
                if rows:
                    import pandas as pd
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)

# ---- Metriques runtime ----
with tab_runtime_metrics:
    st.markdown("### Activité interne d'ObsiRAG")
    metrics_file = settings.runtime_metrics_file
    metrics_payload = load_runtime_metrics_payload(metrics_file)

    if not metrics_payload:
        st.info("Aucune métrique runtime encore enregistrée.")
    else:
        counters = metrics_payload.get("counters", {})
        summaries = metrics_payload.get("summaries", {})
        last_update = load_runtime_metrics_last_update(metrics_file) or "Inconnue"
        st.caption(f"Dernière mise à jour métriques : {last_update}")

        # Snapshot glissant des compteurs fallback pour alerte de fréquence.
        append_fallback_snapshot(
            settings.fallback_snapshot_file,
            counters,
            max_lines=settings.fallback_snapshot_max_lines,
            max_age_days=settings.fallback_snapshot_retention_days,
            max_total_mb=settings.fallback_snapshot_budget_mb,
        )
        fallback_alert = compute_fallback_alert_window(
            settings.fallback_snapshot_file,
            window_minutes=settings.fallback_alert_window_minutes,
            threshold=settings.fallback_alert_rglob_threshold,
        )
        if fallback_alert.should_warn:
            st.warning(
                "⚠️ Fréquence fallback rglob élevée : "
                f"{fallback_alert.summary}. "
                "Chemin nominal indexé potentiellement dégradé."
            )
        else:
            st.caption(
                "Fallback rglob (fenêtre glissante) : "
                f"{fallback_alert.summary}."
            )

        key_metrics = [
            ("rag_sentinel_answers_total", "Réponses sentinelle"),
            ("rag_context_retries_total", "Retries de contexte"),
            ("autolearn_insights_created_total", "Insights créés"),
            ("autolearn_insights_appended_total", "Insights enrichis"),
            ("autolearn_web_search_error_total", "Erreurs web"),
        ]
        available_metrics = [(key, label) for key, label in key_metrics if key in counters]
        if available_metrics:
            st.divider()
            st.markdown("#### Indicateurs clés")
            cols = st.columns(min(3, len(available_metrics)))
            for index, (key, label) in enumerate(available_metrics):
                cols[index % len(cols)].metric(label, _format_metric_number(counters[key]))

        st.divider()
        st.markdown("#### Fallback filesystem (learning)")
        fallback_rows = [
            ("autolearn_fs_fallback_insight_glob_total", "Fallback glob insights"),
            ("autolearn_fs_fallback_insight_rglob_total", "Fallback rglob insights"),
            ("autolearn_fs_fallback_rename_rglob_total", "Fallback rglob renommage"),
        ]
        fallback_cols = st.columns(3)
        for index, (metric_name, label) in enumerate(fallback_rows):
            fallback_cols[index].metric(label, int(counters.get(metric_name, 0)))
        st.caption(
            "Seuil d'alerte : "
            f"{settings.fallback_alert_rglob_threshold} fallback(s) rglob / "
            f"{settings.fallback_alert_window_minutes} min"
        )

        if counters:
            st.divider()
            st.markdown("#### Compteurs cumulés")
            import pandas as pd

            counter_rows = [
                {"Métrique": key, "Valeur": int(value)}
                for key, value in sorted(counters.items(), key=lambda item: (-int(item[1]), item[0]))
            ]
            st.dataframe(pd.DataFrame(counter_rows), use_container_width=True, hide_index=True)

        if summaries:
            st.divider()
            st.markdown("#### Agrégats observés")
            import pandas as pd

            summary_rows = [
                {
                    "Métrique": key,
                    "Observations": int(values.get("count", 0)),
                    "Dernière valeur": _format_metric_number(float(values.get("last", 0.0))),
                    "Moyenne": _format_metric_number(float(values.get("avg", 0.0))),
                    "Total": _format_metric_number(float(values.get("total", 0.0))),
                }
                for key, values in sorted(summaries.items())
            ]
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("#### Export comparatif perf Chroma (local/CI)")
    report_dir = settings.chroma_perf_reports_dir
    latest_local = report_dir / "latest_local.json"
    latest_ci = report_dir / "latest_ci.json"
    latest_cmp = report_dir / "latest_comparison.md"
    baseline_local = report_dir / "baseline_local.json"

    if st.button("🧪 Exporter un rapport perf Chroma", key="export_chroma_perf"):
        try:
            result = subprocess.run(
                [sys.executable, "scripts/export_chroma_perf_report.py"],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = (result.stdout or "").strip()
            st.success("Rapport exporté avec succès.")
            if output:
                st.caption(output)
        except Exception as exc:
            st.warning(f"Export perf Chroma indisponible: {exc}")

    if st.button("🗓️ Export hebdomadaire compact", key="export_observability_weekly"):
        try:
            result = subprocess.run(
                [sys.executable, "scripts/export_observability_weekly.py"],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = (result.stdout or "").strip()
            st.success("Export hebdomadaire observabilité généré.")
            if output:
                st.caption(output)
        except Exception as exc:
            st.warning(f"Export hebdomadaire indisponible: {exc}")

    st.caption(f"Dossier rapports : {report_dir}")
    st.caption(
        "Derniers rapports : "
        f"local={'OK' if latest_local.exists() else 'absent'} · "
        f"ci={'OK' if latest_ci.exists() else 'absent'} · "
        f"comparatif={'OK' if latest_cmp.exists() else 'absent'}"
    )

    st.markdown("##### Navigation rapide fichiers")
    quick_links = [
        ("latest_local.json", latest_local),
        ("latest_ci.json", latest_ci),
        ("latest_comparison.md", latest_cmp),
        ("latest_weekly.json", settings.observability_weekly_reports_dir / "latest_weekly.json"),
        ("latest_weekly.md", settings.observability_weekly_reports_dir / "latest_weekly.md"),
        ("fallback_metrics_history.jsonl", settings.fallback_snapshot_file),
    ]
    for label, path in quick_links:
        if path.exists():
            st.markdown(f"- [{label}]({path.as_uri()})")
        else:
            st.caption(f"- {label} (absent)")

    local_payload = load_latest_json(latest_local)
    if local_payload and st.button("📌 Définir la baseline locale", key="set_chroma_baseline"):
        save_json(baseline_local, local_payload)
        st.success("Baseline locale mise à jour.")

    baseline_payload = load_latest_json(baseline_local)
    trend_alerts = []
    if local_payload and baseline_payload:
        trend_alerts = compute_chroma_trend_alerts(
            local_payload,
            baseline_payload,
            warn_pct=settings.chroma_perf_trend_warn_pct,
        )
        if trend_alerts:
            st.warning(
                "⚠️ Alerte tendance perf Chroma: dégradation détectée "
                f"(seuil {settings.chroma_perf_trend_warn_pct:.1f}%)."
            )
            for alert in trend_alerts:
                st.caption(
                    f"- {alert.metric}: {alert.latest_value:.4f} vs baseline {alert.baseline_value:.4f} "
                    f"({alert.degrade_pct:.2f}%)"
                )
        else:
            st.caption(
                "Tendance perf Chroma stable par rapport à la baseline "
                f"(seuil {settings.chroma_perf_trend_warn_pct:.1f}%)."
            )

    st.divider()
    st.markdown("#### Tableau de bord santé observabilité")
    now_ts = datetime.now(UTC).timestamp()
    local_age_h = -1.0
    ci_age_h = -1.0
    fallback_age_h = -1.0
    if local_payload:
        local_ts = _parse_iso_ts(str(local_payload.get("ts_utc", "")))
        if local_ts > 0:
            local_age_h = max(0.0, (now_ts - local_ts) / 3600.0)
    latest_ci_payload = load_latest_json(latest_ci)
    if latest_ci_payload:
        ci_ts = _parse_iso_ts(str(latest_ci_payload.get("ts_utc", "")))
        if ci_ts > 0:
            ci_age_h = max(0.0, (now_ts - ci_ts) / 3600.0)
    if settings.fallback_snapshot_file.exists():
        fallback_age_h = max(0.0, (now_ts - settings.fallback_snapshot_file.stat().st_mtime) / 3600.0)

    health_status = "green"
    health_reason = "Observabilité nominale"
    if fallback_alert.should_warn or bool(trend_alerts) or local_age_h < 0 or local_age_h > 48:
        health_status = "red"
        health_reason = "Signal critique: fallback/perf/fraîcheur locale"
    elif ci_age_h < 0 or ci_age_h > 168 or fallback_age_h < 0 or fallback_age_h > 24:
        health_status = "orange"
        health_reason = "Signal d'attention: fraîcheur CI/snapshots"

    status_label = {
        "green": "🟢 Vert",
        "orange": "🟠 Orange",
        "red": "🔴 Rouge",
    }[health_status]
    if health_status == "green":
        st.success(f"{status_label} — {health_reason}")
    elif health_status == "orange":
        st.warning(f"{status_label} — {health_reason}")
    else:
        st.error(f"{status_label} — {health_reason}")

    c_health_1, c_health_2, c_health_3 = st.columns(3)
    c_health_1.metric("Fallback rglob fenêtre", fallback_alert.rglob_events_in_window)
    c_health_2.metric("Alertes tendance perf", len(trend_alerts))
    c_health_3.metric("Âge report local", _format_age_hours(local_age_h))
    st.caption(
        "Fraîcheur complémentaire : "
        f"CI={_format_age_hours(ci_age_h)} · "
        f"snapshots fallback={_format_age_hours(fallback_age_h)}"
    )

    st.caption(
        "Rétention active : "
        f"fallback={settings.fallback_snapshot_retention_days}j/{settings.fallback_snapshot_max_lines} lignes/"
        f"{settings.fallback_snapshot_budget_mb:.1f}MB · "
        f"chroma={settings.chroma_perf_report_retention_days}j/{settings.chroma_perf_report_max_files} fichiers/"
        f"{settings.chroma_perf_report_budget_mb:.1f}MB"
    )
    if latest_cmp.exists():
        st.markdown("##### Dernier comparatif local/CI")
        st.markdown(latest_cmp.read_text(encoding="utf-8"))

    st.divider()
    st.markdown("#### État de traitement auto-learner")
    processing_status = load_processing_status(settings.processing_status_file)
    if not processing_status:
        st.caption("Aucun état de traitement persistant disponible.")
    else:
        status_label = "Actif" if processing_status.get("active") else "Inactif"
        st.caption(f"Statut : {status_label}")
        if processing_status.get("note"):
            st.caption(f"Note : {processing_status.get('note')}")
        if processing_status.get("step"):
            st.caption(f"Étape : {processing_status.get('step')}")
        if processing_status.get("log"):
            st.code("\n".join(str(item) for item in processing_status.get("log", [])[-15:]), language=None)

    st.divider()
    st.markdown("#### Journal opérationnel récent")
    log_lines = read_operational_log_tail(
        Path(settings.log_dir) / "obsirag.log",
        fallback_path=Path("logs") / "obsirag.log",
        lines=30,
    )
    if log_lines:
        st.code("\n".join(log_lines), language=None)
    else:
        st.caption("Aucune ligne de log disponible.")

# ---- Index ChromaDB ----
with tab_index:
    st.markdown("### État de l'index vectoriel")
    st.caption("Stocké dans les données système locales — pas dans iCloud")

    recent_notes = svc.chroma.list_recent_notes(limit=20)
    user_notes = svc.chroma.list_user_notes()
    generated_notes = svc.chroma.list_generated_notes()
    c1, c2, c3 = st.columns(3)
    total_notes = svc.chroma.count_notes()
    c1.metric("Notes indexées", total_notes)
    c2.metric("Notes utilisateur", len(user_notes))
    c3.metric("Artefacts générés", len(generated_notes))
    st.caption(f"Chunks total : {svc.chroma.count()}")

    if recent_notes:
        st.markdown("#### 20 notes les plus récentes")
        import pandas as pd
        df = pd.DataFrame([
            {
                "Titre": n["title"],
                "Chemin": n["file_path"],
                "Modifié le": n["date_modified"][:10],
                "Tags": ", ".join(n.get("tags", [])[:3]),
            }
            for n in recent_notes
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

    if st.button("♻️ Re-indexer maintenant", use_container_width=True):
        progress_bar = st.progress(0, text="Démarrage de l'indexation…")
        note_label = st.empty()

        def _on_progress(note: str, processed: int, total: int) -> None:
            pct = processed / total if total > 0 else 0
            progress_bar.progress(pct, text=f"Indexation {processed} / {total}")
            note_label.caption(f"📄 `{note}`")

        stats = svc.indexer.index_vault(on_progress=_on_progress)
        progress_bar.progress(1.0, text="Indexation terminée")
        note_label.empty()
        st.success(
            f"Terminé — +{stats['added']} ajoutées, "
            f"~{stats['updated']} mises à jour, "
            f"🗑 {stats['deleted']} supprimées"
        )

# ---- Zone dangereuse ----
with tab_danger:
    st.warning("⚠️ Ces actions sont irréversibles.")

    st.markdown("#### Réinitialiser l'index vectoriel")
    st.caption(
        "Supprime ChromaDB et l'état d'indexation des données système locales. "
        "Le coffre Obsidian n'est pas modifié. "
        "Une re-indexation complète se lancera au prochain démarrage."
    )
    confirm = st.text_input("Tapez **RESET** pour confirmer", key="reset_confirm")
    if st.button("🗑 Réinitialiser l'index", type="primary") and confirm == "RESET":
        import shutil
        chroma_dir = Path(settings.chroma_persist_dir)
        if chroma_dir.exists():
            shutil.rmtree(chroma_dir)
        if settings.index_state_file.exists():
            settings.index_state_file.unlink()
        st.success("Index réinitialisé. Redémarrez l'application pour recréer la base.")

    st.divider()
    st.markdown("#### Supprimer les notes ObsiRAG du coffre")
    st.caption(
        "Supprime `obsirag/insights/` et `obsirag/synthesis/` de votre coffre. "
        "L'index et les données système ne sont pas affectés."
    )
    confirm2 = st.text_input("Tapez **DELETE NOTES** pour confirmer", key="delete_notes_confirm")
    if st.button("🗑 Supprimer les notes ObsiRAG", type="primary") and confirm2 == "DELETE NOTES":
        import shutil
        for d in [settings.insights_dir, settings.synthesis_dir]:
            if d.exists():
                shutil.rmtree(d)
        st.success("Notes ObsiRAG supprimées du coffre.")

    st.divider()
    st.markdown("#### Nettoyer l'ancien dossier `obsirag/data/`")
    st.caption(
        "Si vous migrez depuis une ancienne version, l'ancien dossier "
        "`obsirag/data/` peut encore exister dans votre coffre. "
        "Vous pouvez le supprimer manuellement depuis Obsidian ou votre Finder."
    )
    st.code(
        f"rm -rf \"{settings.vault_path}/obsirag/data\"",
        language="bash"
    )
