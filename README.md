<p align="left">
  <img src="https://raw.githubusercontent.com/pat-the-geek/obsirag/main/src/ui/static/android-chrome-512x512.png" alt="ObsiRAG" width="120" />
</p>

# ObsiRAG

Un système RAG (Retrieval-Augmented Generation) local pour votre coffre Obsidian, tournant en Python dans Docker et utilisant l'API de LM Studio comme moteur IA.

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

Interface conversationnelle connectée à LM Studio (via son API OpenAI-compatible) et au moteur de recherche du coffre. Les requêtes sont traitées en combinant récupération sémantique et synthèse par l'IA.

### Cerveau — graphe de connaissances

Visualisation interactive des connexions entre vos notes (wikilinks et similarité sémantique). Navigation par dossiers et tags, zoom sur les nœuds les plus connectés.

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
| **Toutes les réponses QA ont échoué** | Erreur LM Studio (contexte dépassé, modèle non disponible…) pour les 3 questions | L'insight n'est pas sauvegardé |
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

> **Astuce** : Si une note attendue ne produit pas d'insight, vérifiez qu'elle est bien indexée (bouton "Re-indexer le coffre" dans le chat) et que le LLM est disponible dans LM Studio.

---

## Comment fonctionne la recherche sémantique

### 1. Découpage en chunks

Une note Obsidian peut être longue et couvrir plusieurs sujets. Pour permettre une recherche précise, chaque note est découpée en **morceaux (chunks)** d'environ 300 mots, avec un léger chevauchement entre chaque morceau pour préserver le contexte aux jonctions.

Le découpage respecte la structure de la note : d'abord par section (`## Titre`), puis par paragraphe, puis par mots si nécessaire. Chaque chunk hérite des métadonnées de la note (titre, tags, dates, wikilinks, entités NER…).

### 2. Vectorisation (embedding)

Chaque chunk est transformé en un **vecteur numérique** — une liste de ~768 nombres — par le modèle `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers, exécuté localement). Ce vecteur encode le *sens* du texte : deux passages sémantiquement proches produisent des vecteurs proches dans l'espace mathématique, même s'ils n'ont aucun mot en commun.

### 3. Stockage dans ChromaDB

Les vecteurs et leurs métadonnées sont stockés dans **ChromaDB**, une base vectorielle locale. L'indexation est incrémentale : seules les notes nouvelles ou modifiées sont retraitées.

### 4. Recherche à la requête

Quand vous posez une question dans le chat :

1. La question est elle-même vectorisée
2. ChromaDB identifie les chunks dont le vecteur est le plus proche → **similarité cosinus**
3. Ces chunks (vos notes) sont injectés comme contexte dans le prompt envoyé à LM Studio
4. LM Studio génère une réponse ancrée dans **votre coffre**, pas dans ses seules connaissances pré-entraînées

> C'est ce mécanisme qui permet de retrouver une note sur "les effets des écrans sur le sommeil" en posant la question "comment la lumière bleue affecte-t-elle le repos ?" — sans que ces mots exacts apparaissent dans la note.

---

## Défi principal : les coffres de grande taille

- Index vectoriel incrémental (mise à jour uniquement des notes nouvelles/modifiées)
- Chunking adaptatif des notes
- Métadonnées légères pour le filtrage rapide avant recherche sémantique

---

## Performances et recommandations matérielles

Temps de traitement, débit du scan, et choix du Mac Apple Silicon : voir [docs/performances.md](docs/performances.md).

---

## Modèles IA utilisés via LM Studio

ObsiRAG utilise LM Studio comme serveur IA local (API compatible OpenAI). Trois types d'appels sont effectués :

| Usage                       | Opération                                    | Exigences minimales                              |
| --------------------------- | -------------------------------------------- | ------------------------------------------------ |
| **Chat / RAG**              | Réponses aux questions sur le coffre         | 7–8B instruct (ex. Llama 3.1 8B, Gemma 4)        |
| **Génération de questions** | Auto-learner — questions ancrées dans le champ sémantique de chaque note | Même modèle que le chat                          |
| **Synapses & synthèses**    | Connexions implicites, synthèse hebdomadaire | Même modèle que le chat                          |

> Un seul modèle de chat suffit pour tout. Configurer `LMSTUDIO_CHAT_MODEL` dans `.env` avec le nom exact du modèle chargé dans LM Studio.

Le modèle doit avoir une fenêtre de contexte d'au moins **4096 tokens**. 8192+ est recommandé pour les coffres volumineux.

Les embeddings sont gérés **localement** par `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`) — aucun appel LM Studio n'est nécessaire pour l'indexation.

---

## Stack technique

| Composant          | Technologie                                                        |
| ------------------ | ------------------------------------------------------------------ |
| Langage            | Python 3.11                                                        |
| Déploiement        | Docker / Docker Compose                                            |
| IA                 | LM Studio (API locale, compatible OpenAI)                          |
| Base vectorielle   | ChromaDB                                                           |
| Embeddings         | sentence-transformers (multilingue)                                |
| Interface          | Streamlit                                                          |
| Graphe             | NetworkX + Pyvis                                                   |
| Recherche web      | DuckDuckGo Search (sources fiables)                                |
| Entités NER        | spaCy + validation [WUDD.ai](http://localhost:5050) (top 5 000 entités officielles) |
| Géolocalisation    | Wikipedia Coordinates API → frontmatter `location:` (Obsidian Map View) |
| Coffre             | Obsidian (lecture seule)                                           |
| Artefacts générés  | `obsirag/insights/`, `obsirag/synthesis/`, `obsirag/synapses/`     |

---

## Installation

```bash
# Cloner le dépôt
git clone https://github.com/PatrickOstertagCH/obsirag.git
cd obsirag

# Configurer l'environnement
cp .env.example .env
# Éditer .env : renseigner VAULT_PATH et LMSTUDIO_BASE_URL

# Lancer
docker compose up -d
```

L'interface est accessible sur [http://localhost:8501](http://localhost:8501).

---

## Statut

Projet actif — développé de façon créative et itérative avec Claude Code.

Le dépôt est public. Contributions et idées bienvenues.
