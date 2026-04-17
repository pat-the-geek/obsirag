# ObsiRAG Expo

Client Expo Router pour la reecriture d'ObsiRAG en React Native + TypeScript.

## Objectif

Ce sous-projet fournit une base exploitable pour migrer l'interface Streamlit actuelle vers :

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
- liste des insights
- detail d'insight
- vue graphe simplifiee
- vue note
- settings

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

## Session et backend

Le store local demarre desormais en mode live avec une API ObsiRAG sur `http://localhost:8000`.

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
