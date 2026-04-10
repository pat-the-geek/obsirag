# Performances — ObsiRAG

Ce document couvre les performances mesurées de l'Auto-learner et les recommandations matérielles pour une utilisation optimale.

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
