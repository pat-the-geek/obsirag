# Architecture ObsiRAG

Ce document décrit l'architecture effective du dépôt, les frontières entre modules, et les invariants utiles avant toute évolution du code.

## Vue d'ensemble

ObsiRAG repose sur cinq blocs principaux :

1. `ServiceManager` orchestre le cycle de vie global.
2. `ChromaStore` fournit l'index vectoriel et les accès de récupération.
3. `RAGPipeline` résout les requêtes utilisateur en séparant désormais mieux retrieval et prompting.
4. `AutoLearner` traite les notes en arrière-plan pour produire insights, synapses et synthèses.
5. L'UI Streamlit expose le chat, le graphe, les insights et le visualiseur de notes.

## Flux principal

### Démarrage

`src/services.py` initialise, dans cet ordre :

1. les répertoires de données,
2. `ChromaStore`,
3. le modèle MLX,
4. `RAGPipeline`,
5. `IndexingPipeline`,
6. `GraphBuilder`,
7. `AutoLearner`,
8. `VaultWatcher`.

Le `ServiceManager` lance ensuite :

- le watcher filesystem,
- l'indexation initiale,
- le watchdog de déchargement du modèle,
- et, si activé, l'auto-learner.

### Requête chat

Une requête suit ce chemin :

1. l'UI transmet la question à `RAGPipeline`,
2. `RAGPipeline` résout la question dans le fil si nécessaire,
3. `RetrievalStrategy` choisit une stratégie de récupération,
4. `AnswerPrompting` prépare le contexte et les messages,
5. le backend MLX produit une réponse,
6. `RAGPipeline` normalise la sortie et applique les garde-fous.

### Auto-apprentissage

Un cycle `AutoLearner` suit ce chemin :

1. sélection des notes à traiter,
2. génération d'une question ciblée,
3. récupération éventuelle d'un contexte web,
4. synthèse via LLM,
5. écriture ou enrichissement d'un insight,
6. découverte facultative de synapses,
7. persistance des statuts et métriques.

## Frontières de modules

### `src/services.py`

Responsabilité : orchestration runtime uniquement.

À préserver :

- ne pas y remettre de logique métier RAG ou autolearn,
- garder les composants injectés une seule fois,
- conserver le rôle de point d'entrée unique côté UI.

### UI Streamlit, hot reload et stratégie d'import

Responsabilité : garder les pages Streamlit robustes malgré les rechargements partiels du runtime.

Constat pratique : en développement, Streamlit peut conserver un état de modules intermédiaire lors d'un hot reload. Cela peut produire des `ImportError` transitoires sur des imports nommés depuis des modules UI récemment modifiés, alors même qu'un import Python propre fonctionne hors runtime Streamlit.

Conventions retenues :

- pour les pages Streamlit qui consomment plusieurs helpers d'un même module UI en évolution rapide, préférer `from src.ui import module_x` puis `module_x.helper(...)` plutôt que multiplier les imports nommés,
- extraire les générateurs HTML purs ou helpers de rendu testables dans de petits modules sans effet de bord de page,
- éviter d'importer au niveau module des dépendances qui déclenchent du runtime lourd si elles ne sont utiles qu'au rendu,
- centraliser les contournements Streamlit sensibles dans des helpers partagés comme `html_embed` ou les helpers Mermaid pour réduire la surface de reload fragile.

Contournements déjà appliqués :

- la page Cerveau s'appuie sur un import de module `brain_explorer` plutôt que sur plusieurs imports nommés,
- les embeds HTML Streamlit sont centralisés dans `src/ui/html_embed.py`,
- le rendu Mermaid du visualiseur de note est sorti dans un helper pur afin d'être testable sans charger toute la page Streamlit.

### `src/database/chroma_store.py`

Responsabilité : unique façade d'accès à ChromaDB.

À préserver :

- les couches supérieures ne doivent pas dépendre directement de `_collection`,
- les accès spécifiques aux chunks liés doivent passer par des méthodes explicites,
- la récupération d'erreurs/corruptions reste localisée ici.

### `src/ai/rag.py`

Responsabilité : coordination de requête, normalisation et politique de réponse.

Sous-composants extraits :

- `src/ai/retrieval_strategy.py` : sélection et combinaison des stratégies de récupération,
- `src/ai/answer_prompting.py` : préparation du contexte, enrichissement des notes liées, construction des prompts.

À préserver :

- `RAGPipeline` garde les wrappers publics utilisés par les tests et les call sites,
- les helpers extraits ne doivent pas modifier les contrats de `query()` et `query_stream()`,
- les garde-fous de type sentinel restent centralisés dans `RAGPipeline`.

### `src/learning/autolearn.py`

Responsabilité : orchestration des cycles d'auto-apprentissage.

Sous-composants extraits :

- `src/learning/artifact_writer.py` : création et mise à jour des insights,
- `src/learning/web_enrichment.py` : récupération web, synthèse et enrichissement,
- `src/learning/synapse_discovery.py` : découverte et écriture des synapses.

À préserver :

- `AutoLearner` reste le point d'entrée du scheduler,
- les méthodes internes historiques sont conservées comme façade pour les tests,
- les écritures d'état passent par l'adaptateur JSON commun.

### `src/storage/json_state.py`

Responsabilité : persistance JSON/JSONL simple, atomique et réutilisable.

Usage actuel :

- notes traitées,
- temps de traitement,
- statut d'auto-learner,
- journal de requêtes utilisateur,
- statut d'indexation du `ServiceManager`.

## Observabilité

`src/metrics.py` centralise maintenant des métriques métier persistées dans `data/stats/metrics.json`.

Métriques actuellement produites :

- `rag_queries_total`,
- `rag_sentinel_answers_total`,
- `rag_context_retries_total`,
- `autolearn_cycle_seconds`,
- `autolearn_notes_skipped_total`,
- `autolearn_insights_created_total`,
- `autolearn_insights_appended_total`,
- `autolearn_web_search_fallback_total`,
- `autolearn_web_search_error_total`.

Ces métriques sont volontairement simples : elles servent d'abord à objectiver le comportement du produit avant une éventuelle exportation vers un backend de monitoring plus riche.

## Invariants importants

1. Les notes utilisateur ne doivent jamais être modifiées hors fonctionnalités explicitement prévues.
2. Les réponses RAG ne doivent jamais dépendre de connaissances hors contexte fourni.
3. Les accès ChromaDB spécifiques restent derrière `ChromaStore` autant que possible.
4. Les composants extraits doivent rester remplaçables sans changer les API des classes principales.
5. Chaque refactor structurel doit rester couvert par un `pytest` complet, la couverture minimale du dépôt restant à 90%.

## Prochaines évolutions naturelles

1. Extraire un sous-système dédié pour les caches WUDD.ai et géocodage.
2. Rapprocher encore les compatibilités de mocks des API publiques Chroma pour supprimer les derniers fallback internes côté RAG.
3. Ajouter un document de séquence simplifié entre UI, ServiceManager, RAG et AutoLearner.
