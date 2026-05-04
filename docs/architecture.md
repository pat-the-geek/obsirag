# Architecture ObsiRAG

Ce document décrit l'architecture effective du dépôt, les frontières entre modules, et les invariants utiles avant toute évolution du code. Les diagrammes de séquence détaillés des flux runtime sont dans [`docs/sequence.md`](sequence.md).

## Vue d'ensemble

ObsiRAG repose sur cinq blocs principaux :

1. `ServiceManager` orchestre le cycle de vie global.
2. `ChromaStore` fournit l'index vectoriel et les accès de récupération.
3. `RAGPipeline` résout les requêtes utilisateur en séparant désormais mieux retrieval et prompting.
4. `AutoLearner` traite les notes en arrière-plan pour produire insights, synapses et synthèses.
5. Le backend FastAPI et le client Expo exposent le chat, la recherche web, le graphe, les insights et le visualiseur de notes.

## Flux principal

### Démarrage

En exploitation locale, les points d'entrée opératoires sont désormais :

1. `./install_service.sh` pour installer le worker `launchd` persistant `com.obsirag.autolearn`,
2. `./start.sh` pour démarrer l'API FastAPI et l'interface Expo web,
3. `./stop.sh` pour arrêter uniquement l'API et Expo,
4. `./status.sh` pour vérifier l'état du worker, de l'API et de l'UI.

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
6. le backend enrichit la réponse avec les contextes d'entités NER et, si le coffre est insuffisant, une synthèse de recherche web,
7. `RAGPipeline` normalise la sortie et applique les garde-fous.

Précision importante sur le NER conversationnel :

- l'extraction ne porte pas seulement sur la question utilisateur, mais sur le texte combiné question + réponse,
- la résolution d'entités tente d'abord un appariement avec WUDD.ai pour stabiliser les noms, types et images,
- un fallback spaCy complète les entités absentes de WUDD.ai,
- chaque entité peut être reliée à des notes du coffre et à une ligne de preuve dans une source candidate,
- le backend produit ensuite une explication courte de la relation entre l'entité détectée et le sujet traité,
- ces données sont retournées dans `entityContexts` pour l'UI Expo et les autres consommateurs API.

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

### API FastAPI et client Expo

Responsabilité : exposer les capacités produit réellement utilisées dans le flux courant.

À préserver :

- FastAPI reste la façade unique pour les conversations, le statut système, le graphe, les notes, les insights et la recherche web,
- Expo reste une couche de présentation et d'interaction, sans logique RAG embarquée,
- les réponses de conversation peuvent transporter des sources, une note principale, un `queryOverview`, des `entityContexts` et une provenance explicite,
- `entityContexts` doit rester le conteneur de référence pour les enrichissements NER du chat: type, notes liées, image éventuelle, ligne de preuve, explication de relation et connaissances web compactes,
- le graphe doit rester filtrable côté backend par texte, dossier, tag, type et profondeur de sous-graphe.

### UI Streamlit héritée, hot reload et stratégie d'import

Responsabilité : documenter et maintenir la surface historique encore présente dans le dépôt, sans la confondre avec le point d'entrée produit principal qui est désormais le couple FastAPI + Expo.

Cette section ne décrit donc qu'un besoin de maintenance de compatibilité pour les modules UI hérités encore présents dans le dépôt.

Constat pratique : en développement, Streamlit peut conserver un état de modules intermédiaire lors d'un hot reload. Cela peut produire des `ImportError` transitoires sur des imports nommés depuis des modules UI récemment modifiés, alors même qu'un import Python propre fonctionne hors runtime Streamlit.

Conventions retenues :

- pour les pages Streamlit qui consomment plusieurs helpers d'un même module UI en évolution rapide, préférer `from src.ui import module_x` puis `module_x.helper(...)` plutôt que multiplier les imports nommés,
- extraire les générateurs HTML purs ou helpers de rendu testables dans de petits modules sans effet de bord de page,
- éviter d'importer au niveau module des dépendances qui déclenchent du runtime lourd si elles ne sont utiles qu'au rendu,
- centraliser les contournements Streamlit sensibles dans des helpers partagés comme `html_embed` ou les helpers Mermaid pour réduire la surface de reload fragile.

Contournements déjà appliqués :

- la page Cerveau s'appuie sur un import de module `brain_explorer` plutôt que sur plusieurs imports nommés,
- les embeds HTML Streamlit sont centralisés dans `src/ui/html_embed.py`,
- le rendu Mermaid du visualiseur de note est sorti dans un helper pur afin d'être testable sans charger toute la page Streamlit,
- `src/ui/services_cache.py` invalide désormais le singleton si le runtime conserve une instance `chroma` ne portant plus les helpers attendus.

### Protocole opératoire hot reload Streamlit

Quand une page Streamlit héritée casse juste après un refactor alors que l'import Python direct fonctionne, suivre cette séquence dans cet ordre :

1. vérifier si le code source expose bien le helper ou symbole attendu via une lecture directe du fichier concerné,
2. confirmer si l'erreur n'existe qu'en runtime Streamlit en comparant avec un import Python hors UI,
3. consulter `logs/obsirag.log` pour distinguer une vraie régression source d'un objet singleton obsolète encore en mémoire,
4. si l'erreur pointe un helper Chroma ou UI récemment ajouté, privilégier la reconstruction des services plutôt qu'un débogage métier prématuré.

Procédure locale recommandée :

1. exécuter `./scripts/validate_local.sh` pour enchaîner redémarrage contrôlé, tests UI ciblés et lecture rapide des logs,
2. recharger ensuite la page Streamlit en cause,
3. en cas d'évolution code significative, compléter avec `source .venv/bin/activate && pytest --no-cov`.

Chaîne standard de validation locale post-changement :

1. `./scripts/validate_local.sh`
2. `source .venv/bin/activate && pytest --no-cov` (optionnel en validation complète)

Variante exhaustive :

1. `./scripts/validate_local.sh --full`

Variante smoke (boucle de dev rapide) :

1. `./scripts/validate_local.sh --smoke`

Variante nrt (non-régression ultra-courte, 7 tests marqués `@pytest.mark.nrt`) :

1. `./scripts/validate_local.sh --nrt`
2. `./scripts/validate_local.sh --nrt --no-restart`

Variante exhaustive sans redémarrage :

1. `./scripts/validate_local.sh --full --no-restart`

Variante smoke sans redémarrage :

1. `./scripts/validate_local.sh --smoke --no-restart`

Sorties machine-readable :

- chaque run de `validate_local.sh` génère un rapport JUnit (`*.junit.xml`) et un résumé JSON (`*.json`) dans `logs/validation/`,
- des alias stables `latest.junit.xml` et `latest.json` sont maintenus pour les scripts externes,
- le dossier de sortie est configurable via `--report-dir <DIR>`.

Signaux utiles de diagnostic :

- si l'import Python direct voit la nouvelle méthode mais que Streamlit signale encore `AttributeError`, suspecter d'abord un objet mis en cache,
- si `services_cache` déclenche une reconstruction et qu'un second rendu passe, conserver la correction côté compatibilité plutôt qu'ajouter un contournement spécifique de page,
- si l'erreur mentionne qu'une clé `st.session_state` ne peut plus être modifiée après instanciation d'un widget, déplacer la mutation dans un callback `on_click` ou `on_change`, ou l'exécuter avant la création du widget,
- si l'erreur persiste après redémarrage complet, traiter alors le problème comme une régression source classique.

### `src/database/chroma_store.py`

Responsabilité : unique façade d'accès au store vecteurs (LanceDB/ChromaDB).

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
3. Les accès au store vecteurs restent derrière l'interface `VectorStore` autant que possible.
4. Les composants extraits doivent rester remplaçables sans changer les API des classes principales.
5. Chaque refactor structurel doit rester couvert par un `pytest` complet, la couverture minimale du dépôt restant à 90%.

## Prochaines évolutions naturelles

1. Extraire un sous-système dédié pour les caches WUDD.ai et géocodage.
2. Rapprocher encore les compatibilités de mocks des API publiques Chroma pour supprimer les derniers fallback internes côté RAG.
3. Ajouter un document de séquence simplifié entre UI, ServiceManager, RAG et AutoLearner.
