# Feuille de route performance (execution)

Date de reference: 2026-04-13
Horizon: 10 semaines
Portee: optimisation performance avec migration Rust conditionnelle (ROI-driven)

## 1) Objectifs cibles (SLO)

- Latence chat bout-en-bout: -35% sur le P95.
- Throughput auto-learner: +50% (notes/heure).
- Stabilité runtime: taux d'erreur < 1%, timeout <= baseline.
- Qualité RAG: aucune regression sur le jeu de verification fonctionnelle.

## 2) Regles Go/No-Go Rust

Un composant est eligible a une migration Rust uniquement si:

1. il pese >= 20% du temps total mesure sur scenario reel,
2. le prototype donne >= x2 sur micro-bench homologue,
3. l'overhead d'integration (IPC/FFI + serialisation) reste <= 10% de la latence finale,
4. un rollback operable est valide avant exposition production.

## 3) Plan par sprint

## Sprint 1 (Semaines 1-2) — Baseline durcie

Objectif: figer la verite de performance, scenario par scenario.

Tickets:

- PERF-01: formaliser les scenarios de charge standard (chat court, chat long, cycle auto-learner, reindexation).
- PERF-02: publier un budget de latence par etape (retrieval, contexte, generation, post-traitement).
- PERF-03: consolider un tableau unique P50/P95/P99 + throughput + erreurs.
- PERF-04: definir les seuils d'alerte et la methode de comparaison baseline vs latest.

Definition of Done:

- Une execution standard produit un rapport unique comparable d'une semaine a l'autre.
- Variance de mesure controllee (tolerance cible +/-10%).
- Top 5 hotspots quantifies (temps absolu + frequence + impact).

## Sprint 2 (Semaines 3-4) — Quick wins Python

Objectif: recuperer du gain rapide avant toute reecriture.

Tickets:

- PERF-05: batching retrieval/contexte pour reduire les tours inutiles.
- PERF-06: reduction des copies et transformations intermediaires couteuses.
- PERF-07: ajustement dynamique du contexte envoye au modele selon intention/requete.
- PERF-08: optimisation des pauses auto-learner pour maximiser le debit sans saturation.

Definition of Done:

- Gain >= 15% sur au moins un axe majeur (P95 chat ou temps/note auto-learner).
- Aucune regression qualite sur le jeu de validation RAG.
- Aucun accroissement du taux d'erreur.

## Sprint 3 (Semaines 5-6) — Pilote Rust #1

Objectif: valider la valeur de Rust sur un seul hotspot critique.

Tickets:

- PERF-09: selection du hotspot #1 (chunking ou scoring/rerank) sur donnees mesurees.
- PERF-10: prototype Rust isole avec benchmark identique a la version Python.
- PERF-11: integration derriere feature flag (activation selective).
- PERF-12: test de rollback en condition reelle.

Definition of Done:

- Gain composant >= x2.
- Gain bout-en-bout >= 10% sur scenario cible.
- Rollback technique valide et documente.

## Sprint 4 (Semaines 7-8) — Extension selective

Objectif: etendre seulement si les criteres restent favorables.

Tickets:

- PERF-13: extension au hotspot #2 (conditionnee au gate Go Rust).
- PERF-14: parallelisme controle et backpressure sur les etapes bulk.
- PERF-15: tuning stabilite P99 (variance et files d'attente).

Definition of Done:

- P99 reduit d'au moins 20% sur les scenarios long-run.
- Throughput global +30% a +50% vs baseline Sprint 1.
- Endurance stable >= 24h sans incident bloquant.

## Sprint 5 (Semaines 9-10) — Hardening et mise en production

Objectif: securiser l'exploitation et mesurer le ROI final.

Tickets:

- PERF-16: deploiement canary progressif (10% -> 30% -> 100%).
- PERF-17: runbook incident performance + procedure rollback.
- PERF-18: bilan ROI (latence, debit, cout infra, complexite d'operation).

Definition of Done:

- SLO tenus pendant 7 jours consecutifs.
- Aucun incident critique imputable a la migration.
- Decision architecture cible formalisee (hybride Python/Rust ou extension Rust).

## 4) Backlog priorise (ordre impose)

1. Baseline et budget de latence.
2. Quick wins Python.
3. Pilote Rust #1.
4. Extension Rust conditionnelle.
5. Canary + hardening + ROI final.

## 5) KPIs de pilotage hebdomadaire

- Latence P50/P95/P99 par etape pipeline.
- Throughput: req/s et notes/heure.
- Temps moyen par note auto-learner.
- Erreurs/timeouts/retries.
- Cout estime par 10k requetes.
- Delta baseline vs latest (en %), avec seuil d'alerte.

## 6) Risques majeurs et mitigation

- Risque: migration Rust prematurée sans hotspot valide.
  - Mitigation: gate Go/No-Go obligatoire avec preuves mesurees.
- Risque: gain composant masque par overhead integration.
  - Mitigation: mesurer l'overhead avant generalisation.
- Risque: regression qualite RAG.
  - Mitigation: batterie de verification fonctionnelle en gate de release.

## 7) Cadence de gouvernance

- Revue performance hebdomadaire: 45 min.
- Decision Go/No-Go Rust: toutes les 2 semaines.
- Gel de scope automatique si regression qualite ou fiabilite.

## 8) Mapping composants prioritaires (obsirag)

Zones de travail ciblees en priorite pour les sprints perf:

- Retrieval/RAG: `src/ai/rag.py`, `src/ai/retrieval_strategy.py`, `src/ai/answer_prompting.py`.
- Ingestion/chunking: `src/indexer/pipeline.py`, `src/indexer/chunker.py`.
- Auto-learner throughput: `src/learning/autolearn.py`, `src/learning/question_answering.py`, `src/learning/web_enrichment.py`.
- Stockage/index: `src/database/chroma_store.py`.

Ces cibles sont priorisees car elles influencent directement le P95 chat et le temps/note auto-learner.

## 9) Execution sans Jira

Si vous ne pilotez pas avec Jira, utilisez ce format minimal directement dans le depot.

### 9.1 Tableau de suivi (Markdown)

Copier ce tableau dans un fichier de suivi (ex: `docs/performance-tracker.md`) et mettre a jour chaque semaine.

| Ticket | Sprint | Owner | Statut | Impact cible | Resultat mesure | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| PERF-01 | S1 | a definir | TODO | Baseline stable | - | - |
| PERF-02 | S1 | a definir | TODO | Budget latence publie | - | - |
| PERF-03 | S1 | a definir | TODO | Dashboard unique | - | - |
| PERF-04 | S1 | a definir | TODO | Seuils d'alerte actifs | - | - |
| PERF-05 | S2 | a definir | TODO | -15% P95 ou temps/note | - | - |
| PERF-06 | S2 | a definir | TODO | Reduction copies/CPU | - | - |
| PERF-07 | S2 | a definir | TODO | Contexte plus efficace | - | - |
| PERF-08 | S2 | a definir | TODO | Throughput learner + | - | - |
| PERF-09 | S3 | a definir | TODO | Hotspot #1 valide | - | - |
| PERF-10 | S3 | a definir | TODO | Prototype x2 composant | - | - |
| PERF-11 | S3 | a definir | TODO | Feature flag actif | - | - |
| PERF-12 | S3 | a definir | TODO | Rollback teste | - | - |
| PERF-13 | S4 | a definir | TODO | Hotspot #2 (si GO) | - | - |
| PERF-14 | S4 | a definir | TODO | Backpressure stable | - | - |
| PERF-15 | S4 | a definir | TODO | P99 -20% | - | - |
| PERF-16 | S5 | a definir | TODO | Canary 10/30/100 | - | - |
| PERF-17 | S5 | a definir | TODO | Runbook incident pret | - | - |
| PERF-18 | S5 | a definir | TODO | ROI final publie | - | - |

Statuts recommandes: `TODO`, `DOING`, `BLOCKED`, `DONE`.

### 9.2 Revue hebdomadaire (30-45 min)

1. Mesures de la semaine (P95, P99, throughput, erreurs).
2. Tickets closes et gain reel constate.
3. Tickets bloques + action de debloquage.
4. Decision Go/No-Go Rust selon les gates section 2.

### 9.3 Format de compte-rendu

Copier ce template dans un journal hebdo (ex: `docs/perf-weekly-YYYY-MM-DD.md`):

```md
# Revue performance - YYYY-MM-DD

## KPI
- P95 chat: X s (delta: Y%)
- P99 chat: X s (delta: Y%)
- Temps/note auto-learner: X min (delta: Y%)
- Throughput: X notes/h (delta: Y%)
- Erreurs/timeouts: X (delta: Y%)

## Tickets termines
- PERF-XX: resultat mesure

## Tickets en cours
- PERF-XX: avancement / risque

## Decisions
- Rust hotspot #1: GO/NO-GO (justification)

## Actions semaine suivante
- PERF-XX
```