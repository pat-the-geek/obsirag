# ObsiRAG — Design System

## Sources de vérité

| Fichier | Portée |
|---------|--------|
| `shared/brand-tokens.json` | Couleurs de marque communes (Streamlit + Expo) |
| `shared/note-type-colors.json` | Couleurs des types de notes (Streamlit + Expo) |

**Règle permanente :** toute valeur hex codée en dur dans un composant JSX/TSX ou dans `theme.py` en dehors de ces deux fichiers est une anomalie à corriger.

---

## Palette de marque

| Token | Valeur | Usage |
|-------|--------|-------|
| `brand-bg` | `#f6f2ea` | Fond principal (warm parchment) |
| `brand-surface` | `#fffdf9` | Surfaces élevées, cartes |
| `brand-accent` | `#a55233` | Couleur primaire / CTA |
| `brand-accent-alt` | `#5a8fc2` | Liens, accents secondaires |
| `brand-text` | `#1f160c` | Texte principal |
| `brand-text-muted` | `#5b4b37` | Texte secondaire, légendes |
| `brand-border` | `#d7cbb8` | Bordures, séparateurs |
| `brand-success` | `#3fb950` | Succès, états positifs |
| `brand-danger` | `#cd3131` | Erreurs, états critiques |
| `brand-warning` | `#8b4d00` | Avertissements |

Le mode sombre dérive les mêmes teintes vers leurs équivalents warm-dark (`bg: #0f0d0a`, `accent: #c97a52` éclairci, etc.).

---

## Types de notes et couleurs

Source : `shared/note-type-colors.json`

| Type | Fill (graphe) | Badge bg | Badge text | Sémantique |
|------|--------------|----------|------------|------------|
| `user` | `#60a5fa` (bleu) | `rgba(0,102,184,0.12)` | `#0066b8` | Note utilisateur du coffre |
| `report` | `#f59e0b` (ambre) | `rgba(180,83,9,0.12)` | `#b45309` | Synthèse / rapport généré |
| `insight` | `#facc15` (jaune) | `rgba(202,138,4,0.12)` | `#a16207` | Insight auto-généré |
| `synapse` | `#c084fc` (violet) | `rgba(147,51,234,0.12)` | `#7e22ce` | Lien implicite entre notes |
| `entity` | `#34d399` (vert) | `rgba(5,150,105,0.12)` | `#047857` | Entité nommée extraite |

---

## Règle violet = Obsidian

Le violet (`#c084fc` / `#7e22ce` et variantes) est **réservé** dans ce projet aux éléments liés à Obsidian :

- Type **Synapse** (lien implicite entre notes, concept natif Obsidian)
- Bouton / lien "Ouvrir dans Obsidian"
- Nœuds synapse dans le graphe de connaissances

Ne pas utiliser le violet pour d'autres éléments UI.

---

## Convention de nommage des tokens

### Streamlit (`theme.py`)

```python
# Clés du dict palette (snake_case)
bg, bg2, bg3          # fonds du plus sombre au plus clair
text, text_dim        # texte principal et atténué
accent, accent_dim    # couleur primaire et son survol/focus
border                # bordures
ok, err, warn         # états sémantiques
```

### Expo (`app-theme.ts`)

```ts
// camelCase, nommage sémantique — jamais de valeur hex directe dans un composant
background, surface, surfaceMuted          // fonds
text, textMuted, textSubtle               // texte
primary, primaryMuted, primaryText        // couleur primaire
border                                    // bordures
tagBackground, tagPillText                // pilule de tag (bleu, filtre)
tagSurface, tagText                       // tag inline dans markdown (warm)
successText, danger, warningText          // états sémantiques
```

**Règle :** le nom d'un token est **sémantique** (rôle) — jamais visuel (`bluish`, `warmRed`). Trois tokens similaires valent mieux qu'un token générique mal nommé.

---

## Bibliothèque d'icônes

- **Expo** : `lucide-react-native` (SVG, pas de font à précharger)
- Les noms d'icônes Feather et Lucide sont identiques, en PascalCase dans Lucide (`share-2` → `Share2`)
