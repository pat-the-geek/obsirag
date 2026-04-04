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
- **Coffre en lecture seule** : ObsiRAG ne modifie jamais vos notes Obsidian
- **Accès complet au coffre** : pas de fenêtre contextuelle limitée, l'ensemble du coffre est exploitable
- **Stockage interne** dans `obsirag/data/` à l'intérieur du coffre (arborescence gérée automatiquement par le système)
- **Déploiement Docker** : isolation propre, reproductible

---

## Architecture

```
obsirag/
├── chat/           # Interface de chat avec le coffre
└── learner/        # Moteur d'auto-apprentissage en tâche de fond
```

### Le Chat

Interface conversationnelle connectée à LM Studio (via son API OpenAI-compatible) et au moteur de recherche du coffre. Les requêtes sont traitées en combinant récupération sémantique et synthèse par l'IA.

### L'Auto-apprentissage (background learner)

Un processus léger tourne en arrière-plan et :
1. Détecte chaque jour les nouvelles notes ajoutées au coffre
2. Génère automatiquement des questions et prompts à partir du contenu des notes
3. **Apprend de vos requêtes** : chaque question posée dans le chat est analysée et intégrée pour affiner les futurs prompts générés automatiquement
4. Enrichit la base de connaissances interne dans `obsirag/data/`
5. Optimise l'arborescence de stockage de manière autonome

> Le learner est conçu pour consommer un minimum de CPU et s'exécuter très discrètement en tâche de fond.

---

## Défi principal : les coffres de grande taille

La gestion de coffres volumineux est l'enjeu technique central du projet. La stratégie envisagée repose sur :

- Un index vectoriel incrémental (mise à jour uniquement des notes nouvelles/modifiées)
- Une segmentation intelligente des notes (chunking adaptatif)
- Une hiérarchie de résumés automatiques pour ne pas charger l'intégralité du coffre en mémoire
- Des métadonnées légères pour le filtrage rapide avant la recherche sémantique

---

## Stack technique

| Composant       | Technologie                      |
|----------------|----------------------------------|
| Langage         | Python                           |
| Déploiement     | Docker / Docker Compose          |
| IA              | LM Studio (API locale)           |
| Coffre          | Obsidian (lecture seule)         |
| Stockage interne| `obsirag/data/` dans le coffre   |

---

## Statut

Projet en démarrage — développé de façon créative et itérative avec Claude Code.

Le dépôt est public. Contributions et idées bienvenues.
