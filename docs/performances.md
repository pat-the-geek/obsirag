# Performances — ObsiRAG

Ce document couvre les performances mesurées de l'Auto-learner et les recommandations matérielles pour une utilisation optimale.

---

## MLX vs Ollama — Comparaison mesurée sur Mac M5 16GB

> Données issues des logs `tokens.log` (3 353 appels LLM, du 2026-04-04 au 2026-04-10).
> Matériel : **Apple M5 16GB** — même modèle de base **Qwen 2.5 7B** sur les deux backends.
> Méthode : durée mesurée = écart horodaté entre deux appels LLM consécutifs du même backend (fenêtre 5–300 s pour exclure les pauses longues et les sessions mortes).

### Chronologie des modèles testés

| Période | Backend | Modèle | Appels |
| --- | --- | --- | --- |
| 04-04 → 04-07 | **MLX** | `google/gemma-4-e4b` | 1 696 |
| 04-07 → 04-08 | **Ollama** | `gemma3:4b` | 418 |
| 04-08 → 04-10 | **Ollama** | `qwen2.5:7b` | 983 |
| 04-10 | **MLX** | `mlx-community/Qwen2.5-7B-Instruct-4bit` | 246 |

La comparaison équitable ci-dessous porte sur **Qwen 2.5 7B** (même poids de base, quantisation 4-bit sur les deux backends).

---

### Vitesse de génération par opération (tok/s en sortie)

> Tous les chiffres sont des moyennes sur les échantillons mesurés.

| Opération | Ollama `qwen2.5:7b` | MLX `Qwen2.5-7B-4bit` | Gain MLX |
| --- | --- | --- | --- |
| `autolearn_questions` | 8,5 tok/s | **14,2 tok/s** | **+67 %** |
| `autolearn_enrich` | 14,1 tok/s | **18,7 tok/s** | **+33 %** |
| `autolearn_web_synthesis` | 11,0 tok/s | **16,3 tok/s** | **+48 %** |
| `rag_query` | 6,1 tok/s | **12,6 tok/s** | **+107 %** |
| `autolearn_semantic_field` | 0,4 tok/s | **2,7 tok/s** | **+575 %** † |

† Seulement 5 échantillons MLX pour `semantic_field` — à confirmer.

---

### Durée mesurée par opération (wall-clock)

| Opération | n Ollama | Durée Ollama | n MLX | Durée MLX | Gain MLX |
| --- | --- | --- | --- | --- | --- |
| `autolearn_questions` | 72 | 19,8 s | 25 | **11,6 s** | **–41 %** |
| `autolearn_enrich` | 176 | 62,8 s | 61 | **46,0 s** | **–27 %** |
| `autolearn_web_synthesis` | 62 | 50,6 s | 23 | **40,7 s** | **–20 %** |
| `rag_query` | 313 | 62,3 s | 86 | **36,4 s** | **–42 %** |
| `autolearn_semantic_field` | 52 | 123,7 s | 5 | **21,4 s** | **–83 %** † |
| `autolearn_rename` | 12 | 7,8 s | — | ~7 s | ≈ |

---

### Tokens générés par appel (verbosité / complétude)

La quantisation 4-bit sur les deux backends produit une verbosité comparable pour le même modèle :

| Opération | Completion Ollama | Completion MLX | Δ |
| --- | --- | --- | --- |
| `autolearn_questions` | 168 tok | 165 tok | ≈ |
| `autolearn_enrich` | 885 tok | 862 tok | ≈ |
| `autolearn_web_synthesis` | 555 tok | **662 tok** | +19 % |
| `rag_query` | 383 tok | **460 tok** | +20 % |

Les réponses MLX sont légèrement plus complètes sur les opérations synthèse/RAG — probablement un artefact du chat template appliqué nativement par `mlx_lm`.

---

### Estimation du temps par note (pipeline Auto-learner complet)

Pipeline d'une note = questions + 3 × RAG + enrichissement + synthèse web + renommage + champ sémantique + fetch web (~60 s fixe).

| Étape | Ollama `qwen2.5:7b` | MLX `Qwen2.5-7B-4bit` |
| --- | --- | --- |
| `autolearn_questions` | 20 s | 12 s |
| 3 × `rag_query` | 187 s | **109 s** |
| `autolearn_enrich` | 63 s | **46 s** |
| `autolearn_web_synthesis` | 51 s | **41 s** |
| `autolearn_rename` | 8 s | 7 s |
| `autolearn_semantic_field` | 124 s | **21 s** |
| Fetch web (fixe) | 60 s | 60 s |
| **Total estimé** | **~513 s (~8,5 min)** | **~296 s (~4,9 min)** |
| **Débit (3 notes/cycle)** | **~25,5 min/cycle** | **~14,8 min/cycle** |
| **100 notes** | **~850 min (~14 h)** | **~490 min (~8 h)** |

> Le gain de **~45 %** sur la durée totale est principalement dû au `rag_query` (×2 plus rapide) et au `semantic_field` (×6 plus rapide).

---

### Particularités architecturales

| Aspect | Ollama | MLX |
| --- | --- | --- |
| **Démarrage** | Instantané (serveur toujours actif) | 30–60 s de chargement au lancement |
| **Isolation** | Serveur HTTP séparé (`localhost:11434`) | In-process (pas de nœud réseau) |
| **Mémoire** | Gérée par Ollama (swap auto) | Unified Memory macOS, contrôle direct |
| **GPU/ANE** | Metal (via llama.cpp) | Metal natif via `mlx` |
| **Streaming** | Via SSE (OpenAI-compat.) | Via générateur Python natif |
| **Multi-modèle** | Swap automatique entre modèles | Un seul modèle chargé à la fois |
| **Qualité quant.** | GGUF Q4_K_M (llama.cpp) | MLX 4-bit (format natif Apple) |

---

### Recommandation

**Sur Mac M5 16GB, MLX est préférable** pour l'Auto-learner d'ObsiRAG :

- **+67 %** de vitesse sur la génération de questions
- **+107 %** sur les requêtes RAG (l'opération la plus fréquente)
- **–45 %** sur la durée totale par note (~5 min vs ~8,5 min)
- Latence réseau nulle (pas de serveur HTTP intermédiaire)

Ollama reste utile pour **tester rapidement** un nouveau modèle (pas de rechargement) ou pour faire tourner **plusieurs modèles en parallèle** (swap automatique).

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

---

## Notes

- Les tok/s sont mesurés en **génération** (decode), pas en prefill.
- Les durées ObsiRAG incluent les pauses configurées entre les appels LLM (`_SLEEP_BETWEEN_NOTES`, `_SLEEP_BETWEEN_QUESTIONS`) pour ne pas saturer Ollama.
- La recherche web (DDG + fetch URLs) prend ~30–45s par question, indépendamment du matériel.
- Les embeddings (`nomic-embed-text` via Ollama) s'exécutent sur le Metal/ANE du Mac. L'indexation initiale d'un coffre de 176 notes prend ~4 min à ~29 chunks/s.
