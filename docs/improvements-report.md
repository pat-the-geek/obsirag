# Rapport des travaux d'amelioration

Ce document suit les ameliorations recentes appliquees a ObsiRAG, leur portee fonctionnelle et leur niveau de validation.

## Mise a jour du 2026-04-12 (suite)

### Correction bug accumulation _archive_ sur les insights

- `find_existing_insight` dans `artifact_writer.py` parcourait tous les `.md` avec `rglob`, y compris les fichiers deja archives (`_archive_YYYYMMDD_HHMMSS`).
- Comme leur stem commence toujours par le meme prefixe que l'insight source, ils etaient selectionnes comme "existants", recevaient du contenu supplementaire, puis etaient archives a nouveau, generant une accumulation infinie de suffixes `_archive_`.
- Correction : les fichiers dont le stem correspond au motif `_archive_\d{8}_\d{6}` sont desormais exclus de la recherche dans `find_existing_insight`.
- Correction defensive dans `2_Insights.py` : `_read_md_file` capture `FileNotFoundError` et affiche un message neutre au lieu de crasher la page.
- Validation finale de la mise a jour du jour : 509 tests passes, 0 echec.

### Correction affichage sidebar : notes vs chunks

- La sidebar `app.py` appelait `svc.chroma.count()` (nombre de chunks) pour les deux metriques "Notes indexees" et "Chunks vectorises".
- "Notes indexees" appelle desormais `svc.chroma.count_notes()` (methode dediee de ChromaStore).
- La page Parametres supprime son indirection via `chroma_compat.count_notes` et appelle directement `svc.chroma.count_notes()`.

### Extraction sous-systeme cache WUDD.ai et geocodage

- Creation de `src/learning/entity_cache.py` avec deux classes autonomes :
  - `WuddaiCache(data_dir, utc_now_fn, normalize_fn, wuddai_url)` : cache JSON local avec TTL 24 h pour la liste d'entites WUDD.ai, aucune dependance vers AutoLearner.
  - `GeocodeCache(data_dir, normalize_fn)` : cache JSON persistant pour les coordonnees GPS via Wikipedia, aucune dependance vers AutoLearner.
- Refactoring de `entity_services.py` : `load_wuddai_entities` et `fetch_gpe_coordinates` deleguent aux nouveaux objets cache, eliminant la logique HTTP/JSON inline dans la classe.
- 12 nouveaux tests unitaires dans `tests/test_entity_cache.py` couvrant : cache frais, cache expire, ecriture sur disque, fallback reseau, retour None, tentatives fr/en pour Wikipedia.
- Tous les tests existants `test_entity_services.py` (4) et `test_autolearn.py` (3 sur les caches) restent verts.

### Alignement mocks Chroma sur l'API publique

- La fixture `mock_chroma` de `tests/conftest.py` expose desormais toutes les methodes publiques supplementaires de `ChromaStore` : `count_notes`, `list_user_notes`, `list_generated_notes`, `list_recent_notes`, `get_chunks_by_note_title`, `get_chunks_by_file_path`.
- Supprime les dernieres differences entre le mock de base et les stubs attendus par les tests RAG et Settings.

### Sortie complete de `chroma_compat` du depot

- Les pages `1_Brain.py`, `2_Insights.py`, `3_Settings.py`, `4_Note.py` et `app.py` appellent desormais directement les methodes publiques de `ChromaStore` au lieu de passer par `src/ui/chroma_compat.py`.
- `services_cache.py` devient l'unique point de defense contre les objets `chroma` obsoletes conserves par un hot reload Streamlit partiel.
- Le predicat `_is_services_instance_compatible()` verifie maintenant explicitement les methodes requises par le runtime UI : `list_notes_sorted_by_title`, `list_note_folders`, `list_note_tags`, `list_notes_by_type`, `list_recent_notes`, `list_user_notes`, `list_generated_notes`, `count_notes`, `get_backlinks`.
- Le module `src/ui/chroma_compat.py` et ses tests dedies ont ete supprimes du depot.
- `docs/architecture.md` ne documente plus `chroma_compat` comme filet de securite actif.

### Projections derivees et cachees dans `ChromaStore`

- Ajout d'un snapshot derive interne dans `src/database/chroma_store.py` pour centraliser, sur une base cachee commune, les vues construites a partir de `list_notes()`.
- `count_notes`, `list_note_folders`, `list_note_tags`, `list_notes_sorted_by_title`, `list_recent_notes`, `list_notes_by_type`, `list_user_notes`, `list_generated_notes` et `get_backlinks` reutilisent maintenant ce snapshot au lieu de recalculer chacun leur propre parcours.
- `get_notes_by_file_paths` et `get_note_by_file_path` utilisent maintenant un index derive `by_file_path` pour eviter les parcours complets inutiles lors des resolutions par chemin.
- L'invalidation de cache remet a zero a la fois `list_notes()` et les projections derivees.
- Des tests dedies ont ete ajoutes pour verifier la reutilisation d'un snapshot unique et l'invalidation du cache derive.

### Helper commun de lecture defensive

- Ajout de `src/storage/safe_read.py` avec trois points d'entree communs : `read_text_file`, `read_text_lines`, `read_json_file`.
- Les lecteurs centraux UI et storage (`runtime_state_store.py`, `telemetry_store.py`, `conversation_store.py`, `query_history_store.py`, `chat_navigation.py`, `2_Insights.py`, `4_Note.py`, `json_state.py`) utilisent maintenant ce helper.
- Les composants learning et infrastructure les plus exposes (`entity_cache.py`, `artifact_writer.py`, `note_renamer.py`, `synapse_discovery.py`, `indexer/pipeline.py`, `logger.py`) ont ete bascules sur la meme couche defensive.
- La gestion des fichiers absents, archives ou JSON invalides est maintenant plus uniforme entre UI, learning et storage.

### Reduction des scans d'insights cote auto-learner

- `find_existing_insight()` dans `artifact_writer.py` s'appuie maintenant sur `list_insight_notes()` quand Chroma expose deja la vue des insights indexes, au lieu de repartir systematiquement d'un `rglob("*.md")` sur le dossier des artefacts.
- Le fallback filesystem est conserve pour les cas non indexes ou les tests qui ne branchent pas `ChromaStore` complet.
- Un test dedie couvre explicitement ce chemin pour eviter un retour accidentel au scan disque comme comportement principal.
- Optimisation complementaire : quand un candidat matche deja fortement le prefixe de titre attendu, la recherche evite desormais les lectures de frontmatter inutiles pour le scoring NER, ce qui reduit les I/O sur les cycles frequents.
- Le fallback disque privilegie d'abord le layout mensuel standard `insights/YYYY-MM/*.md` via un scan peu profond avant de retomber sur un `rglob` complet si necessaire.

### Reduction des scans de renommage dans le coffre

- `note_renamer.py` privilegie desormais la liste de notes deja indexees (`_chroma.list_notes`) pour mettre a jour les wikilinks, avant de tomber en fallback sur `rglob("*.md")`.
- Le comportement de secours est conserve pour les cas ou l'index n'est pas disponible ou incomplet.
- Un test dedie valide ce chemin "index-first" pour eviter de revenir par inadvertance au scan complet comme chemin nominal.

### Document de sequence simplifie

- Creation de `docs/sequence.md` avec quatre diagrammes Mermaid `sequenceDiagram` :
  - Demarrage de l'application (ServiceManager → ChromaStore, MLX, RAG, AutoLearner, VaultWatcher).
  - Requete chat complete (UI → RAGPipeline → RetrievalStrategy → ChromaStore → AnswerPrompting → MLX).
  - Cycle AutoLearner note par note (EntityServices, EntityCache, QuestionAnswering, WebEnrichment, ArtifactWriter).
  - Evenement VaultWatcher (filesystem → IndexingPipeline → ChromaStore → notification AutoLearner).
- Reference ajoutee dans la premiere ligne de `docs/architecture.md`.

### Rendu HTML et verification visuelle minimale

- Extraction de fragments UI purs dans `src/ui/chat_ui_fragments.py` pour centraliser le rendu des blocs dynamiques du chat (sources, bulle utilisateur, en-tete sidebar, statut de generation).
- Branchage de la page Chat sur ces helpers pour reduire les assemblages HTML inline difficiles a tester.
- Couverture de ces rendus via des tests dedies dans `tests/test_chat_ui_fragments.py`.
- Extension de la meme approche a la page Note via `src/ui/note_ui_fragments.py` (lien Obsidian, entrees de plan et resultats de recherche).
- Couverture de ces nouveaux fragments via `tests/test_note_ui_fragments.py`.
- Extension de l'extraction vers la page Cerveau via `src/ui/brain_ui_fragments.py` (en-tete, rangee de badges, lignes de notes).
- Extraction complementaire d'un helper de rendu pour les notes citees dans l'historique chat (`build_cited_source_row_html`).
- Assertions dediees ajoutees pour ces helpers dans `tests/test_brain_ui_fragments.py` et `tests/test_chat_ui_fragments.py`.
- Poursuite de l'extraction sur les blocs detail restants du Cerveau et du chat pour homogénéiser davantage le rendu via helpers testables.
- Extraction complementaire des assembleurs de presentation du chat vers `src/ui/chat_view_models.py` (navigation, conversations sauvegardees, resume de generation, sources web).
- Extraction du dernier bloc de stats historiques du chat vers `build_message_stats_caption` dans `chat_ui_fragments.py`; la boucle d'historique dans `app.py` utilise desormais ce helper au lieu d'une f-string inline.
- Amelioration UX sur l'attente chat : pendant `query_stream`, la zone de statut affiche maintenant une progression d'activite en temps reel (etapes retrieval + temps ecoule) au lieu d'un message statique "Recherche dans le coffre…".
- Evolution de cette amelioration : la progression est desormais pilotee par des evenements backend reels emis par `RAGPipeline`/`RetrievalStrategy` (intention detectee, mode de retrieval, nombre de passages retenus, preparation prompt, retry contexte), puis consommee par l'UI chat avec affichage du temps ecoule.
- Ajout d'une timeline visible directement dans la conversation pendant la generation : phases `analyse → retrieval → contexte → generation`, avec etat courant et transitions completees en temps reel.
- La timeline est maintenant persistée dans chaque message assistant (expander "Timeline activité" dans l'historique), pour rester visible après la fin de la génération et après rerun Streamlit.
- Renforcement du garde-fou runtime dans `services_cache.py` : la compatibilite de l'instance singleton verifie aussi la signature de `rag.query_stream` (presence de `progress_callback`) pour forcer une reconstruction propre en cas de hot reload partiel vers une instance RAG obsolete.

### Index et acces aux artefacts (suite 2026-04-12)

- Remplacement des derniers comptages filesystem ad hoc du chat par des helpers Chroma specialises (`list_insight_notes()` et `list_synapse_notes()`).
- Renforcement de la page Insights pour prioriser les helpers Chroma specialises (`list_insight_notes()`, `list_synapse_notes()`, `list_report_notes()`) avant fallback generique.
- Ajout d'un point d'entree explicite pour les conversations sauvegardees dans `src/ui/conversation_store.py`, utilise par la navigation chat en remplacement d'un parcours implicite directement porte par la couche UI.
- Ajout d'un point d'entree explicite pour l'historique des requetes dans `src/ui/query_history_store.py`, consomme par la page Insights.
- Uniformisation de la couche d'acces UI non indexee avec tests dedies (`tests/test_conversation_store.py`, `tests/test_query_history_store.py`).
- Extension de la logique de points d'entree explicites aux etats de traitement et aux journaux operationnels via `src/ui/runtime_state_store.py`, consomme par le chat et la page Parametres.
- Extension aux fichiers de telemetry/statistiques via `src/ui/telemetry_store.py`, consomme par la page Parametres pour les tokens et les metriques runtime.
- Ajout de `load_runtime_metrics_last_update()` dans `telemetry_store.py`; la page Parametres supprime son dernier acces direct `.stat().st_mtime` sur le fichier de metriques.

### Exploitation locale (suite 2026-04-12)

- Execution manuelle d'un cycle `./stop.sh && ./start.sh` pour valider la relance apres changements recents.
- Relance confirmee sans erreur bloquante, avec une nouvelle instance active de l'application.
- URL locale de service confirmee: `http://localhost:8501`.
- Ajout du script `scripts/post_restart_check.sh` pour automatiser le controle post-redemarrage (stop/start, verification HTTP 200, lecture rapide des logs).
- Integration du script dans le protocole operatoire et la chaine standard de validation locale documentee (`README.md` et `docs/architecture.md`).
- Ajout de la commande wrapper `scripts/validate_local.sh` pour enchaîner en un seul point d'entree le redemarrage controle, les tests UI cibles et la verification rapide des logs.
- Ajout de la variante `scripts/validate_local.sh --full` pour executer la validation exhaustive dans le meme flux.
- Ajout de l'option `--no-restart` (compatible avec `--full`) pour rejouer les validations sans redemarrage quand seul le code applicatif evolue.
- Ajout du preset `scripts/validate_local.sh --smoke` (compatible avec `--no-restart`) pour une boucle de validation critique plus rapide en phase de dev.
- Ajout d'une sortie machine-readable en fin de validation locale (rapports JUnit XML + resume JSON) avec pointeurs stables `logs/validation/latest.junit.xml` et `logs/validation/latest.json`.
- Ajout de l'option `--report-dir` pour rediriger les artefacts de validation vers un dossier cible (usage CI locale/scripts externes).
- Ajout du preset `--nrt` dans `scripts/validate_local.sh` pour la suite la plus courte possible : 7 tests marques `@pytest.mark.nrt`, couvrant compat Chroma, rendu UI, stores et cache de services.
- Ajout du marqueur `nrt` dans `pytest.ini`; tests annotes directement dans les fichiers de tests concernes.
- Validation complete de la suite apres suppression de `chroma_compat`, ajout du cache derive ChromaStore, introduction de `safe_read` et reduction des rescans cote learning : 513 tests passes.

### Suivi lot performance et robustesse (complement 2026-04-12)

- Audit des rescans markdown restants : les derniers `rglob("*.md")` sont desormais confines a des chemins explicitement bulk/fallback (`indexer/pipeline.py`, fallback de `artifact_writer.py`, fallback de `note_renamer.py`).
- Verification de la mutualisation des lectures defensives : aucun `read_text()` applicatif disperse restant hors `safe_read`; les lectures binaires (`read_bytes`) conservees sont des cas volontaires (hashing/assets).
- Ajout de tests de non-regression sur les vues derivees de `list_notes()` dans `tests/test_chroma_store.py` (snapshot partage, invalidation, coherences inter-helpers).
- Ajout de micro-benchmarks cibles dans `tests/test_chroma_store.py` pour objectiver les performances des helpers derives (`count_notes`, `list_note_tags`, `get_backlinks`, etc.).
- Mise a jour de `docs/performances.md` avec les mesures consolidees de ce lot (construction snapshot, cache hits, enchainement des helpers derives).
- Validation globale post-modifs : 521 tests passes, 0 echec.

### Continuation lot 1/2/3 (complement 2026-04-12)

- Calibration des seuils micro-bench local/CI dans `tests/test_chroma_store.py` : les seuils restent stricts en local et sont adaptes en CI pour reduire les faux positifs lies a la variabilite de machine.
- Instrumentation runtime des fallbacks filesystem dans les parcours learning :
  - `artifact_writer.py` mesure et compte les chemins fallback `glob`/`rglob` de recherche d'insights,
  - `note_renamer.py` mesure et compte le fallback `rglob` de mise a jour des wikilinks.
- Extension de la couverture de non-regression UI/stockage avec des tests explicites "no recursive rescan in nominal path" sur :
  - `tests/test_conversation_store.py` (pas de `rglob` en listage nominal des conversations),
  - `tests/test_chat_navigation.py` (delegation propre du listage sans rescan recursif),
  - `tests/test_insights_browser.py` (parcours indexes sans rescan recursif).
- Renforcement des tests learning sur les fallbacks instrumentes :
  - `tests/test_autolearn.py` valide la remontée de métriques quand `find_existing_insight` doit basculer jusqu'au `rglob`,
  - `tests/test_note_renamer.py` valide la remontée de métriques quand le fallback `rglob` est utilise.
- Validation globale post-modifs : 526 tests passes, 0 echec.

### Continuation lot observabilite Parametres + alerte + export perf (complement 2026-04-12)

- Page Parametres enrichie : affichage explicite des compteurs fallback `autolearn_fs_fallback_*` dans l'onglet metriques runtime.
- Ajout d'une alerte soft sur fenetre glissante configurable :
  - seuils `fallback_alert_window_minutes` et `fallback_alert_rglob_threshold` ajoutes a la configuration,
  - snapshots historiques des compteurs fallback persists dans `stats/fallback_metrics_history.jsonl`,
  - warning non bloquant affiche quand la frequence `rglob` depasse le seuil.
- Observabilite perf Chroma completee par export local/CI automatise :
  - nouveau script `scripts/export_chroma_perf_report.py` (rapport horodate, latest local/ci, comparatif markdown),
  - integration non bloquante dans `scripts/validate_local.sh` avec reference du rapport dans le JSON de sortie,
  - integration UI via bouton d'export et affichage du dernier comparatif dans la page Parametres.
- Couverture de tests et validation :
  - nouveaux tests `tests/test_telemetry_store.py` pour snapshots fallback et alerte glissante,
  - recalage des seuils micro-bench local/CI maintenu dans `tests/test_chroma_store.py`,
  - validation globale post-modifs : 528 tests passes, 0 echec.

### Continuation lot navigation rapide + retention + tendance perf (complement 2026-04-12)

- Navigation rapide depuis Parametres vers les artefacts d'observabilite:
  - liens directs vers `latest_local.json`, `latest_ci.json`, `latest_comparison.md`,
  - lien direct vers `fallback_metrics_history.jsonl`.
- Politique de retention configurable mise en place:
  - snapshots fallback: retention age + volume (`fallback_snapshot_retention_days`, `fallback_snapshot_max_lines`),
  - rapports perf Chroma: retention age + volume (`chroma_perf_report_retention_days`, `chroma_perf_report_max_files`) appliquee a chaque export.
- Alerte tendance distincte de l'alerte fallback:
  - comparaison `latest_local` vs `baseline_local` avec seuil `chroma_perf_trend_warn_pct`,
  - warning dedie en cas de degradation relative des micro-bench Chroma.
- Operations UI associees:
  - bouton "Definir la baseline locale" dans Parametres,
  - affichage de la tendance stable/degradee selon le seuil configure.
- Validation:
  - nouveaux tests `tests/test_telemetry_store.py` (retention rapports + tendance micro-bench),
  - validation globale post-modifs: 530 tests passes, 0 echec.

### Continuation lot dashboard sante + export hebdo + retention budget MB (complement 2026-04-12)

- Ajout d'un tableau de bord "sante observabilite" dans Parametres avec statut global couleur (vert/orange/rouge) base sur:
  - frequence fallback `rglob` sur fenetre glissante,
  - alertes de tendance perf Chroma,
  - fraicheur des rapports local/CI et des snapshots fallback.
- Export compact hebdomadaire introduit via `scripts/export_observability_weekly.py`:
  - generation JSON + Markdown des deltas fallback 7 jours + etat tendance perf,
  - conservation des pointeurs `latest_weekly.json` et `latest_weekly.md`,
  - comparaison courte avec la semaine precedente quand disponible.
- Extension de la retention avec mode budget disque (quota MB) en plus age/volume:
  - fallback snapshots (`fallback_snapshot_budget_mb`),
  - rapports perf Chroma (`chroma_perf_report_budget_mb`),
  - exports hebdomadaires (`observability_weekly_budget_mb`).
- Integration operationnelle:
  - bouton d'export hebdomadaire dans Parametres,
  - export hebdomadaire non bloquant branche dans `scripts/validate_local.sh`.
- Validation:
  - tests telemetry enrichis pour budget MB + retention + tendance,
  - validation globale post-modifs: 532 tests passes, 0 echec.

## Mise a jour du 2026-04-11

### Experience chat

- Ajout d'un etat de session par fil de discussion dans l'UI Streamlit.
- Persistance du brouillon, des messages et des statistiques de generation par thread.
- Restauration correcte du thread actif lors des changements de conversation.
- Conservation des statistiques de la derniere generation dans le fil courant au lieu d'un etat global ambigu.
- Correction d'un cas d'erreur Streamlit sur la remise a zero du brouillon de fil en deplacant la mutation de `chat_thread_draft` dans un callback compatible avec les widgets.

### Graphe et navigation dans le coffre

- Stabilisation de la page Cerveau apres des erreurs d'import a chaud dans Streamlit en passant par un import de module plus robuste.
- Durcissement complementaire de la page Cerveau face aux objets `ChromaStore` obsoletes conserves par le hot reload Streamlit.
- Remplacement des derniers scans ad hoc de dossiers et tags visibles dans la page Cerveau par des helpers Chroma explicites.
- Ajout de filtres par type de note et de resumes associes dans l'exploration du graphe.
- Uniformisation de l'affichage des badges de type et des couleurs associees aux notes.

### Index et acces aux artefacts

- Ajout de `list_generated_notes()` dans `ChromaStore` pour exposer explicitement les artefacts generes par ObsiRAG.
- Simplification de la page Parametres, qui s'appuie maintenant sur cette API au lieu d'un calcul indirect a partir de toutes les notes.
- Propagation continue des helpers Chroma explicites dans l'UI pour reduire les parcours bruts de listes de notes.
- Ajout de `list_recent_notes()` pour exposer explicitement les notes les plus recentes sans tri ad hoc dans l'UI.
- Ajout de `count_notes()`, `list_note_folders()` et `list_note_tags()` pour exposer explicitement les besoins de navigation et de comptage encore calcules localement dans l'UI.
- Ajout de `list_notes_by_type()`, `list_insight_notes()`, `list_synapse_notes()` et `list_report_notes()` pour sortir la page Insights des parcours bruts de repertoires d'artefacts.
- Le cycle normal de l'auto-learner repart maintenant d'une liste de notes utilisateur plutot que d'un `list_notes()` brut pour son full-scan et la decouverte de synapses.

### Rendu HTML et compatibilite Streamlit

- Suppression des usages de `components.html` devenus deprecies.
- Introduction du helper partage `src/ui/html_embed.py`.
- Debut d'extraction des generateurs HTML UI vers des helpers purs testables hors runtime Streamlit.
- Extraction du rendu Mermaid du chat vers un helper dedie, en plus du visualiseur de note.
- Renforcement de la verification du HTML Pyvis genere pour le graphe et de ses hooks d'interaction Obsidian/UI.
- Rendu des documents HTML complets via `st.iframe` avec URL `data:` encodee en base64.
- Execution des scripts inline via `st.html` pour les cas limites de navigation et synchronisation de theme.
- Migration des pages Chat, Cerveau, Note et Theme vers ce point d'entree unique.
- Ajout d'une invalidation de cache dans `src/ui/services_cache.py` pour reconstruire automatiquement les services si le runtime conserve une instance Chroma incompatible.
- Ajout de wrappers de compatibilite UI dans `src/ui/chroma_compat.py` pour tolerer temporairement des objets `chroma` ne portant pas encore les helpers recents lors d'un rechargement a chaud.

### Qualite et tests

- Ajout de tests cibles pour la persistance des statistiques de generation des threads de chat.
- Ajout de tests cibles pour `list_generated_notes()`.
- Ajout de tests cibles pour `list_recent_notes()` et pour l'usage exclusif des notes utilisateur dans le cycle normal de l'auto-learner.
- Ajout d'une verification minimale du HTML genere pour Mermaid et pour le graphe Pyvis.
- Ajout de tests dedies pour `src/ui/html_embed.py`.
- Ajout de tests dedies pour les helpers Mermaid du chat et du visualiseur.
- Ajout de tests dedies pour `src/ui/services_cache.py` et `src/ui/chroma_compat.py` afin de couvrir le correctif de compatibilite runtime Streamlit.
- Renforcement des assertions HTML du graphe Pyvis pour verifier explicitement les hooks d'ouverture de note et le fallback `postMessage` du rendu Brain.
- Ajout d'un helper pur pour preparer et etiqueter les entrees d'artefacts de la page Insights, avec assertions dediees sur ce rendu minimal.
- Validation complete de la suite `pytest --no-cov` : 470 tests passes.
- Validation complementaire ciblee sur les changements recents : 84 tests passes.
- Validation ciblee du correctif de compatibilite runtime : 72 tests passes.

### Exploitation locale

- Nettoyage du redemarrage local des services apres les changements UI.
- Verification du redemarrage de l'application : reponse HTTP 200 sur `http://127.0.0.1:8501`.
- Verification des logs de demarrage : pas de nouvelle erreur bloquante observee sur la derniere relance.
- Verification complementaire apres reconstruction des services : la page Cerveau rebati correctement un graphe de 527 noeuds et 640 aretes apres redemarrage.
- Documentation d'un protocole operatoire de diagnostic, purge de cache et relance locale pour les hot reload Streamlit incomplets.
- Extension du protocole Streamlit avec le cas specifique des cles `session_state` liees a un widget qui doivent etre mutees via callback ou avant instanciation.

## Commits associes

- `9711f0d` - Persist chat stats and modernize HTML embeds
- `ba18d71` - Add tests for HTML embed helper
- `98e59ea` - Extract Mermaid UI helpers and expand Chroma note APIs
- `019b960` - Refine note listing helpers and autolearn filtering
- `5b51a46` - Harden Streamlit runtime compatibility
- `c719480` - Expand Chroma note helpers and Brain checks
- `1e6945f` - Fix chat draft reset in Streamlit

## Impact produit

- L'UI est plus robuste face aux rechargements Streamlit.
- Le suivi des conversations est plus coherent pour l'utilisateur.
- Les ecrans d'administration et d'exploration s'appuient sur des API plus explicites.
- Le risque de regression sur le rendu HTML integre est maintenant couvert par des tests dedies.
- Le cycle d'auto-apprentissage evite mieux de rebalayer les artefacts internes comme s'il s'agissait de notes source.
- Un hot reload Streamlit laisse maintenant moins facilement l'UI dans un etat incoherent quand des helpers Chroma ont evolue entre deux rechargements.
- Le diagnostic local des regressions UI liees au hot reload est plus rapide et plus reproductible grace au protocole documente.
- La page Insights depend moins de scans filesystem implicites et davantage d'API Chroma explicites, ce qui reduit les divergences entre ecrans UI.

## Prochaines ameliorations a poursuivre

Les trois priorites listees dans la mise a jour precedente ont ete traitees dans cette mise a jour du 2026-04-12.

Prochain lot propose :

1. Ajouter des controles UI Parametres pour ajuster a chaud (sans edition `.env`) les seuils d'alerte fallback/tendance et les politiques de retention.
1. Introduire un resume hebdomadaire agrégé multi-semaines (sparkline + variation %) pour visualiser l'evolution des deltas fallback et des micro-bench Chroma.
1. Ajouter une sauvegarde optionnelle des exports observabilite vers un dossier externe (archive locale/partagee) avec verification d'integrite simple (hash + index).