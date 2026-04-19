# ObsiRAG Expo

Client Expo Router pour la reecriture d'ObsiRAG en React Native + TypeScript.

## Objectif

Ce sous-projet fournit l'interface produit principale actuelle d'ObsiRAG, basee sur Expo web, et remplace l'ancien role central de l'UI Streamlit. Il fournit notamment :

- Expo Router
- React Query
- Zustand persistant
- client API deja structure
- ecrans MVP conformes a la specification produit

Le backend RAG Python n'est pas reimplementé ici. Le projet est concu pour etre branche a une API ObsiRAG exposee en HTTP/SSE.

## Fonctionnellement inclus

- configuration serveur
- dashboard systeme
- liste des conversations
- detail de conversation avec streaming SSE backend ou fallback mock
- affichage des sources, de la note principale et de la provenance coffre/web/hybride
- recherche sur le web via le backend avec resume de requete et sources DDG
- affichage des contextes d'entites detectees (NER) renvoyes par l'API
- liste des insights
- detail d'insight
- vue graphe avec filtres, recherche texte, spotlight et notes recentes
- vue note
- settings

## Apercu visuel

### Dashboard systeme

La capture ci-dessous est la meilleure illustration de l'ecran de pilotage runtime : etat du backend, disponibilite du LLM, indexation, metriques et activite auto-learner.

![Capture Expo - dashboard systeme](../docs/Screen-Captures/Dashboard.png)

### Liste des conversations

Cette capture se place naturellement avec les fonctionnalites de fil de discussion : reprise multi-tour, recherche locale et suppression d'un fil.

![Capture Expo - liste des conversations](../docs/Screen-Captures/Chat - Conversations.png)

### Detail d'un insight

Cette capture complete la section Insights : on y voit la provenance, les tags, les entites detectees et le rendu question/reponse de l'artefact.

![Capture Expo - detail d'un insight](../docs/Screen-Captures/Insights - exemple 1 - Question - Réponse.png)

## Lancer le projet

```bash
cd obsirag-expo
npm install
npm run start
```

Puis :

- `i` pour iOS
- `a` pour Android
- `w` pour web

Pour lancer directement le GUI web depuis la racine du depot :

```bash
./scripts/run_expo_web.sh
```

URL du GUI web : `http://localhost:8081`

URL du backend API : `http://localhost:8000`

Depuis la racine du depot, le cycle de vie recommande est :

```bash
./start.sh
./status.sh
./stop.sh
```

`./start.sh` relance l'API FastAPI et l'interface Expo web. L'auto-learner reste gere a part via `launchd` et `./install_service.sh`.

## Session et backend

Le store local demarre desormais en mode live avec une API ObsiRAG sur `http://localhost:8000`.

Les endpoints principaux deja exploites par le client sont :

- `/api/v1/system/status`
- `/api/v1/conversations`
- `/api/v1/notes/search`
- `/api/v1/graph` et `/api/v1/graph/subgraph`
- `/api/v1/web-search`

Si tu veux revenir en mode mock :

1. ouvrir `Settings`,
2. utiliser `Basculer en mock`.

Si ton backend exige un token :

1. ouvrir l'ecran de configuration serveur,
2. renseigner l'URL du backend,
3. saisir le token,
4. enregistrer la session.

## Mode mock

Le mode mock reste disponible pour travailler sans backend.

1. ouvrir l'ecran de configuration serveur,
2. activer `Utiliser le backend mock`,
3. renseigner l'URL du backend,
4. ou revenir ensuite en mode live.

## Structure

- `app/` : routes Expo Router
- `components/` : composants UI et metier
- `features/` : hooks et logique d'ecran
- `services/api/` : client API et mocks
- `services/storage/` : persistance securisee
- `store/` : etat local persistant
- `types/` : contrats TypeScript
- `spec/` : elements importables et complements

## Documents de reference

- `../docs/react-expo-specification.md`
- `spec/project-brief.md`
- `spec/api-contract.md`

## Prochaines etapes conseillees

1. renforcer le garde de session et les redirections auth
2. remplacer le rendu texte des notes par un renderer markdown complet
3. enrichir la navigation du graphe et des sources
4. ajouter tests unitaires et e2e Expo
