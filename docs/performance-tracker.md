# Performance Tracker

Date de demarrage: 2026-04-13
Reference roadmap: docs/performance-roadmap.md

## Regles de statut

- `TODO`: non commence
- `DOING`: en cours
- `BLOCKED`: bloque par une dependance
- `DONE`: termine et mesure

## Sprint en cours

Sprint actif: S4 (Semaines 7-8) — optimisation generation MLX
Objectif sprint: reduire la latence de generation MLX (hotspot #1 = 99.27%) par KV cache quantifie et pre-chauffe du prompt systeme.

## Tableau de suivi

| Ticket | Sprint | Owner | Statut | Impact cible | Resultat mesure | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| PERF-01 | S1 | Patrick | DONE | Baseline stable | Scenarios de reference formalises | OK |
| PERF-02 | S1 | Patrick | DONE | Budget latence publie | Budget P95 publie par scenario | OK |
| PERF-03 | S1 | Patrick | DONE | Dashboard unique P50/P95/P99 | `scripts/benchmark_baseline.py` + tableau KPI | OK |
| PERF-04 | S1 | Patrick | DONE | Seuils d'alerte actifs | Seuils orange/rouge definis | OK |
| PERF-05 | S2 | Patrick | DONE | -15% P95 ou temps/note | P95 `build_context` -27.7% (micro-bench PERF-05) | OK |
| PERF-06 | S2 | Patrick | DONE | Reduction copies/CPU | Hint note dominante: P95 preparation contexte -11.56% | OK |
| PERF-07 | S2 | Patrick | DONE | Contexte plus efficace | Iteration 2: chars contexte moyen -8.54%, P95 `build_context` -6.63% | OK |
| PERF-08 | S2 | Patrick | DONE | Throughput learner + | Pause adaptative: throughput estime 20.73 -> 25.03 notes/h (+20.75%) | OK |
| PERF-09 | S3 | Patrick | DONE | Hotspot #1 valide | Hotspot global = generation MLX (99.27%), meilleur hotspot interne = retrieval (0.69%) | NO-GO Rust app |
| PERF-10 | S3 | Patrick | BLOCKED | Prototype x2 composant | Gate PERF-09 negatif: aucun hotspot interne >= 20% | En attente d'un nouveau hotspot |
| PERF-11 | S4 | Patrick | DONE | KV cache 8-bit: TPS +10% sur P95 | Benchmark PERF-11/12 (AB, n=20): TPS moyen 25.64 tok/s (cache_hit 20/20) | OK |
| PERF-12 | S4 | Patrick | DONE | Pre-chauffe prompt systeme: TTFT -2s | Benchmark PERF-11/12 (AB, n=20): TTFT moyen 2.451s, P95 3.845s | OK |
| PERF-13 | S4 | Patrick | DONE | max_tokens adaptatif par intent | Caps activés + AB10: total moyen 15.048s (P95 28.078s), completions observées <= 700 tokens | MIXTE (latence totale en légère baisse, TTFT/TPS à surveiller) |
| PERF-14 | S4 | Patrick | DONE | Backpressure stable | `_InferenceBackpressure` dans `rag.py` : 1 inférence active, max_queue=2, timeout=120s, rejet immédiat si saturé — 7 tests unitaires (99/99 pass) | OK |
| PERF-15 | S4 | Patrick | DONE | P99 -20% | (a) `_AnswerCache` TTL 5 min, 128 entrées — supprime les doublons de rechargement UI et les requêtes rafales ; (b) `_retry_forced_study_synthesis` conditionné à ≥ 2 notes distinctes — élimine le 2e appel LLM inutile sur source unique — 12 nouveaux tests (111/111 pass) | OK (mesure P99 à valider en bench AB) |
| PERF-16 | S5 | Patrick | DONE | Canary 10/30/100 | Feature flags `rag_backpressure_enabled`/`rag_answer_cache_enabled` dans `config.py` ; `scripts/canary_validation.py` 3 phases (2/6/20 req), seuils PERF-02, Go/No-Go par phase, rapport JSON — 16 tests unitaires (127/127 pass) | OK |
| PERF-17 | S5 | Patrick | TODO | Runbook incident pret | - | - |
| PERF-18 | S5 | Patrick | TODO | ROI final publie | - | - |

## Checklist Sprint 1

- [x] Scenario chat court formalise (donnees, volume, requetes)
- [x] Scenario chat long formalise
- [x] Scenario auto-learner formalise
- [x] Scenario reindexation formalise
- [x] Budget latence par etape valide
- [x] Tableau KPI P50/P95/P99 formalise
- [x] Seuils d'alerte hebdomadaires fixes
- [ ] Top 5 hotspots captures avec impact quantifie (S2)

## PERF-02 - Budget de latence cible

Objectif: fixer une enveloppe P95 par etape pour piloter les optimisations S1/S2.

### Budget P95 - Scenario A (chat court)

| Etape | Budget P95 cible |
| --- | --- |
| Retrieval + rerank | <= 8 s |
| Construction contexte/prompt | <= 3 s |
| Generation LLM | <= 18 s |
| Post-traitement/formatage | <= 1 s |
| **Total** | **<= 30 s** |

### Budget P95 - Scenario B (chat long)

| Etape | Budget P95 cible |
| --- | --- |
| Retrieval + rerank | <= 12 s |
| Construction contexte/prompt | <= 5 s |
| Generation LLM | <= 40 s |
| Post-traitement/formatage | <= 3 s |
| **Total** | **<= 60 s** |

### Budget P95 - Scenario C (auto-learner)

| Etape | Budget cible |
| --- | --- |
| Questions (LLM) | <= 12 s/note |
| 3 x rag_query | <= 108 s/note |
| Enrichissement | <= 45 s/note |
| Synthese web | <= 40 s/note |
| Renommage + semantique + I/O | <= 30 s/note |
| **Total** | **<= 235 s/note (~3.9 min)** |

### Budget P95 - Scenario D (reindexation)

| Etape | Budget cible |
| --- | --- |
| Parsing + chunking | >= 30 chunks/s |
| Ecriture index vectoriel | >= 25 chunks/s |
| **Temps total lot 100 notes** | **<= 8 min** |

### Regle d'alerte

- Alerte orange: depassement > 10% d'un budget sur 2 runs consecutifs.
- Alerte rouge: depassement > 20% d'un budget sur 1 run.

### Resultat PERF-02

- Statut: termine.
- Decision: passage a PERF-03 (tableau unique P50/P95/P99 + throughput + erreurs).

## PERF-01 - Scenarios de reference (baseline)

Objectif: disposer de 4 scenarios stables, rejouables d'une semaine a l'autre.

### Scenario A - Chat court

- Intent: question factuelle simple repondable sur 1-3 notes.
- Jeu de test: 10 requetes courtes fixes (liste figee dans un fichier de campagne).
- Charge: execution sequentielle, 1 run = 10 requetes.
- Mesures attendues: latence totale P50/P95/P99, taux d'erreur, nombre moyen de passages contextuels.
- Critere de validite: variance inter-runs <= 10% sur P95.

### Scenario B - Chat long

- Intent: questions de synthese multi-notes (contexte dense).
- Jeu de test: 10 requetes longues fixes.
- Charge: execution sequentielle, 1 run = 10 requetes.
- Mesures attendues: latence P50/P95/P99, tokens de sortie, retries eventuels, erreurs/timeouts.
- Critere de validite: variance inter-runs <= 10% sur P95 et P99.

### Scenario C - Auto-learner

- Intent: evaluer le debit note-par-note et le temps de cycle.
- Jeu de test: echantillon fixe de 20 notes representatif (court/moyen/long).
- Charge: 1 cycle complet learner (questions + rag + enrich + synthesis).
- Mesures attendues: temps moyen par note, temps total cycle, notes/heure, erreurs.
- Critere de validite: temps moyen/note stable (+/-10%) sur 3 executions.

### Scenario D - Reindexation

- Intent: mesurer l'ingestion/chunking/indexation.
- Jeu de test: lot fixe de 100 notes ou echantillon equivalent stable.
- Charge: reindexation complete a froid.
- Mesures attendues: duree totale, notes/min, chunks/min, erreurs d'indexation.
- Critere de validite: debit stable (+/-10%) sur 3 executions.

### Protocole commun d'execution

1. Utiliser la meme machine et fermer les applications lourdes en arriere-plan.
2. Lancer chaque scenario 3 fois et conserver mediane + P95.
3. Conserver les rapports dans `logs/validation/` et noter les deltas dans ce tracker.
4. En cas d'ecart > 10%, rejouer une 4e fois et marquer l'anomalie dans le journal.

### Resultat PERF-01

- Statut: termine.
- Decision: baseline scenarios figee, passage a PERF-02 (budget de latence par etape).

## PERF-03 - Tableau KPI hebdomadaire

Objectif: disposer d'un tableau unique a remplir chaque semaine pour suivre l'evolution des KPIs.

### Format de remplissage

Copier ce tableau dans le journal hebdo et remplir apres chaque run de scenarios.

| Metrique | Baseline | Semaine N | Delta | Statut |
| --- | --- | --- | --- | --- |
| P50 chat court (s) | _a mesurer_ | - | - | - |
| P95 chat court (s) | _a mesurer_ | - | - | - |
| P99 chat court (s) | _a mesurer_ | - | - | - |
| P50 chat long (s) | _a mesurer_ | - | - | - |
| P95 chat long (s) | _a mesurer_ | - | - | - |
| P99 chat long (s) | _a mesurer_ | - | - | - |
| Temps/note learner (s) | _a mesurer_ | - | - | - |
| Throughput learner (notes/h) | _a mesurer_ | - | - | - |
| Debit reindexation (chunks/s) | _a mesurer_ | - | - | - |
| Erreurs + timeouts totaux | _a mesurer_ | - | - | - |

Colonne **Delta**: `(SemaineN - Baseline) / Baseline * 100`, exprime en `+X%` ou `-X%`.
Colonne **Statut**: `OK`, `ORANGE` (>+10%), `ROUGE` (>+20%).

### Resultat PERF-03

- Statut: termine.
- Tableau KPI fige. Baseline a remplir apres le premier run des 4 scenarios.
- Decision: passage a PERF-04 (seuils d'alerte finalises).

## PERF-04 - Seuils d'alerte et methode de comparaison

Objectif: definir les regles automatiques d'alerte pour ne pas rater une regression silencieuse.

### Regles d'alerte par niveau

| Niveau | Condition | Action |
| --- | --- | --- |
| OK | Tous les deltas <= +10% | Rien, continuer. |
| ORANGE | Un delta entre +10% et +20% sur 2 runs consecutifs | Documenter dans le journal, investiguer avant le prochain sprint. |
| ROUGE | Un delta > +20% sur 1 run | Gel du sprint en cours, investigation immediate. |

### Regles de comparaison baseline

- La baseline est figee au premier run complet des 4 scenarios.
- Elle n'est mise a jour que sur decision explicite (changement materiel ou refonte majeure).
- Toute mise a jour de baseline est documentee dans le journal avec justification.

### Regles de comparaison Go/No-Go Rust

- Un hotspot est eligible si son delta P95 depasse +20% apres S2, OU s'il pese >= 20% du temps total mesure.
- Le gate est verifie a chaque revue bi-hebdomadaire.

### Resultat PERF-04

- Statut: termine.
- Seuils d'alerte figes et methode de comparaison baseline definie.
- Sprint S1 complet. Passage a S2 (quick wins Python).

## Mesures de la semaine (baseline - a remplir apres premier run)

- P50 chat court: 12.085 s (live, scenario A)
- P95 chat court: 24.61 s (live, scenario A)
- P99 chat court: 27.244 s (live, scenario A)
- P50 chat long: 22.712 s (live, scenario B)
- P95 chat long: 29.631 s (live, scenario B)
- P99 chat long: 31.729 s (live, scenario B)
- Temps moyen auto-learner par note:
- Throughput auto-learner (notes/heure):
- Debit reindexation (chunks/s): N/A (mesure actuelle: 619 notes en 56.289s, 659.8 notes/min)
- Erreurs + timeouts: scenario A/B/C/D = 0

## Journal de revue hebdo

### 2026-04-13

- Avancement:
  - Tracker initialise.
  - Sprint S1 demarre.
  - PERF-01 termine: 4 scenarios de baseline formalises.
  - PERF-02 termine: budget de latence publie.
  - PERF-03 termine: script benchmark `scripts/benchmark_baseline.py` cree (scenarios A/B/C/D, percentiles, rapport MD+JSON).
  - PERF-04 termine: seuils d'alerte et methode de comparaison definis.
  - Sprint S1 termine.
  - Baseline scenario C executee: P50=0.029s, P95=0.100s, P99=0.304s (retrieval pur).
  - Baseline scenario D executee: 147.888s pour 607 notes (246.3 notes/min), 0 erreur.
  - Baseline C relancee apres reconstruction index/chroma 1.5.6: P50=0.012s, P95=0.071s, P99=0.315s.
  - Baseline D relancee apres reconstruction index: 56.289s pour 619 notes (659.8 notes/min), 0 erreur.
  - Baseline A live finalisee: P50=12.085s, P95=24.61s, P99=27.244s, 0 erreur.
  - Baseline B live finalisee: P50=22.712s, P95=29.631s, P99=31.729s, 0 erreur.
  - Downgrade Chroma applique et fige: `chromadb==1.5.6` (segfault non reproduit sur A/B/C apres changement).
  - S2/PERF-05 demarre: batching des linked chunks ajoute (bulk par `file_path`) pour reduire les appels Chroma repetes en construction de contexte.
  - PERF-05 mesure et valide: micro-bench `scripts/benchmark_perf05_context.py` → P95 contexte 16.42ms (legacy) -> 11.87ms (bulk), gain 27.7%.
  - PERF-06 mesure et valide: micro-bench `scripts/benchmark_perf06_primary_hint.py` → P95 preparation contexte 10.79ms (recompute) -> 9.54ms (hint), gain 11.56%.
  - PERF-07 iteration 1: dedup des chunks en amont du prompt (`_dedupe_context_chunks`) + micro-bench `scripts/benchmark_perf07_context_dedupe.py`.
  - Resultat PERF-07 iteration 1: P95 `build_context` 1.65ms (sans dedupe) -> 1.44ms (dedupe), gain 12.92%; reduction de taille moyenne du contexte: 0.0% (jeu actuel peu redondant).
  - PERF-07 iteration 2: benchmark corrige (baseline legacy complete), filtre anti-redondance au rendu + cap adaptatif des chunks quand contexte multi-notes.
  - Resultat PERF-07 final: `scripts/benchmark_perf07_context_dedupe.py` -> chars contexte moyen 5011.7 -> 4583.7 (-8.54%), P95 `build_context` 1.676ms -> 1.565ms (-6.63%).
  - PERF-08 implemente: pause adaptative entre notes du cycle normal (`src/learning/autolearn.py`) pour eviter les 30s d'attente fixes quand une note a deja consomme du temps de traitement.
  - PERF-08 mesure: `scripts/benchmark_perf08_autolearn_pause.py` (100 dernieres notes) -> cycle moyen 173.69s -> 143.84s, throughput estime 20.73 -> 25.03 notes/h (+20.75%).
  - PERF-09 mesure live: `scripts/benchmark_perf09_hotspot.py` sur 5 requetes A + 5 requetes B avec instrumentation par phase (resolve, retrieval, contexte, prompt, generation, post-traitement).
  - Resultat PERF-09: generation MLX domine 99.27% du temps mesure; meilleur hotspot applicatif interne = retrieval a 0.69%.
  - Decision PERF-09: gate Rust applicatif = NO-GO a ce stade. La latence est principalement portee par l'inference modele deja native, pas par un composant Python interne.
- Blocages:
  - Aucun blocage actif sur les scenarios baseline apres stabilisation Chroma.
- Prochaine action:
  - Reprioriser S3 hors Rust applicatif: soit optimiser le chemin generation/serving modele, soit revenir a des optimisations Python/produit avec impact utilisateur mesurable.
