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
2. Génère automatiquement des questions perspicaces sur le contenu
3. Répond via RAG sur le coffre — et **complète avec le web** si la réponse est insuffisante
4. N'utilise que des **sources fiables** (Wikipédia, presse de référence, institutions, revues scientifiques…)
5. Sauvegarde les insights en Markdown dans `obsirag/insights/` avec indication de provenance et **références citées**
6. Génère une **synthèse hebdomadaire** le dimanche dans `obsirag/synthesis/`

> Les artefacts générés sont indexés et deviennent eux-mêmes interrogeables dans le chat.

### Page Insights

Consultation des artefacts, synapses et synthèses générés, avec historique des requêtes posées dans le chat.

---

## Défi principal : les coffres de grande taille

- Index vectoriel incrémental (mise à jour uniquement des notes nouvelles/modifiées)
- Chunking adaptatif des notes
- Métadonnées légères pour le filtrage rapide avant recherche sémantique

---

## Modèles IA utilisés via LM Studio

ObsiRAG utilise LM Studio comme serveur IA local (API compatible OpenAI). Trois types d'appels sont effectués :

| Usage                       | Opération                                    | Exigences minimales                              |
| --------------------------- | -------------------------------------------- | ------------------------------------------------ |
| **Chat / RAG**              | Réponses aux questions sur le coffre         | 7–8B instruct (ex. Llama 3.1 8B, Gemma 4)        |
| **Génération de questions** | Auto-learner — questions sur chaque note     | Même modèle que le chat                          |
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
