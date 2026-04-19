# Specification Complete — Reécriture ObsiRAG en React + Expo

## 1. Objet du document

Ce document sert de specification produit et technique pour reécrire ObsiRAG avec un frontend React base sur Expo.

Il est concu pour etre importe tel quel dans un nouveau projet afin de guider :

- le cadrage fonctionnel,
- l'architecture frontend et backend,
- le modele de donnees,
- les contrats d'API,
- les exigences non fonctionnelles,
- le plan de livraison.

Le but n'est pas de reproduire l'ancienne interface a l'identique, mais de conserver les invariants utiles d'ObsiRAG tout en basculant vers une application moderne, mobile-first, multi-plateforme.

## 2. Decision d'architecture

### 2.1 Decision principale

La reécriture cible une architecture en 2 couches :

1. un client Expo/React Native pour l'interface,
2. un backend applicatif separe pour la logique RAG, l'indexation, le graphe de connaissances, l'auto-apprentissage et l'acces au coffre Obsidian.

### 2.2 Justification

L'implementation actuelle repose sur :

- Python,
- MLX-LM sur Apple Silicon,
- ChromaDB,
- acces filesystem direct au vault Obsidian,
- watchers de fichiers,
- traitements d'arriere-plan planifies.

Ces capacites ne doivent pas etre portees telles quelles dans Expo :

- Expo ne doit pas heberger MLX ni ChromaDB localement,
- l'app mobile ne doit pas indexer directement un vault Obsidian desktop,
- les taches longues et le scheduler doivent rester cote serveur.

### 2.3 Conclusion technique

La cible recommandee est donc :

- Expo = couche presentation, navigation, cache UI, interaction utilisateur,
- Backend = moteur ObsiRAG, expose via API HTTP et WebSocket/SSE.

## 3. Vision produit cible

ObsiRAG vNext est un compagnon conversationnel de connaissance personnelle qui permet de :

- interroger son vault Obsidian en langage naturel,
- consulter les notes sources, leurs liens et leurs retroliens,
- visualiser le graphe de connaissance,
- consulter les insights, synapses et syntheses generes,
- suivre l'etat du systeme d'indexation et d'auto-apprentissage,
- poursuivre les conversations sur mobile, tablette et web.

## 4. Principes non negociables

### 4.1 Invariants metier a conserver

1. Les notes utilisateur ne sont jamais modifiees hors fonctionnalites explicitement prevues.
2. Les reponses RAG ne doivent pas s'appuyer sur des connaissances hors contexte sans le signaler.
3. Le fallback web ne doit se declencher que lorsqu'une information n'est pas disponible dans le coffre.
4. Les artefacts generes doivent etre tracables : source coffre, web ou hybride.
5. La conversation doit conserver un contexte exploitable pour le retrieval, pas seulement pour la generation.
6. Les sources doivent etre visibles, dedupees et la note principale doit etre identifiable.

### 4.2 Contraintes produit

1. L'application doit fonctionner sur iOS, Android et web via Expo.
2. Le mode principal est mobile-first.
3. Le backend peut tourner sur macOS local, sur un mini-serveur personnel ou dans un conteneur local reseau.
4. L'utilisateur doit pouvoir continuer a utiliser son vault Obsidian comme source de verite.

## 5. Perimetre fonctionnel

### 5.1 Perimetre MVP obligatoire

1. Authentification locale ou session simple protegee.
2. Liste des conversations.
3. Ecran de chat complet avec streaming.
4. Gestion du contexte conversationnel multi-tours.
5. Affichage des sources et de la note principale.
6. Consultation d'une note.
7. Recherche et navigation dans les insights.
8. Dashboard systeme minimal.
9. Parametres de connexion backend.
10. Persistance locale des brouillons et de l'historique recent cote client.

### 5.2 Perimetre V2 prioritaire

1. Graphe de connaissances interactif.
2. Visualisation Mermaid dans le chat.
3. Recherche web explicite apres reponse.
4. Vue des entites detectees.
5. Conversations sauvegardees et restaurables.
6. Suivi des jobs d'auto-apprentissage.

### 5.3 Perimetre V3

1. Notifications push de fin d'indexation ou d'insight genere.
2. Mode offline en lecture seule pour notes et conversations recentes.
3. Parametrage fin des strategies de retrieval.
4. Administration multi-vault ou multi-utilisateur.

### 5.4 Reperes visuels actuels

Les captures presentes dans `docs/Screen-Captures/` ne sont pas des maquettes abstraites. Elles servent de reference concrete pour les surfaces deja visibles ou deja suffisamment stabilisees pour guider le produit.

- Dashboard runtime : `Screen-Captures/Dashboard.png`
- Liste des conversations : `Screen-Captures/Chat - Conversations.png`
- Chat RAG avec sources et note principale : `Screen-Captures/Chat - IA - RAG depuis coffre.png`
- Chat avec viewer Mermaid : `Screen-Captures/Chat - Mermaid - integration.png` et `Screen-Captures/Chat - Mermaid - viewer.png`
- Graphe de connaissances : `Screen-Captures/Cerveau - Coffre - Notes - Synapses.png`
- Detail d'insight : `Screen-Captures/Insights - exemple 1 - Question - Réponse.png`

Ces captures doivent etre considerees comme des exemples de niveau d'information, de hierarchy visuelle et de densite fonctionnelle a conserver dans Expo, meme si le rendu final evolue.

### 5.5 Ecarts entre cible et implementation actuelle

Cette specification reste un document cible. Le depot actuel couvre deja une partie significative du perimetre, mais tout n'est pas au meme niveau de maturite.

Deja visible ou exploitable aujourd'hui dans le depot courant :

- dashboard systeme branche au backend,
- liste des conversations et detail de conversation,
- streaming de reponse cote API et client Expo avec mode mock de secours,
- affichage des sources, de la note principale et de la provenance,
- recherche web explicite cote backend,
- contextes d'entites NER dans les reponses,
- vue note,
- vue insights,
- vue graphe avec filtres, recherche texte, spotlight et notes recentes,
- cycle operatoire local `install_service.sh` + `start.sh` + `stop.sh` + `status.sh` pour worker, API et Expo.

Partiellement implemente ou encore en stabilisation :

- gestion de session simple et token backend,
- sauvegarde et restauration de conversations selon les flows backend disponibles,
- sous-graphes centres et experience mobile du graphe,
- exposition homogène de toutes les actions secondaires dans chaque ecran,
- alignement complet entre la specification cible et tous les ecrans Expo reels.

Toujours au stade cible / roadmap :

- notifications push,
- mode offline reel en lecture seule,
- parametrage fin des strategies de retrieval,
- administration multi-vault ou multi-utilisateur,
- finition complete de toutes les surfaces Mermaid dans Expo si un rendu natif stable est retenu.

Regle de lecture : quand ce document entre en conflit avec l'etat reel du code, considerer le code et les README operationnels comme source de verite pour le present, et cette specification comme reference de convergence produit.

## 6. Utilisateurs cibles

### 6.1 Persona principal

Utilisateur individuel avancé qui :

- possede un vault Obsidian personnel,
- veut interroger sa base de connaissances de partout,
- accepte une architecture perso locale ou auto-hebergee,
- privilegie la qualite du retrieval et la tracabilite sur l'effet demo.

### 6.2 Persona secondaire

Utilisateur technique qui veut piloter le systeme :

- indexation,
- performance,
- auto-learner,
- diagnostics,
- integrations futures.

## 7. Architecture cible

### 7.1 Vue d'ensemble

Le systeme cible se compose de 4 blocs :

1. Expo App
2. API Gateway / Backend App
3. Moteur RAG et traitements de fond
4. Stockage et sources

### 7.2 Expo App

Responsabilites :

- rendu UI,
- navigation,
- cache client,
- optimistic UI limitee,
- synchronisation conversationnelle,
- preferences locales,
- visualisation markdown, Mermaid et graphe.

### 7.3 Backend App

Responsabilites :

- authentification,
- orchestration des conversations,
- endpoints REST,
- streaming temps reel,
- exposition des etats de jobs,
- normalisation des donnees frontend.

### 7.4 Moteur RAG

Responsabilites :

- retrieval,
- prompting,
- generation,
- fallback web,
- auto-apprentissage,
- synapses,
- indexation,
- watcher du vault.

### 7.5 Stockages

1. Vault Obsidian : source documentaire et destination des artefacts markdown.
2. Base vectorielle : chunks et embeddings.
3. Stockage JSON/SQL backend : conversations, preferences, statuts, telemetry.
4. Stockage local Expo : cache UI, brouillons, derniers ecrans, auth token si necessaire.

## 8. Stack recommandee

### 8.1 Frontend Expo

- Expo SDK recent
- React Native
- Expo Router
- TypeScript strict
- TanStack Query pour les donnees distantes
- Zustand pour l'etat UI local non serveur
- React Hook Form + Zod pour les formulaires
- NativeWind ou Tamagui ou un design system maison leger
- react-native-markdown-display ou renderer markdown custom
- react-native-svg pour graphes et icones
- Victory Native ou equivalent pour metrics simples
- react-native-webview uniquement si necessaire pour Mermaid ou visualisations complexes

### 8.2 Backend recommande

Option recommandee : conserver le backend Python et l'exposer proprement via FastAPI.

Pourquoi :

- le coeur ObsiRAG est deja Python,
- MLX et Chroma y sont naturels,
- le cout de reécriture totale backend en Node serait eleve et risqué.

### 8.3 Contrat global

Frontend Expo neuf.
Backend Python nettoye en API produit.

## 9. Arborescence cible du nouveau projet frontend

```text
app/
  (auth)/
    login.tsx
    server-config.tsx
  (tabs)/
    index.tsx                # Dashboard
    chat/
      index.tsx             # liste conversations ou chat courant
      [conversationId].tsx
    insights/
      index.tsx
      [insightId].tsx
    graph.tsx
    note/
      [noteId].tsx
    settings.tsx
components/
  chat/
  notes/
  graph/
  insights/
  ui/
features/
  auth/
  chat/
  notes/
  insights/
  graph/
  settings/
  system/
services/
  api/
  realtime/
  storage/
  markdown/
  mermaid/
store/
types/
utils/
spec/
```

## 10. Domaines fonctionnels

### 10.1 Authentification et connexion backend

Le frontend doit permettre :

- de configurer l'URL du backend,
- de verifier la connectivite,
- de stocker une session,
- de gerer un backend local reseau ou distant.

MVP :

- mode single-user,
- token simple ou session password-protected,
- ecran de configuration au premier lancement.

### 10.2 Conversations

Chaque conversation est un fil persistant avec :

- identifiant,
- titre derive,
- date de mise a jour,
- messages,
- brouillon courant,
- stats de derniere generation,
- eventuels enrichissements associes.

Fonctionnalites :

- creer un fil,
- changer de fil,
- supprimer un fil,
- reprendre une conversation,
- sauvegarder une conversation en artefact markdown si le backend le supporte,
- restaurer les messages apres redemarrage client.

### 10.3 Chat RAG

Fonctionnalites obligatoires :

- saisie de prompt,
- reponse streamée token par token,
- rendu markdown,
- support des sources,
- affichage de la note principale,
- timeline ou statut de generation,
- etat explicite quand l'information n'est pas dans le coffre,
- bouton de recherche web explicite si applicable,
- reprise correcte des relances courtes,
- affichage des entites detectees dans la conversation avec leur type et leur contexte.

Precisions sur le NER du chat :

- le frontend consomme des entites detectees sur le texte combine question + reponse, pas uniquement sur la saisie utilisateur,
- il ne re-implemente ni l'extraction ni la validation des entites,
- il restitue les enrichissements retournes par l'API sans perdre la provenance ni le lien avec les notes source,
- il doit pouvoir compacter la vue NER sur mobile sans faire disparaitre les informations essentielles.

### 10.4 Conversation intelligence

Le frontend ne doit pas reimplementer la logique conversationnelle profonde, mais doit exposer les bons signaux fournis par le backend :

- question resolue eventuelle,
- note principale,
- intent de retrieval,
- statut sentinel,
- fallback web,
- provenance de la reponse,
- `entityContexts` enrichis avec preuve, relation et contexte web compact.

### 10.5 Notes

Le module note doit permettre :

- afficher une note markdown,
- suivre les wikilinks,
- afficher les tags,
- afficher les metadonnees,
- afficher les retroliens,
- ouvrir une note source depuis le chat, le graphe ou les insights.

### 10.6 Insights et synapses

Le module insights doit permettre :

- lister les artefacts generes,
- filtrer par type,
- rechercher par texte ou tag,
- consulter le contenu,
- afficher la provenance,
- ouvrir les notes reliees,
- distinguer insight, synapse, synthese, conversation sauvegardee.

### 10.7 Graphe de connaissances

Le module graphe doit afficher :

- noeuds = notes,
- aretes = wikilinks,
- taille du noeud = importance ou connexions,
- couleur = dossier ou type,
- filtres par dossier, tag, type,
- ouverture d'une note depuis un noeud,
- resume metrique : nombre de noeuds, densite, top noeuds.

Sur mobile, le graphe doit proposer 2 modes :

- vue d'ensemble simplifiee,
- focus sur sous-graphe centre sur une note.

### 10.8 Dashboard systeme

Le dashboard doit afficher :

- etat du backend,
- etat du modele,
- nombre de notes indexees,
- nombre de chunks,
- etat de l'indexation,
- etat de l'auto-learner,
- derniers logs ou alertes importantes,
- acces rapides.

### 10.9 Parametres

Le module settings doit couvrir :

- URL backend,
- etat de la connexion,
- theme,
- preferences UI,
- diagnostics,
- lecture des grandes statistiques backend,
- eventuellement export ou reset du cache local.

## 11. Ecrans a produire

### 11.1 Onboarding / Configuration serveur

Objectif : connecter l'app a une instance ObsiRAG.

Contenu :

- champ URL backend,
- bouton tester la connexion,
- statut de compatibilite version API,
- saisie de mot de passe ou token si necessaire,
- validation.

### 11.2 Dashboard

Sections :

- statut systeme,
- indexation,
- auto-learner,
- volume documentaire,
- actions rapides,
- alertes.

Repere visuel actuel : `Screen-Captures/Dashboard.png`.

### 11.3 Liste des conversations

Comportements :

- tri par derniere activite,
- recherche locale,
- creation d'un nouveau fil,
- badge de nombre de tours,
- preview du dernier message utile.

Repere visuel actuel : `Screen-Captures/Chat - Conversations.png`.

### 11.4 Ecran de chat

Blocs :

- header de conversation,
- liste virtualisee des messages,
- messages utilisateur,
- messages assistant,
- statut live de generation,
- sources,
- note principale,
- enrichissements eventuels,
- composer avec brouillon persistant,
- actions secondaires.

Actions secondaires :

- enregistrer conversation,
- effacer historique du fil,
- rechercher sur le web,
- ouvrir une note citee.

Reperes visuels actuels : `Screen-Captures/Chat - IA - RAG depuis coffre.png`, `Screen-Captures/Chat - Mermaid - integration.png` et `Screen-Captures/Chat - Mermaid - viewer.png`.

### 11.5 Ecran note

Blocs :

- titre,
- metadonnees,
- markdown,
- tags,
- retroliens,
- liens sortants,
- bouton ouvrir dans Obsidian si deeplink disponible.

### 11.6 Ecran insights

Blocs :

- filtres,
- recherche,
- tabs insight/synapse/synthese/conversation,
- liste d'artefacts,
- lecture detaillee.

Repere visuel actuel : `Screen-Captures/Insights - exemple 1 - Question - Réponse.png`.

### 11.7 Ecran graphe

Blocs :

- resume des metrics,
- filtres,
- canvas graphe,
- top noeuds,
- fiche d'un noeud selectionne.

Repere visuel actuel : `Screen-Captures/Cerveau - Coffre - Notes - Synapses.png`.

### 11.8 Ecran settings

Blocs :

- connectivite,
- backend info,
- theme,
- stockage local,
- debug et logs.

## 12. Experience utilisateur

### 12.1 Regles UX du chat

1. Le dernier message ne doit jamais etre ecrase lors d'un nouveau prompt.
2. Le brouillon doit survivre aux changements d'ecran.
3. Le streaming doit etre visible sans bloquer le scroll.
4. Les sources doivent etre lisibles sur mobile sans expander complexe obligatoire.
5. Les erreurs doivent etre actionnables.
6. L'utilisateur doit voir si la reponse provient du coffre, du web ou des deux.

### 12.2 Regles UX mobile-first

1. Les listes doivent etre virtualisees.
2. Les surfaces d'action doivent etre tactiles.
3. Les ecrans doivent rester utiles hors paysage desktop.
4. Le graphe doit degrader proprement sur petit ecran.

## 13. Modeles de donnees frontend

### 13.1 ConversationSummary

```ts
type ConversationSummary = {
  id: string;
  title: string;
  preview: string;
  updatedAt: string;
  turnCount: number;
  messageCount: number;
  isCurrent?: boolean;
};
```

### 13.2 ChatMessage

```ts
type ChatMessage = {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt: string;
  sources?: SourceRef[];
  primarySource?: SourceRef | null;
  stats?: GenerationStats;
  timeline?: string[];
  queryOverview?: QueryOverview | null;
  entityContexts?: EntityContext[];
  enrichmentPath?: string | null;
  provenance?: 'vault' | 'web' | 'hybrid' | 'unknown';
  sentinel?: boolean;
};
```

Attentes de rendu pour `entityContexts` dans un `ChatMessage` :

- presenter un libelle humain du type d'entite,
- montrer les notes du coffre reliees quand elles existent,
- exposer l'image associee quand l'API en fournit une,
- rendre visible l'explication de relation avec le sujet,
- afficher un contexte web compact quand `ddgKnowledge` est present,
- proposer une version compacte mobile et une version detaillee web/desktop.

### 13.3 SourceRef

```ts
type SourceRef = {
  filePath: string;
  noteTitle: string;
  dateModified?: string;
  score?: number;
  isPrimary?: boolean;
};
```

### 13.4 QueryOverview

```ts
type QueryOverview = {
  query: string;
  searchQuery: string;
  summary: string;
  sources: WebSource[];
};
```

### 13.5 EntityContext

```ts
type EntityContext = {
  type: string;
  typeLabel: string;
  value: string;
  mentions?: number;
  lineNumber?: number;
  relationExplanation?: string;
  imageUrl?: string;
  tag?: string;
  notes: RelatedNote[];
  ddgKnowledge?: DdgKnowledge;
};
```

### 13.6 NoteDetail

```ts
type NoteDetail = {
  id: string;
  filePath: string;
  title: string;
  bodyMarkdown: string;
  tags: string[];
  frontmatter: Record<string, unknown>;
  backlinks: RelatedNote[];
  links: RelatedNote[];
  dateModified?: string;
  noteType?: string;
};
```

### 13.7 InsightItem

```ts
type InsightItem = {
  id: string;
  title: string;
  filePath: string;
  kind: 'insight' | 'synapse' | 'synthesis' | 'conversation';
  provenance?: 'vault' | 'web' | 'hybrid';
  tags: string[];
  dateModified?: string;
  excerpt?: string;
};
```

### 13.8 SystemStatus

```ts
type SystemStatus = {
  backendReachable: boolean;
  llmAvailable: boolean;
  notesIndexed: number;
  chunksIndexed: number;
  indexing?: {
    running: boolean;
    processed: number;
    total: number;
    current?: string;
  };
  autolearn?: {
    active: boolean;
    note?: string;
    step?: string;
    log?: string[];
    nextRunAt?: string;
  };
  alerts?: SystemAlert[];
};
```

## 14. Contrats API backend

### 14.1 Principes

1. REST pour les ressources.
2. SSE ou WebSocket pour le streaming de chat.
3. DTO stables et versionnes.
4. Aucune fuite des structures internes Python non normalisees.

### 14.2 Endpoints minimaux

#### Health

`GET /api/v1/health`

Retour :

```json
{
  "status": "ok",
  "version": "1.0.0",
  "llmAvailable": true,
  "vectorStoreAvailable": true
}
```

#### System status

`GET /api/v1/system/status`

#### Conversations

`GET /api/v1/conversations`
`POST /api/v1/conversations`
`GET /api/v1/conversations/:id`
`DELETE /api/v1/conversations/:id`
`POST /api/v1/conversations/:id/save`

#### Messages

`POST /api/v1/conversations/:id/messages`

Mode recommande :

- HTTP pour envoyer le prompt,
- SSE sur une URL dediee pour le flux de tokens.

Option alternative : un endpoint unique WebSocket pour chat streaming.

#### Notes

`GET /api/v1/notes/:id`
`GET /api/v1/notes`
`GET /api/v1/notes/search?q=`

#### Insights

`GET /api/v1/insights`
`GET /api/v1/insights/:id`

#### Graph

`GET /api/v1/graph`
`GET /api/v1/graph/subgraph?noteId=`

#### Search web explicit

`POST /api/v1/web-search`

#### Jobs / runtime

`POST /api/v1/index/rebuild`
`GET /api/v1/index/status`
`GET /api/v1/autolearn/status`

### 14.3 Reponse d'un message assistant

Le backend doit renvoyer un payload final normalise proche de :

```json
{
  "message": {
    "id": "msg_123",
    "role": "assistant",
    "content": "### Apercu de ...\n\n...",
    "sentinel": false,
    "provenance": "vault",
    "sources": [],
    "primarySource": null,
    "stats": {
      "tokens": 412,
      "ttft": 1.2,
      "total": 8.5,
      "tps": 54.1
    },
    "timeline": [
      "Analyse de la requete",
      "Recherche dans le coffre",
      "Generation"
    ],
    "queryOverview": null,
    "entityContexts": [],
    "enrichmentPath": null
  }
}
```

### 14.4 Evenements de streaming recommandes

```text
message_start
retrieval_status
token
sources_ready
message_complete
message_error
```

## 15. Persistance locale cote Expo

### 15.1 Donnees a stocker localement

- configuration backend,
- token de session si utilise,
- theme,
- conversation ouverte recemment,
- brouillons de conversation,
- cache de listes,
- dernier system status exploitable.

### 15.2 Technologies recommandees

- SecureStore pour token sensible,
- AsyncStorage ou MMKV pour cache UI,
- persistance Zustand pour preferences locales.

### 15.3 Donnees a ne pas considerer comme source de verite

- historique conversationnel complet,
- system status officiel,
- etat d'indexation officiel,
- contenu canonique des notes.

Ces donnees doivent venir du backend.

## 16. Navigation

Navigation recommandee avec Expo Router :

1. groupe auth/config,
2. tabs principales,
3. routes detail pour conversation, note, insight.

Tabs recommandees :

1. Dashboard
2. Chat
3. Insights
4. Graphe
5. Settings

## 17. Design system

### 17.1 Direction visuelle

Le produit ne doit pas ressembler a un wrapper IA generique. Il doit exprimer :

- outil personnel de connaissance,
- precision,
- calme,
- densite informationnelle maitrisée.

### 17.2 Recommandations UI

- fond clair casse ou sombre profond selon theme,
- accent principal non violet par defaut,
- typographie editoriale serieuse,
- cartes denses mais lisibles,
- usage fort de badges semantiques : provenance, type de note, note principale.

### 17.3 Composants de base

- AppHeader
- StatusBadge
- SourceChip
- PrimarySourceCard
- ChatBubbleUser
- ChatBubbleAssistant
- GenerationTimeline
- NoteLinkCard
- EntityCard
- InsightListItem
- GraphLegend

## 18. Comportements critiques du chat

### 18.1 Regles metier obligatoires

1. Les relances courtes doivent rester rattachees au sujet precedent quand le backend le permet.
2. Le sentinel doit etre distingue d'une vraie reponse.
3. Une reponse mixte ne doit pas etre traitee comme un sentinel pur.
4. Les sources doivent etre dedupees par note.
5. La note principale doit etre mise en avant.
6. La conversation doit survivre aux rerenders frontend et aux redemarrages de l'app.

### 18.2 Etats UI a couvrir

- idle,
- sending,
- retrieving,
- generating,
- complete,
- error,
- degraded backend,
- disconnected.

## 19. Synchronisation temps reel

### 19.1 Chat

Le streaming doit etre temps reel.

### 19.2 Status backend

Le dashboard peut etre rafraichi par polling intelligent toutes les 5 a 15 secondes ou via push serveur.

### 19.3 Jobs longs

Indexation et auto-learner peuvent exposer :

- polling pour MVP,
- WebSocket plus tard.

## 20. Gestion des erreurs

### 20.1 Erreurs a distinguer

1. backend inaccessible,
2. session invalide,
3. LLM indisponible,
4. vector store indisponible,
5. note introuvable,
6. erreur de streaming,
7. timeout job long,
8. fallback web sans resultat.

### 20.2 Comportement attendu

1. message utilisateur clair,
2. retry possible si pertinent,
3. conservation du prompt en brouillon en cas d'echec,
4. pas de perte silencieuse de conversation.

## 21. Accessibilite

Exigences minimales :

- contraste correct,
- tailles tactiles suffisantes,
- labels accessibles,
- navigation clavier utile sur web,
- lecture lisible des messages et sources,
- etat de streaming annonce visuellement.

## 22. Performance

### 22.1 Objectifs frontend

- ouverture app < 2 s hors premier boot,
- affichage liste conversations < 300 ms depuis cache local,
- affichage detail conversation < 500 ms hors streaming,
- scroll fluide sur 500+ messages virtualises,
- pas de rerender massif du thread complet a chaque token si evitables.

### 22.2 Objectifs backend exposes a l'UI

- TTFT expose,
- temps total expose,
- nombre de tokens expose,
- progression retrieval exploitable.

## 23. Securite

1. Aucun secret hardcode dans le frontend.
2. Les tokens doivent etre stockes en zone securisee.
3. Le backend doit filtrer les chemins de fichiers exposes.
4. Les acces aux fichiers du vault doivent passer par des endpoints controles.
5. Les logs frontend ne doivent pas contenir de contenu sensible complet en production.

## 24. Observabilite

### 24.1 Frontend

- erreurs runtime,
- temps de navigation,
- evenements critiques : envoi prompt, reponse recue, echec streaming,
- desactivation facile en mode prive local.

### 24.2 Backend visible dans l'app

- rag_queries_total,
- rag_sentinel_answers_total,
- autolearn metrics,
- indexation status,
- alertes critiques.

## 25. Strategie de migration depuis l'existant

### 25.1 Ce qui doit etre conserve

- vault et artefacts markdown,
- base vectorielle si compatible,
- logique RAG Python,
- logique auto-learner Python,
- mecanismes conversationnels.

### 25.2 Ce qui doit etre remplace

- ancienne UI web,
- etat session purement lie au runtime historique,
- widgets et flux de rendu specifiques a cette interface.

### 25.3 Strategie recommandee

1. Exposer l'existant via API FastAPI.
2. Construire Expo en parallele.
3. Brancher d'abord chat + note viewer.
4. Ajouter insights + dashboard.
5. Ajouter graphe en second temps.

## 26. Decoupage en lots

### Lot 1 — Fondation backend API

- health,
- auth simple,
- conversations,
- chat stream,
- notes detail,
- status systeme.

### Lot 2 — Frontend MVP

- onboarding serveur,
- dashboard,
- liste conversations,
- ecran chat,
- note viewer,
- settings.

### Lot 3 — Knowledge surfaces

- insights,
- conversations sauvegardees,
- sources enrichies,
- entites.

### Lot 4 — Graphe

- graph API,
- vue graphe mobile/web,
- sous-graphes centres.

### Lot 5 — Durcissement

- offline read cache,
- telemetry,
- accessibilite,
- optimisation streaming,
- QA multi-plateforme.

## 27. Critères d'acceptation par domaine

### 27.1 Chat

- un prompt envoie un message utilisateur visible immediatement,
- la reponse assistant streamée apparait sans effacer les precedentes,
- la conversation reouvre apres relance de l'app,
- les sources s'affichent correctement,
- la note principale est visible quand fournie.

### 27.2 Notes

- une note s'ouvre depuis une source,
- le markdown s'affiche correctement,
- les wikilinks internes sont navigables,
- les retroliens sont visibles.

### 27.3 Dashboard

- l'etat backend est visible,
- l'indexation est visible,
- l'etat du modele est visible,
- les alertes critiques remontent.

### 27.4 Insights

- la liste charge,
- les filtres marchent,
- un artefact detail s'ouvre,
- la provenance est visible.

### 27.5 Graphe

- le graphe charge sur web et mobile,
- les filtres marchent,
- l'ouverture d'une note depuis un noeud marche.

## 28. Tests a prevoir dans le nouveau projet

### 28.1 Unitaires frontend

- formatting messages,
- mapping DTO -> view models,
- persistance brouillon,
- reducers / stores.

### 28.2 Integration frontend

- navigation,
- chat streaming,
- rehydratation conversation,
- ouverture note depuis source.

### 28.3 Contract tests backend/frontend

- health,
- conversations,
- chat stream,
- notes,
- graph,
- insights.

### 28.4 E2E

- connexion backend,
- creation conversation,
- envoi prompt,
- reception reponse,
- reprise apres redemarrage app,
- navigation vers une note.

## 29. Questions ouvertes a trancher rapidement

1. Auth simple locale ou vrai multi-user ?
2. Cible principale : mobile only ou mobile + web prioritaire ?
3. Graphe natif React Native ou WebView pour la V1 ?
4. Conversation persistee uniquement backend ou aussi snapshot client hors ligne ?
5. Faut-il conserver toutes les surfaces d'administration dans Expo ou garder un panneau desktop separe ?

## 30. Recommandation finale

Ne pas tenter une reécriture totale simultanee frontend + moteur RAG.

La trajectoire la plus solide est :

1. figer les contrats backend autour du coeur Python existant,
2. construire un frontend Expo propre et typé contre ces contrats,
3. migrer les ecrans par valeur metier en commencant par chat, notes et dashboard.

## 31. Prompt d'import pour un nouveau projet

Le texte ci-dessous peut etre reutilise comme brief initial dans un nouveau projet :

```text
Construire une application ObsiRAG en Expo Router + React Native + TypeScript strict.
L'application est un client mobile/web pour un backend ObsiRAG existant expose via API HTTP/SSE.

Priorites MVP :
1. configuration de l'URL backend et healthcheck
2. dashboard systeme
3. liste des conversations
4. ecran de chat avec streaming, sources, note principale, persistance du brouillon
5. visualiseur de note markdown avec wikilinks et retroliens
6. settings

Contraintes produit :
- mobile-first
- aucun secret dans le frontend
- conversation jamais perdue au rerender ou au redemarrage
- typage strict des DTO
- usage de TanStack Query pour les donnees serveur
- usage d'un store local leger pour preferences et brouillons
- architecture par features

Respecter la specification fonctionnelle et technique du document react-expo-specification.md.
```
