# Project Brief

Construire une application ObsiRAG en Expo Router + React Native + TypeScript strict.

## Produit

Application mobile/web cliente d'un backend ObsiRAG existant expose en HTTP/SSE.

## MVP attendu

1. configuration du backend
2. dashboard systeme
3. conversations
4. chat avec streaming
5. notes detail
6. insights
7. settings

## Contraintes

- mobile-first
- conversation jamais perdue
- DTO strictement types
- backend Python conserve
- pas de secret en dur dans le frontend
- mode mock disponible pour developpement UI

## Architecture attendue

- Expo Router pour la navigation
- React Query pour les donnees serveur
- Zustand pour brouillons et preferences locales
- couche API centralisee
- separation nette `app`, `features`, `components`, `services`, `types`

## Reference principale

Le developpement doit respecter `../docs/react-expo-specification.md`.
