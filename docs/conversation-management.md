# Gestion des conversations — ObsiRAG

Ce document décrit le mécanisme utilisé par ObsiRAG pour gérer une conversation multi-tours dans le chat, en particulier les **relances courtes**, la **sélection de la note principale**, le **formatage des réponses** et les **garde-fous anti hors-sujet**.

---

## Objectif

Le problème principal d'un chat RAG n'est pas seulement de générer une bonne réponse, mais de **retrouver les bons extraits** lorsque l'utilisateur ne répète pas explicitement le sujet à chaque tour.

Exemple typique :

1. `parle moi de Artemis II`
2. `tu as plus de détail sur les objectifs`

Sans mécanisme conversationnel, la seconde requête peut être interprétée comme une recherche générique sur le mot `objectifs`, ce qui mène à des notes sans rapport ou à un fallback web inutile.

Le rôle du mécanisme conversationnel est donc de :

- conserver le sujet courant entre deux tours
- réinjecter ce sujet dans la récupération RAG quand la nouvelle question est ambiguë
- limiter le contexte aux notes vraiment pertinentes
- maintenir une réponse lisible et structurée

---

## Vue d'ensemble du flux

Pour chaque message utilisateur, le pipeline suit les étapes suivantes :

1. **Lecture de l'historique récent**
2. **Détection éventuelle d'une relance ambiguë**
3. **Résolution de la question dans le fil**
4. **Retrieval sur la question résolue**
5. **Filtrage lexical anti hors-sujet**
6. **Sélection d'une note dominante si la requête est mono-sujet**
7. **Construction du contexte envoyé au modèle**
8. **Génération de la réponse**
9. **Post-traitement de la réponse**
10. **Affichage des sources avec note principale**

---

## 1. Historique de conversation

Le chat transmet les derniers messages au pipeline RAG. Cet historique sert à deux choses distinctes :

- **génération** : les derniers tours sont ajoutés au prompt envoyé au LLM
- **retrieval conversationnel** : l'historique est analysé pour retrouver le sujet courant quand la nouvelle question est elliptique

Point important : avant la correction récente, l'historique était déjà transmis au LLM, mais **pas utilisé pour la récupération des notes**. C'est cette asymétrie qui faisait perdre le sujet entre deux questions.

---

## 2. Détection des relances ambiguës

Une question est considérée comme une relance si elle ressemble à un prolongement conversationnel et qu'elle ne contient pas déjà un sujet autonome suffisamment net.

Exemples de formulations reconnues :

- `tu as plus de détail sur les objectifs`
- `et la durée de la mission ?`
- `peux-tu détailler ?`
- `et concernant la suite ?`

Le système évite en parallèle de traiter comme un vrai sujet des expressions trop génériques telles que :

- `les objectifs`
- `la durée`
- `les détails`
- `les informations`

Ces expressions sont volontairement considérées comme des **références conversationnelles** et non comme des thèmes autonomes.

---

## 3. Résolution de la question dans le fil

Quand une relance est détectée, ObsiRAG parcourt les messages récents en sens inverse pour retrouver le dernier sujet exploitable.

Le sujet peut être extrait depuis :

- la dernière question utilisateur
- la dernière réponse assistant
- un nom propre
- une entité explicitement mentionnée
- un thème mono-sujet reconnu

Si un sujet est trouvé, la requête est réécrite avant la récupération.

Exemple :

- question utilisateur : `tu as plus de détail sur les objectifs`
- sujet retrouvé dans l'historique : `Artemis II`
- requête résolue : `tu as plus de détail sur les objectifs concernant Artemis II`

Cette forme résolue est utilisée pour le retrieval, le scoring des notes et la construction du contexte. Le prompt garde aussi la question originale pour que la réponse reste naturelle dans le chat.

---

## 4. Retrieval mono-sujet et note dominante

Quand la requête correspond à un sujet unique, ObsiRAG ne se contente plus d'un simple top-k de chunks. Il cherche une **note dominante**.

### Principe

Les chunks récupérés sont regroupés par note, puis chaque note est scorée selon :

- présence du sujet dans le titre
- présence du sujet dans les entités extraites
- présence du sujet dans le texte du chunk
- meilleur score de similarité observé
- quantité de texte informatif disponible

La meilleure note devient la **note principale**.

### Effet sur le contexte

Une fois la note principale trouvée, le pipeline :

- récupère plusieurs chunks de cette note
- limite les autres notes à un rôle d'appoint
- envoie donc au LLM un contexte fortement recentré sur le sujet demandé

Cela réduit fortement les réponses diluées ou multi-axes sur une question qui devrait rester mono-sujet.

---

## 5. Filtrage lexical anti hors-sujet

Le retrieval vectoriel seul peut parfois faire remonter des notes faibles ou lexicalement trompeuses, surtout sur des requêtes courtes.

Pour limiter ce problème, ObsiRAG applique un **filtrage lexical complémentaire** sur certaines requêtes mono-sujet (`entity`, `general`, `general_kw_fallback`).

Le filtre vérifie notamment :

- que le titre ou le texte contient réellement des termes du sujet
- que ce recouvrement n'est pas purement accidentel
- que le score minimum reste compatible avec une vraie proximité sémantique

Si aucun chunk fiable ne passe ce filtre, le pipeline vide le contexte et coupe la génération.

Résultat : au lieu d'inventer une réponse à partir d'une mauvaise note, ObsiRAG répond immédiatement :

`Cette information n'est pas dans ton coffre.`

---

## 6. Gestion du fallback web

Le fallback web n'est déclenché dans l'UI que lorsque la réponse du coffre est un sentinel pur :

- `Cette information n'est pas dans ton coffre.`

Le mécanisme conversationnel réduit donc les faux fallback web de deux façons :

- il reformule les relances ambiguës avec le bon sujet
- il évite les faux positifs de retrieval sur des notes hors sujet

Autrement dit, le web ne doit intervenir que lorsqu'il manque vraiment de la matière dans le coffre, pas parce que le sujet a été perdu entre deux tours.

---

## 7. Formatage des réponses

Les réponses mono-sujet sont désormais formatées en Markdown avec deux intertitres fixes :

- `### Aperçu de ...`
- `### Détails utiles`

Objectif : améliorer la lisibilité dans le chat sans retomber dans une structure de synthèse comparative.

### Comportement attendu

- section `Aperçu` : cadrage rapide du sujet
- section `Détails utiles` : faits, étapes, contraintes, dates, éléments saillants présents dans les notes

Si le modèle répond encore sous forme de bloc, un post-traitement essaie de reconstruire cette structure automatiquement.

Les réponses d'étude multi-thèmes, elles, conservent leur structure distincte avec plusieurs chapitres.

---

## 8. Affichage des sources dans l'UI

Le chat n'affiche plus seulement une liste plate de sources.

Les sources renvoyées par le pipeline sont annotées avec un marqueur `is_primary` quand elles appartiennent à la note dominante. L'interface :

- affiche une ligne `Note principale : ...`
- conserve cette information après déduplication des sources
- marque la note concernée comme `Principale` dans l'expander des sources

Cela permet de comprendre immédiatement quelle note a servi de base au raisonnement principal.

---

## 9. Cas couverts par le mécanisme

### Cas bien pris en charge

- question explicite suivie d'une relance courte
- sujet mono-note ou fortement concentré dans une note
- sujet mentionné dans la dernière réponse assistant plutôt que dans la dernière question utilisateur
- requête générale mono-sujet qui n'a en réalité aucun support fiable dans le coffre

### Cas encore délicats

- relances très longues contenant plusieurs objets flous à la fois
- changement de sujet implicite sans signal lexical clair
- questions du type *"et pour l'autre ?"* après une synthèse multi-thèmes
- historique très long avec plusieurs sujets proches qui se succèdent

Ces cas peuvent nécessiter une résolution conversationnelle plus avancée sur plusieurs tours ou un mécanisme explicite de `current topic` en session.

---

## 10. Résumé opérationnel

Le mécanisme conversationnel actuel repose sur quatre idées simples :

1. **détecter** qu'une question est une relance
2. **retrouver** le dernier sujet du fil
3. **réécrire** la requête avant la récupération
4. **resserrer** le contexte autour d'une note principale et de chunks lexicalement fiables

Ce n'est pas une mémoire générale au sens LLM du terme. C'est une mémoire **pragmatique de retrieval**, conçue pour empêcher le sujet de se perdre entre deux tours et pour réduire les réponses hors contexte.