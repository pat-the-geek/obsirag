# Performances — ObsiRAG

Ce document couvre les performances mesurées de l'Auto-learner et les recommandations matérielles pour une utilisation optimale.

---

## Ollama — Référence actuelle sur Mac M5 16GB

> Données de référence issues des mesures conservées pour le backend Ollama actuellement utilisé par ObsiRAG.
> Matériel : **Apple M5 16GB**.
> Modèle de base recommandé : **`qwen2.5:7b`**.

### Résumé rapide

- **Backend courant** : Ollama local (`OLLAMA_BASE_URL`)
- **Modèle chat recommandé** : `qwen2.5:7b`
- **Modèle d'embedding recommandé** : `nomic-embed-text`
- **Ordre de grandeur du pipeline Auto-learner** : **~8 à 12 min par note** sur cette machine

### Particularités du backend Ollama

| Aspect | Ollama |
| --- | --- |
| **Isolation** | Serveur HTTP local (`localhost:11434`) |
| **Streaming** | Via SSE / API compatible OpenAI |
| **GPU/ANE** | Accélération Metal via le runtime local |
| **Multi-modèle** | Changement de modèle simple via `ollama pull` / `OLLAMA_CHAT_MODEL` |
| **Embeddings** | `OLLAMA_EMBED_MODEL` possible, sinon fallback CPU |

### Recommandation actuelle

**Sur Mac M5 16GB, `qwen2.5:7b` reste le meilleur défaut pragmatique** pour ObsiRAG : qualité correcte en français, compatibilité simple avec le pipeline chat/RAG et disponibilité immédiate via Ollama.

---

## Mesures de référence (Mac M5 16GB)

Matériel de test : **Apple M5 16GB** — modèle Ollama : `gemma3:4b`

### Temps de traitement par note (flux web-first)

| Étape | Durée mesurée |
| --- | --- |
| Génération des 3 questions (LLM) | ~90s |
| Recherche DDG par question | ~3s |
| Fetch et nettoyage de 4 URLs | ~30s |
| Synthèse LLM des sources web | ~60–90s |
| Pause entre questions (× 2) | 30s |
| Pause après la note | 30s |
| **Total par note** | **~8–12 min** |

### Débit du cycle Auto-learner (configuration par défaut)

| Paramètre | Valeur par défaut |
| --- | --- |
| `AUTOLEARN_FULLSCAN_PER_RUN` | 3 notes/cycle |
| `AUTOLEARN_INTERVAL_MINUTES` | 60 min |
| **Débit effectif** | **~3 notes/heure** |

### Projection sur un coffre complet

| Taille du coffre | Durée estimée (M5 16GB) |
| --- | --- |
| 50 notes | ~17h |
| 100 notes | ~35h |
| 200 notes | ~70h (~3 jours) |
| 500 notes | ~175h (~7 jours) |

> Le traitement est **progressif et résumable** : en cas d'interruption (redémarrage, coupure), le scan reprend automatiquement là où il s'était arrêté grâce au fichier `processed_notes.json`.

---

## Optimisation de la configuration

Pour accélérer le scan sans changer de matériel, modifier `.env` :

```env
# Passer de 3 à 5 notes par cycle
AUTOLEARN_FULLSCAN_PER_RUN=5

# Réduire l'intervalle entre les cycles
AUTOLEARN_INTERVAL_MINUTES=30
```

Gain estimé : **÷ 2 sur la durée totale** (35h → ~17h pour 100 notes).

Limite : Ollama est sollicité en continu — le Mac reste moins disponible pour d'autres usages.

---

## Recommandations matérielles Apple Silicon

Le goulot d'étranglement principal n'est pas le CPU mais la **bande passante mémoire unifiée** : les LLM chargent leurs poids depuis la RAM à chaque token généré. Plus la RAM est grande et rapide, plus les modèles sont qualitatifs et les tokens/s élevés.

### Tableau comparatif

| Modèle | RAM | Bande passante | Tok/s estimés (7B Q4) | Modèles accessibles | Verdict |
| --- | --- | --- | --- | --- | --- |
| M5 16GB *(actuel)* | 16GB | ~120 GB/s | ~40–60 tok/s | 7B Q4 max | Limité |
| M4 Pro 24GB | 24GB | ~273 GB/s | ~80–100 tok/s | 7B–13B Q6/Q8 | Bon rapport qualité/prix |
| **M4 Pro 48GB** | **48GB** | **~273 GB/s** | **~90–110 tok/s** | **7B–30B Q6/Q8** | **Polyvalent recommandé** |
| M4 Max 48GB | 48GB | ~400 GB/s | ~120–150 tok/s | 7B–30B Q6/Q8 | Meilleur en vitesse |
| M4 Max 128GB | 128GB | ~400 GB/s | ~130–160 tok/s | Jusqu'à 70B | Usage intensif |

> **Le seuil de confort est 48GB.** Passer de 16 à 24GB reste frustrant car les modèles 14B Q8 passent à peine. À 48GB, les modèles 13B–30B sont accessibles en qualité complète.

### Impact sur ObsiRAG

| Matériel | Temps/note estimé | 100 notes | Modèle recommandé |
| --- | --- | --- | --- |
| M5 16GB *(actuel)* | ~10 min | ~35h | Gemma 4 Q4 / Qwen2.5 7B Q4 |
| M4 Pro 48GB | ~4–5 min | ~15h | Qwen2.5 14B Q6, Mistral 12B Q8 |
| M4 Max 48GB | ~3–4 min | ~12h | Qwen2.5 14B Q8, Llama 3.1 70B Q2 |

### Modèles Ollama recommandés par configuration

| RAM | Modèle recommandé | Qualité | Tok/s attendus |
| --- | --- | --- | --- |
| 16GB | `gemma3:4b` | Bonne | 40–60 |
| 16GB | `qwen2.5:7b` | Bonne | 50–70 |
| 24GB | `qwen2.5:14b` | Très bonne | 40–60 |
| 48GB | `qwen2.5:14b-instruct-q6_K` | Excellente | 60–80 |
| 48GB | `mistral-nemo:12b` | Excellente | 70–90 |
| 128GB | `qwen2.5:72b` | Maximale | 30–50 |

### Validation de performance reproductible

Le script versionné pour mesurer le backend actuel est `scripts/benchmark_ollama_chat20.py`.

```bash
python scripts/benchmark_ollama_chat20.py
```

---

## Notes

- Les tok/s sont mesurés en **génération** (decode), pas en prefill.
- Les durées ObsiRAG incluent les pauses configurées entre les appels LLM (`_SLEEP_BETWEEN_NOTES`, `_SLEEP_BETWEEN_QUESTIONS`) pour ne pas saturer Ollama.
- La recherche web (DDG + fetch URLs) prend ~30–45s par question, indépendamment du matériel.
- Les embeddings (`nomic-embed-text` via Ollama) s'exécutent sur le Metal/ANE du Mac. L'indexation initiale d'un coffre de 176 notes prend ~4 min à ~29 chunks/s.

---

## Optimisations runtime recentes (scans et I/O)

En plus des performances LLM, plusieurs optimisations ciblent la reduction des rescans filesystem et des lectures fragiles :

- `ChromaStore` maintient un snapshot derive cache de `list_notes()`. Les vues `count_notes`, dossiers, tags, tris, filtrage par type, notes user/generees et backlinks reutilisent la meme base au lieu de recalculer chacune un parcours complet.

- `find_existing_insight()` (auto-learner) privilegie `list_insight_notes()` quand la vue Chroma est disponible. Le scan disque `rglob("*.md")` n'est plus le chemin principal.

- `note_renamer` met a jour les wikilinks en priorite depuis la liste de notes indexees (`_chroma.list_notes`). Le scan complet du coffre reste seulement un fallback de securite.

- Une couche commune `safe_read` uniformise la lecture defensive de fichiers textes/JSON. Moins d'exceptions runtime liees aux fichiers absents, archives ou temporairement invalides.

### Mesures de non-régression — vues dérivées de `list_notes()` (store vecteurs éphémère, Mac M5 16GB)

> Mesures issues de `TestChromaPerformance` / `TestChromaDerivedViewsNonRegression` dans `tests/test_chroma_store.py`.
> Store vecteurs en mémoire, embedding mocké — les chiffres reflètent la seule logique Python, sans I/O disque ni réseau.
> Seuils calibrés local/CI : les bornes sont strictes en local et assouplies automatiquement en CI via un facteur de robustesse pour limiter les faux positifs de timing.

| Opération | Données | Durée mesurée | Seuil garanti |
| --- | --- | --- | --- |
| `_build_note_views()` (construction snapshot) | 500 notes | < 5 ms | < 200 ms |
| Helper dérivé (cache hit) | 200 notes, 200 appels | ~0,5 µs/appel | < 100 µs/appel |
| 9 helpers dérivés successifs (cache hit) | 100 notes | < 0,1 ms total | < 0,5 ms total |
| `list_notes()` invoqué pour N helpers dérivés | N = 9 helpers | **1 seul appel** | = 1 (non-régression) |
| `list_notes()` invoqué après `invalidate_list_notes_cache()` | — | **1 rebuild** | = 1 (non-régression) |

**Interprétation :**

- La construction du snapshot pour 500 notes prend moins de 5 ms en pratique (seuil fixé à 200 ms pour absorber la variabilité d'autres machines).
- En cache hit, chaque appel à une vue dérivée (`count_notes`, `list_note_tags`, `get_backlinks`, etc.) coûte moins de 1 µs.
- La propriété de non-régression critique est garantie par test : `list_notes()` est invoqué **exactement une fois** quel que soit le nombre de helpers enchaînés dans le même cycle TTL.

### Instrumentation runtime des fallbacks filesystem

Pour objectiver le caractère exceptionnel des rescans disque, les chemins fallback des composants learning exposent désormais des compteurs/latences :

- `autolearn_fs_fallback_insight_glob_total`
- `autolearn_fs_fallback_insight_glob_seconds`
- `autolearn_fs_fallback_insight_rglob_total`
- `autolearn_fs_fallback_insight_rglob_seconds`
- `autolearn_fs_fallback_rename_rglob_total`
- `autolearn_fs_fallback_rename_rglob_seconds`

Ces métriques permettent de vérifier en exploitation locale que les chemins indexés restent nominaux et que les rescans complets (`rglob`) demeurent rares.

### Export comparatif automatisé local/CI (Chroma)

- Script dédié : `scripts/export_chroma_perf_report.py`.
- Exporte un rapport horodaté dans `stats/chroma_perf_reports/` avec:
  - mesures micro-bench (`build_note_views_ms`, `cache_hit_us`, `nine_helpers_ms`),
  - seuils appliqués selon le contexte local/CI,
  - statut pass/fail par métrique.
- Maintient les pointeurs `latest_local.json`, `latest_ci.json`, `latest.json` et un comparatif `latest_comparison.md` quand les deux environnements sont disponibles.
- Intégré au flux `scripts/validate_local.sh` (non bloquant) pour garder une trace continue des tendances de performance.

Impact mesuré :

- baisse de la charge I/O pendant les cycles auto-learner,
- meilleure prédictibilité de latence côté UI,
- réduction des régressions liées aux états de fichiers transitoires.
