<p align="left">
  <img src="https://raw.githubusercontent.com/pat-the-geek/obsirag/main/src/ui/static/android-chrome-512x512.png" alt="ObsiRAG" width="120" />
</p>

# ObsiRAG

Un système RAG (Retrieval-Augmented Generation) local pour votre coffre Obsidian, tournant en Python dans Docker et utilisant **Ollama** comme moteur IA local.

---

## Vision du projet

**ObsiRAG** vous permet d'interagir avec l'intégralité de votre coffre Obsidian via un chat en langage naturel — le tout en local, sans envoyer vos données dans le cloud.

Exemples de requêtes :

- *"Quelles sont mes dernières notes ? Fais une synthèse de cette semaine."*
- *"Quelles sont les notes où je parle de X ou Y ?"*
- *"Qu'est-ce que j'ai appris ce mois-ci sur le sujet Z ?"*

---

## Principes fondamentaux

- **100% local** : vos notes ne quittent jamais votre machine
- **Coffre en lecture seule** : ObsiRAG ne modifie jamais vos notes Obsidian existantes
- **Accès complet au coffre** : pas de fenêtre contextuelle limitée, l'ensemble du coffre est exploitable
- **Artefacts traçables** : les insights générés indiquent leur provenance (Coffre, Web, ou Coffre et Web)
- **Déploiement Docker** : isolation propre, reproductible

---

## Fonctionnalités

### Chat avec le coffre

Interface conversationnelle connectée à **Ollama** (via son API OpenAI-compatible) et au moteur de recherche du coffre. Les requêtes sont traitées en combinant récupération sémantique et synthèse par l'IA.

### Cerveau — graphe de connaissances

Visualisation interactive du réseau de vos notes sous forme de graphe interactif (rendu Pyvis sur fond sombre). Chaque nœud est une note, chaque arête une connexion.

**Ce qui est affiché :**

- **Nœuds** : chaque note du coffre est un nœud coloré selon son dossier d'appartenance (palette de 8 couleurs distinctes). La taille du nœud est proportionnelle à son nombre de connexions — les notes les plus référencées apparaissent plus grandes
- **Arêtes (connexions)** : les `[[wikilinks]]` entre notes forment les arêtes du graphe
- **Tooltip au survol** : titre, date de modification, tags et deux boutons d'action — ouvrir la note dans le visualiseur intégré ou directement dans Obsidian
- **Métriques en en-tête** : nombre de nœuds, connexions, densité du graphe et nombre de notes filtrées
- **Top 5 nœuds les plus connectés** : liste sous le graphe avec leur score de centralité, avec bouton d'ouverture directe

**Filtres disponibles (barre latérale) :**

- Par **dossier** (tous ou sélection multiple)
- Par **tag** Obsidian (sélection multiple)
- Sélecteur de note alphabétique pour ouvrir directement une note dans le visualiseur

Le graphe est mis en cache 5 minutes et recalculé à la demande via le bouton 🔄. Il est également exporté en JSON (`data/graph/knowledge_graph.json`) pour un usage externe éventuel.

### Auto-apprentissage (background learner)

Un processus léger tourne en arrière-plan et :

1. Détecte les notes récemment modifiées dans le coffre
2. **Détermine le champ sémantique** de chaque note (domaine, concepts-clés, angle traité) pour ancrer la génération dans le bon univers lexical
3. Génère des questions perspicaces **strictement alignées avec ce champ sémantique**
4. Répond via RAG sur le coffre — et **complète avec le web** si la réponse est insuffisante
5. N'utilise que des **sources fiables** (Wikipédia, presse de référence, institutions, revues scientifiques…)
6. Sauvegarde les insights en Markdown dans `obsirag/insights/` avec indication de provenance et **références citées**
7. Génère une **synthèse hebdomadaire** le dimanche dans `obsirag/synthesis/`

> Les artefacts générés sont indexés et deviennent eux-mêmes interrogeables dans le chat.

Le système est conçu pour fonctionner **sans pénaliser l'utilisation normale de la machine** : les appels LLM sont espacés (pause configurable entre chaque note et chaque question), le nombre de notes traitées par cycle est limité, et tout tourne dans un thread d'arrière-plan isolé dans Docker. La machine reste pleinement disponible pendant le traitement.

#### Alignement sémantique des questions

Avant de générer des questions, l'auto-learner extrait le champ sémantique de la note :
> `Domaine: [domaine principal] | Concepts: [concept1, concept2, concept3] | Angle: [angle spécifique]`

Ce champ est injecté comme contrainte explicite dans le prompt de génération, garantissant que les questions — et donc les insights produits — restent dans le même univers thématique que la note source. Une note sur la *finance comportementale* génère des questions sur les biais cognitifs et non sur un sujet adjacent que le LLM pourrait dériver.

#### Entités nommées (NER) — validation WUDD.ai

Chaque insight généré est enrichi avec des **entités nommées validées** (personnes, organisations, pays, produits) issues de la liste officielle [WUDD.ai](http://localhost:5050). Le processus :

1. Extrait les entités candidates par analyse spaCy du texte Q&A
2. Valide chaque entité contre la liste officielle WUDD.ai (top 5 000 entités, triées par fréquence de mention) — les entités non reconnues sont ignorées
3. Génère les **tags Obsidian** (`personne/`, `org/`, `lieu/`, `produit/`…) en utilisant le nom canonique officiel
4. Insère une **galerie d'images** (table Markdown) avec la photo/logo de l'entité principale par type (PERSON, ORG, GPE, PRODUCT), depuis le cache Wikimedia de WUDD.ai
5. Injecte **`location: [lat, lng]`** dans le frontmatter YAML pour la géolocalisation Obsidian Map View (coordonnées Wikipedia)

> **Dépendance externe :** WUDD.ai doit être accessible sur `WUDDAI_ENTITIES_URL` (configurable dans `.env`). En cas d'indisponibilité, l'extraction spaCy seule est utilisée en fallback — les insights sont créés mais sans validation officielle. La liste est mise en cache localement pendant 24h.

Pour migrer les insights existants (tags + géolocalisation + galeries) :
```bash
docker exec obsirag python3 /app/scripts/migrate_insight_tags.py --dry-run  # simulation
docker exec obsirag python3 /app/scripts/migrate_insight_tags.py              # application
```

### Page Insights

Consultation des artefacts, synapses et synthèses générés, avec :
- **Progression & estimation du temps restant** : widget affichant le nombre de notes traitées, restantes, et une estimation de la durée nécessaire pour compléter le traitement — avec heure du prochain cycle en heure locale
- Historique des requêtes posées dans le chat

---

## Conditions de génération d'un insight

Toutes les notes ne donnent pas lieu à un insight. Voici les cas où une note est ignorée :

| Condition | Raison | Ce qui se passe |
| --- | --- | --- |
| **Note trop courte / mal indexée** | Aucun chunk trouvé dans ChromaDB | La note n'est pas dans l'index vectoriel ; elle sera ignorée jusqu'à la prochaine réindexation |
| **Aucune question générée** | Le LLM n'a pas suivi le format attendu, ou le contenu est trop pauvre pour formuler une question | L'étape de génération de questions est sautée |
| **Toutes les réponses QA ont échoué** | Erreur Ollama (contexte dépassé, modèle non disponible…) pour les 3 questions | L'insight n'est pas sauvegardé |
| **Note mal parsée (YAML invalide)** | Le frontmatter Obsidian contient des caractères illégaux ou est mal formé | La note n'est pas indexée du tout |

### Notes qui produisent un insight

Une note génère un insight lorsque :

1. Elle est présente et correctement indexée dans ChromaDB (au moins un chunk)
2. Le LLM génère au moins une question orientée vers des **connaissances externes** pertinentes au domaine
3. Au moins une réponse QA aboutit — soit via web (DDG + synthèse LLM), soit en fallback via RAG
4. La réponse n'est pas détectée comme vide ou générique (filtres anti-réponse-creuse)

L'insight est sauvegardé dans `obsirag/insights/YYYY-MM/` avec :

- Les questions générées et leurs réponses
- La provenance (Web, Coffre, ou Web+Coffre)
- Une synthèse des sources web lorsque des URLs ont été récupérées et analysées

> **Astuce** : Si une note attendue ne produit pas d'insight, vérifiez qu'elle est bien indexée (bouton "Re-indexer le coffre" dans le chat) et que le LLM est disponible dans Ollama (`ollama list`).

---

## Synapses — connexions implicites entre notes

### Pourquoi "synapse" ?

En neurologie, une **synapse** est la jonction entre deux neurones : elle transmet un signal d'un neurone à l'autre, créant une connexion qui n'existait pas de façon anatomique directe. Le terme est utilisé ici par analogie : deux notes de votre coffre sont des "neurones", et ObsiRAG découvre une connexion implicite entre elles — une connexion qui n'a jamais été formalisée par un wikilink.

### Comment ça fonctionne

1. **Détection de paires** : à chaque cycle, ObsiRAG tire aléatoirement des notes du coffre et cherche dans ChromaDB les notes sémantiquement proches (similarité cosinus au-dessus d'un seuil configurable), en excluant celles qui ont déjà un wikilink entre elles
2. **Mémoire des paires** : chaque paire `Note A ↔ Note B` est mémorisée dans `data/synapse_index.json` — elle ne sera jamais retraitée deux fois
3. **Génération du texte** : le LLM reçoit un extrait des deux notes et explique en 3 à 5 phrases la connexion implicite qui les unit, ainsi qu'une question à approfondir
4. **Fichier résultat** : une note Markdown est créée dans `obsirag/synapses/` nommée `{NoteA}__{NoteB}_{date}.md`, avec le score de similarité, la connexion expliquée et les extraits des deux notes sources

### Ce que vous voyez dans Obsidian

Les fichiers synapses contiennent des wikilinks vers chacune des deux notes sources, ce qui les intègre automatiquement dans le **graphe de connaissances** — révélant visuellement des ponts thématiques entre des notes que vous n'auriez peut-être pas rapprochées vous-même.

---

## Nom et structure des fichiers insights

### Nom du fichier

Le fichier est nommé automatiquement à partir du titre de la note source :

```
obsirag/insights/YYYY-MM/{titre_note}_{YYYYMMDD}.md
```

- Les caractères spéciaux sont supprimés, les espaces remplacés par `_`, le tout tronqué à 60 caractères
- La date du jour (heure locale) est ajoutée en suffixe
- Les fichiers sont regroupés par mois dans un sous-dossier `YYYY-MM/`

**Exemple :** une note intitulée "La vitesse des LLMs", traitée le 7 avril 2026, produit :
`obsirag/insights/2026-04/La_vitesse_des_LLMs_20260407.md`

### Mise à jour vs. création

À chaque cycle, avant de créer un nouveau fichier, ObsiRAG cherche un insight existant pouvant être complété, selon deux critères :

1. **Même note source** : le nom du fichier correspond au titre de la note (priorité maximale)
2. **Même thématique** : au moins 2 tags entités NER en commun dans le frontmatter

Si un fichier correspondant est trouvé, les nouveaux Q&A sont **ajoutés à la suite** (numérotation continue `## Question N`), la date "Mise à jour le" est rafraîchie, les tags NER sont fusionnés et la galerie d'images mise à jour. Sinon, un nouveau fichier est créé.

### Structure du contenu

```
---                          ← Frontmatter YAML
tags:
  - insight
  - {tags de la note source}
  - {entités NER : personne/, org/, lieu/…}
location: [lat, lng]         ← optionnel, si entité géolocalisable
---

# Insights : {titre de la note}

**Note source :** [[lien wikilink]]
**Générée le / Mise à jour le :** {date heure locale}
**Provenance :** Web | Coffre | Coffre et Web

## Entités clés          ← galerie d'images des entités principales (WUDD.ai)

## Question 1
> {question générée}
{réponse LLM}
*Provenance / Notes consultées / Références web*

## Question 2 …

## Synthèse des sources web   ← si des pages web ont été analysées
```

---

## Comment fonctionne la recherche sémantique

### 1. Découpage en chunks

Une note Obsidian peut être longue et couvrir plusieurs sujets. Pour permettre une recherche précise, chaque note est découpée en **morceaux (chunks)** d'environ 300 mots, avec un léger chevauchement entre chaque morceau pour préserver le contexte aux jonctions.

Le découpage respecte la structure de la note : d'abord par section (`## Titre`), puis par paragraphe, puis par mots si nécessaire. Chaque chunk hérite des métadonnées de la note (titre, tags, dates, wikilinks, entités NER…).

### 2. Vectorisation (embedding)

Chaque chunk est transformé en un **vecteur numérique** — une liste de ~768 nombres — par le modèle `nomic-embed-text` via **Ollama** (calculs sur GPU/ANE du Mac, sans charge CPU dans Docker). Ce vecteur encode le *sens* du texte : deux passages sémantiquement proches produisent des vecteurs proches dans l'espace mathématique, même s'ils n'ont aucun mot en commun.

### 3. Stockage dans ChromaDB

Les vecteurs et leurs métadonnées sont stockés dans **ChromaDB**, une base vectorielle locale. L'indexation est incrémentale : seules les notes nouvelles ou modifiées sont retraitées.

### 4. Recherche à la requête

Quand vous posez une question dans le chat :

1. La question est elle-même vectorisée
2. ChromaDB identifie les chunks dont le vecteur est le plus proche → **similarité cosinus**
3. Ces chunks (vos notes) sont injectés comme contexte dans le prompt envoyé à Ollama
4. Ollama génère une réponse ancrée dans **votre coffre**, pas dans ses seules connaissances pré-entraînées

> C'est ce mécanisme qui permet de retrouver une note sur "les effets des écrans sur le sommeil" en posant la question "comment la lumière bleue affecte-t-elle le repos ?" — sans que ces mots exacts apparaissent dans la note.

---

## Défi principal : les coffres de grande taille

- Index vectoriel incrémental (mise à jour uniquement des notes nouvelles/modifiées)
- Chunking adaptatif des notes
- Métadonnées légères pour le filtrage rapide avant recherche sémantique

---

## Performances et recommandations matérielles

ObsiRAG est conçu pour fonctionner **en tâche de fond sur un MacBook Air M5 16 Go** — la machine de référence du projet. L'ensemble du traitement (indexation, génération d'insights, synapses) tourne de façon transparente sans perturber l'utilisation normale : navigation web, rédaction dans Obsidian, appels visio.

**Temps d'amorçage initial :** pour un coffre d'environ 200 notes, comptez **2 à 3 jours** pour que l'ensemble des insights soit généré.

Ce délai est intentionnel et s'explique par la mécanique du cycle :

- L'auto-learner se réveille **toutes les 60 minutes** et traite au maximum **3 notes nouvelles** par cycle (full-scan)
- Pour chaque note, il génère 3 questions et effectue des appels LLM espacés de **15 secondes** entre chaque question, et de **30 secondes** entre chaque note
- Résultat : 200 notes ÷ 3 notes/cycle × 60 min/cycle ≈ **67 heures**, soit environ 3 jours en fonctionnement continu

Ces pauses sont délibérées — elles garantissent qu'Ollama reste disponible pour le chat en temps réel et que la machine n'est pas saturée en arrière-plan. Les paramètres `AUTOLEARN_FULLSCAN_PER_RUN` et `AUTOLEARN_INTERVAL_MINUTES` dans `.env` permettent d'accélérer l'amorçage si vous le souhaitez (ex. 5 notes/cycle toutes les 30 min pour traiter le coffre en moins d'une journée).

Une fois l'amorçage terminé, seules les notes nouvelles ou récemment modifiées sont retraitées à chaque cycle — le fonctionnement courant est quasi-instantané.

Pour les détails de débit, temps de traitement par note et choix du modèle : voir [docs/performances.md](docs/performances.md).

---

## Modèles IA utilisés via Ollama

ObsiRAG utilise **Ollama** comme serveur IA local (API compatible OpenAI). Deux modèles sont nécessaires :

| Usage                       | Opération                                    | Modèle configuré                                 |
| --------------------------- | -------------------------------------------- | ------------------------------------------------ |
| **Chat / RAG**              | Réponses aux questions sur le coffre         | `LMSTUDIO_CHAT_MODEL` (ex. `gemma3:4b`)          |
| **Génération de questions** | Auto-learner — questions ancrées dans le champ sémantique de chaque note | Même modèle que le chat                          |
| **Synapses & synthèses**    | Connexions implicites, synthèse hebdomadaire | Même modèle que le chat                          |
| **Embeddings**              | Vectorisation des notes et des requêtes      | `LMSTUDIO_EMBED_MODEL` (ex. `nomic-embed-text`)  |

> Un seul modèle de chat suffit pour tout. Configurer `LMSTUDIO_CHAT_MODEL` dans `.env` avec le nom exact du modèle Ollama.

Le modèle doit avoir une fenêtre de contexte d'au moins **4096 tokens**. 8192+ est recommandé pour les coffres volumineux. Ajuster `LMSTUDIO_CONTEXT_SIZE` en conséquence.

Les embeddings sont gérés par Ollama via `LMSTUDIO_EMBED_MODEL` (`nomic-embed-text` par défaut, 768 dimensions) — les calculs s'effectuent sur le GPU/ANE du Mac, sans charge CPU dans Docker.

---

## Stack technique

| Composant          | Technologie                                                        |
| ------------------ | ------------------------------------------------------------------ |
| Langage            | Python 3.11                                                        |
| Déploiement        | Docker / Docker Compose                                            |
| IA                 | Ollama (API locale, compatible OpenAI)                             |
| Base vectorielle   | ChromaDB                                                           |
| Embeddings         | Ollama — `nomic-embed-text` (768 dimensions, Metal/ANE)            |
| Interface          | Streamlit                                                          |
| Graphe             | NetworkX + Pyvis                                                   |
| Recherche web      | DuckDuckGo Search (sources fiables)                                |
| Entités NER        | spaCy + validation [WUDD.ai](http://localhost:5050) (top 5 000 entités officielles) |
| Géolocalisation    | Wikipedia Coordinates API → frontmatter `location:` (Obsidian Map View) |
| Coffre             | Obsidian (lecture seule)                                           |
| Artefacts générés  | `obsirag/insights/`, `obsirag/synthesis/`, `obsirag/synapses/`     |

---

## Fréquence et comportement de l'auto-learner

| Paramètre `.env` | Valeur par défaut | Rôle |
|---|---|---|
| `AUTOLEARN_INTERVAL_MINUTES` | **60 min** | Fréquence du cycle — l'auto-learner se réveille toutes les heures |
| `AUTOLEARN_LOOKBACK_HOURS` | **24 h** | Fenêtre de détection — seules les notes modifiées dans les dernières 24h sont candidates |
| `AUTOLEARN_MIN_REPROCESS_DAYS` | **7 jours** | Délai de grâce — une note déjà traitée ne sera pas retraitée avant 7 jours |

Le premier cycle démarre **5 minutes après le lancement du container**, pour laisser le temps à Ollama d'être prêt.

> Ces trois paramètres permettent d'adapter le comportement selon l'usage : un intervalle plus court (ex. 30 min) pour un coffre très actif, un lookback plus large (ex. 48h) pour rattraper des notes modifiées en dehors des heures habituelles, et un `MIN_REPROCESS_DAYS` plus court si vous souhaitez qu'une note soit ré-enrichie plus fréquemment.

---

## Installation

```bash
# Installer Ollama (si ce n'est pas déjà fait)
curl -fsSL https://ollama.com/install.sh | sh

# Télécharger les modèles nécessaires
ollama pull gemma3:4b          # modèle chat (~3.3 GB)
ollama pull nomic-embed-text   # modèle embedding (~274 MB)

# Cloner le dépôt
git clone https://github.com/PatrickOstertagCH/obsirag.git
cd obsirag

# Configurer l'environnement
cp .env.example .env
# Éditer .env : renseigner VAULT_PATH (LMSTUDIO_BASE_URL pointe déjà sur Ollama par défaut)

# Lancer
docker compose up -d
```

L'interface est accessible sur [http://localhost:8501](http://localhost:8501).

---

## Statut

Projet actif — développé de façon créative et itérative avec Claude Code.

Le dépôt est public. Contributions et idées bienvenues.
