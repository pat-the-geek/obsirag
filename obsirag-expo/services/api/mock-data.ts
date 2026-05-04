import {
  ChatMessage,
  ConversationDetail,
  ConversationSummary,
  GraphData,
  InsightItem,
  NoteDetail,
  SystemStatus,
} from '../../types/domain';

const now = new Date().toISOString();

const messages: ChatMessage[] = [
  {
    id: 'msg-1',
    role: 'user',
    content: 'Parle moi de Artemis II.',
    createdAt: now,
  },
  {
    id: 'msg-2',
    role: 'assistant',
    content:
      '### Apercu de Artemis II\n\nArtemis II est la premiere mission habitee du programme Artemis.\n\n### Details utiles\n\n- La mission valide les systemes du vol habite\n- Elle prepare les etapes suivantes vers la Lune',
    createdAt: now,
    provenance: 'vault',
    primarySource: {
      filePath: 'Space/Artemis II.md',
      noteTitle: 'Artemis II',
      isPrimary: true,
    },
    sources: [
      {
        filePath: 'Space/Artemis II.md',
        noteTitle: 'Artemis II',
        isPrimary: true,
        score: 0.96,
      },
    ],
    timeline: ['Analyse de la requete', 'Recherche dans le coffre', 'Génération locale'],
    stats: {
      tokens: 196,
      ttft: 0.9,
      total: 4.8,
      tps: 40.8,
    },
  },
];

export const mockConversations: ConversationDetail[] = [
  {
    id: 'conv-1',
    title: 'Mission Artemis II',
    updatedAt: now,
    draft: '',
    messages,
    lastGenerationStats: {
      tokens: 196,
      ttft: 0.9,
      total: 4.8,
      tps: 40.8,
    },
  },
  {
    id: 'conv-2',
    title: 'Finance comportementale',
    updatedAt: now,
    draft: 'Quels biais cognitifs reviennent le plus ?',
    messages: [],
  },
];

export const mockConversationSummaries: ConversationSummary[] = mockConversations.map((item) => ({
  id: item.id,
  title: item.title,
  preview: item.messages[item.messages.length - 1]?.content ?? 'Fil vide',
  updatedAt: item.updatedAt,
  turnCount: item.messages.filter((message) => message.role === 'user').length,
  messageCount: item.messages.length,
}));

export const mockSystemStatus: SystemStatus = {
  backendReachable: true,
  llmAvailable: true,
  notesIndexed: 736,
  chunksIndexed: 4812,
  runtime: {
    llmProvider: 'Local',
    llmModel: 'qwen2.5:7b',
    embeddingModel: 'paraphrase-multilingual-MiniLM-L12-v2',
    vectorStore: 'LanceDB',
    nerModel: 'xx_ent_wiki_sm',
    autolearnMode: 'worker',
    euriaProvider: 'Infomaniak',
    euriaModel: 'openai/gpt-oss-120b',
    euriaEnabled: true,
  },
  startup: {
    ready: true,
    currentStep: 'Tous les services sont opérationnels',
    steps: [
      '📁 Initialisation des répertoires de données…',
      "🗄️ Chargement du store vecteurs et du modèle d'embedding (peut prendre 30 s)…",
      '🤖 Initialisation du client Ollama…',
      '🔗 Initialisation du pipeline RAG…',
      "🗂️ Initialisation du pipeline d'indexation…",
      '🧠 Initialisation du graphe de connaissances…',
      "📚 Initialisation de l'auto-learner…",
      '👁️ Démarrage du watcher de coffre…',
      '🚀 Lancement des services en arrière-plan…',
      '✅ Tous les services sont opérationnels',
    ],
    updatedAt: new Date().toISOString(),
  },
  indexing: {
    running: false,
    processed: 736,
    total: 736,
    current: 'Indexation terminee',
  },
  autolearn: {
    active: false,
    managedBy: 'worker',
    running: true,
    pid: 4821,
    step: 'En attente',
    log: [
      '2026-04-17 08:42:11 Cycle demarre',
      '2026-04-17 08:42:15 Scan des notes candidates termine',
      '2026-04-17 08:42:19 3 entites enrichies depuis le cache',
      '2026-04-17 08:42:27 1 synapse detectee et ecrite dans le vault',
      '2026-04-17 08:42:31 Cycle termine sans erreur',
    ],
    startedAt: new Date(Date.now() - 1000 * 60 * 18).toISOString(),
    updatedAt: new Date().toISOString(),
    nextRunAt: new Date(Date.now() + 1000 * 60 * 45).toISOString(),
  },
  alerts: [
    {
      id: 'alert-1',
      level: 'info',
      title: 'Mode mock actif',
      description: 'Le frontend fonctionne actuellement avec des donnees de demonstration.',
    },
  ],
};

export const mockNotes: NoteDetail[] = [
  {
    id: 'note-1',
    filePath: 'Space/Artemis II.md',
    title: 'Artemis II',
    bodyMarkdown:
      '# Artemis II\n\nMission habitee de validation du programme Artemis.\n\n## Objectifs\n\n- valider Orion\n- qualifier la mission lunaire\n\nVoir aussi [[Space/Artemis Program.md|Artemis Program]].',
    tags: ['space', 'nasa', 'mission'],
    frontmatter: {
      type: 'user-note',
      status: 'active',
    },
    backlinks: [
      {
        title: 'Artemis Program',
        filePath: 'Space/Artemis Program.md',
      },
    ],
    links: [
      {
        title: 'Artemis Program',
        filePath: 'Space/Artemis Program.md',
      },
    ],
    dateModified: now,
    noteType: 'user-note',
  },
  {
    id: 'obsirag/insights/2026-04/web_artemis_ii.md',
    filePath: 'obsirag/insights/2026-04/web_artemis_ii.md',
    title: 'Artemis II et validation mission',
    bodyMarkdown:
      '# Artemis II et validation mission\n\n> [!info] Rapport insight mock charge depuis le viewer Expo.\n\n## Contexte\n\nLa mission Artemis II sert de base de demonstration pour les artefacts markdown du module chat.\n\n## Synthese\n\nCe document montre comment un rapport genere peut etre relu directement dans le viewer.',
    tags: ['insight', 'space', 'obsirag', 'rapport'],
    frontmatter: {
      type: 'rapport',
      statut: 'finalise',
    },
    backlinks: [],
    links: [
      {
        title: 'Artemis II',
        filePath: 'Space/Artemis II.md',
      },
    ],
    dateModified: now,
    noteType: 'insight',
  },
];

export const mockInsights: InsightItem[] = [
  {
    id: 'ins-1',
    title: 'Artemis II et validation mission',
    filePath: 'obsirag/insights/2026-04/web_artemis_ii.md',
    kind: 'insight',
    provenance: 'hybrid',
    tags: ['insight', 'space', 'obsirag'],
    dateModified: now,
    excerpt: 'Synthese des objectifs et de la logique de validation de la mission.',
  },
  {
    id: 'syn-1',
    title: 'Lien entre biais et decisions',
    filePath: 'obsirag/synapses/2026-04/biais-decisions.md',
    kind: 'synapse',
    provenance: 'vault',
    tags: ['synapse', 'finance'],
    dateModified: now,
    excerpt: 'Connexion implicite detectee entre deux notes du coffre.',
  },
];

export const mockGraphData: GraphData = {
  nodes: [
    { id: 'note-1', label: 'Artemis II', group: 'Space', degree: 4, tags: ['mission', 'nasa'], noteType: 'user', dateModified: '2026-04-16T09:00:00Z' },
    { id: 'note-2', label: 'Artemis Program', group: 'Space', degree: 7, tags: ['program', 'nasa'], noteType: 'insight', dateModified: '2026-04-15T09:00:00Z' },
    { id: 'note-3', label: 'Apollo Legacy', group: 'History', degree: 2, tags: ['archive'], noteType: 'report', dateModified: '2026-03-20T09:00:00Z' },
  ],
  edges: [
    { id: 'edge-1', source: 'note-1', target: 'note-2' },
    { id: 'edge-2', source: 'note-2', target: 'note-3' },
  ],
  metrics: {
    nodeCount: 3,
    edgeCount: 2,
    density: 0.67,
    filteredNoteCount: 3,
    totalNoteCount: 3,
  },
  topNodes: [
    { id: 'note-2', label: 'Artemis Program', degree: 7 },
    { id: 'note-1', label: 'Artemis II', degree: 4 },
  ],
  filterOptions: {
    folders: ['History', 'Space'],
    tags: ['archive', 'mission', 'nasa', 'program'],
    types: ['user', 'report', 'insight', 'synapse'],
  },
  noteOptions: [
    { title: 'Apollo Legacy', filePath: 'note-3', dateModified: '2026-03-20T09:00:00Z', noteType: 'report' },
    { title: 'Artemis II', filePath: 'note-1', dateModified: '2026-04-16T09:00:00Z', noteType: 'user' },
    { title: 'Artemis Program', filePath: 'note-2', dateModified: '2026-04-15T09:00:00Z', noteType: 'insight' },
  ],
  spotlight: [
    { filePath: 'note-2', title: 'Artemis Program', score: 1, dateModified: '2026-04-15', tags: ['program', 'nasa'], noteType: 'insight' },
    { filePath: 'note-1', title: 'Artemis II', score: 0.5, dateModified: '2026-04-16', tags: ['mission', 'nasa'], noteType: 'user' },
  ],
  recentNotes: [
    { title: 'Artemis II', filePath: 'note-1', dateModified: '2026-04-16T09:00:00Z', noteType: 'user' },
    { title: 'Artemis Program', filePath: 'note-2', dateModified: '2026-04-15T09:00:00Z', noteType: 'insight' },
  ],
  folderSummary: [
    { label: 'Space', count: 2 },
    { label: 'History', count: 1 },
  ],
  tagSummary: [
    { label: 'nasa', count: 2 },
    { label: 'archive', count: 1 },
  ],
  typeSummary: [
    { label: 'user', count: 1 },
    { label: 'report', count: 1 },
    { label: 'insight', count: 1 },
  ],
  legend: [
    { key: 'user', label: 'Note', color: '#60a5fa' },
    { key: 'report', label: 'Rapport', color: '#f59e0b' },
    { key: 'insight', label: 'Insight', color: '#facc15' },
    { key: 'synapse', label: 'Synapse', color: '#c084fc' },
  ],
};
