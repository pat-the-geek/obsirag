# Runbook — Incident Performance ObsiRAG

## 1. Détection
- **Alertes** :
  - Surveillez les métriques critiques (ChromaStore, RAG, auto-learner) via les exports :
    - `scripts/export_chroma_perf_report.py`
    - `scripts/export_observability_weekly.py`
  - Consultez les rapports dans `data/stats/chroma_perf_reports/` et `data/stats/observability_weekly/`.
  - Vérifiez les tests de performance (`pytest -m perf`).
- **Signaux d’incident** :
  - Régression sur les temps de réponse (> seuils docs/performances.md)
  - Échecs ou lenteurs dans les benchmarks/tests
  - Alertes dans la CI ou lors de la validation locale

## 2. Diagnostic
- **Collecte d’évidence** :
  - Récupérez les logs récents (`logs/`, logs/validation/)
  - Exportez les rapports de performance :
    - `python scripts/export_chroma_perf_report.py`
    - `python scripts/export_observability_weekly.py`
  - Relancez les benchmarks ciblés :
    - `python scripts/benchmark_baseline.py --scenario A|B|C|D`
    - `pytest -m perf`
- **Analyse** :
  - Comparez les rapports `latest_local.json` vs `baseline_local.json`
  - Identifiez les métriques hors seuil (voir docs/performances.md)
  - Vérifiez les changements récents (git log, tracker)

## 3. Remédiation
- **Rollback rapide** :
  - Désactivez les features récentes via feature flags dans `.env` ou `src/config.py` :
    - `rag_backpressure_enabled`, `rag_answer_cache_enabled`, etc.
  - Si besoin, revert le commit fautif (`git revert ...`)
- **Restauration** :
  - Redémarrez le service/Stack
  - Re-indexez si nécessaire
  - Revalidez avec les benchmarks/tests

## 4. Documentation & Communication
- Documentez l’incident dans le tracker (ticket, changelog)
- Ajoutez un résumé dans ce runbook (section incidents)
- Prévenez l’équipe concernée

---

## Incidents récents

| Date       | Symptôme         | Cause racine      | Action         | Résultat |
|------------|------------------|-------------------|----------------|----------|
|            |                  |                   |                |          |

---

*Voir aussi : docs/performances.md, scripts/validate_local.sh, tests/test_rag.py, tests/test_chroma_store.py*
