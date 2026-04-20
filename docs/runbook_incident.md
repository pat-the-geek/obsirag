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

### Incident frontend web exporte

Si l'incident concerne une page blanche, un bootstrap web Expo bloque ou une regression d'artefact statique :

```bash
cd obsirag-expo
npm run test:web-export
```

Ce test permet de distinguer rapidement :

- un export casse,
- une erreur console au demarrage,
- un `#root` qui ne rend rien,
- ou un shell de preboot qui ne se masque jamais.

En cas d'echec, conserver dans le ticket :

- le message d'assertion exact,
- la derniere erreur console ou page error remontee,
- et le `root snapshot` final quand il est present.

### Incident app bloquee sur Reglages backend

Si l'application web reste sur `server-config` alors que le backend semble sain :

1. verifier la session backend :

```bash
curl -sS http://127.0.0.1:8000/api/v1/session
curl -sS -X POST http://127.0.0.1:8000/api/v1/session
```

Le cas nominal pour un runtime ouvert est un payload contenant `authenticated=true`, `requiresAuth=false` et un `backendUrlHint` coherent.

2. verifier que le frontend exporte le bon bundle :

```bash
cd obsirag-expo
npm run web:export
cd ..
./stop.sh
./start.sh
curl -sS http://127.0.0.1:8000/ | grep -o '_expo/static/js/web/entry-[A-Za-z0-9]*\.js' | head -n 1
```

3. si le serveur sert bien le dernier bundle mais que le navigateur affiche encore `server-config`, faire un hard refresh ou vider les donnees du site pour eliminer un cache stale.

4. si le blocage persiste apres reload, verifier que l'acces manuel depuis `Settings` n'utilise pas un lien volontaire avec `allowStay=1`, ce qui desactive l'auto-sortie de l'ecran.

5. en cas de doute sur la configuration provider, verifier aussi que `EURIA_URL` et `EURIA_BEARER` sont correctement charges si le fil utilise Euria.

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

## Voir aussi

- `docs/performances.md`
- `scripts/validate_local.sh`
- `tests/test_rag.py`
- `tests/test_chroma_store.py`
