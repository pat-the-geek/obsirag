"""
Constructeur du graphe de connaissances (le "Cerveau").

Deux types d'arêtes :
  - Structurelles : [[wikilinks]] entre notes
  - Entités NER partagées : notes mentionnant les mêmes personnes / orgs / lieux

Exportation :
  - HTML interactif (Pyvis) pour l'affichage dans Streamlit
  - JSON (NetworkX node-link) sauvegardé dans obsirag/data/graph/
"""
from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
from loguru import logger
from pyvis.network import Network

from src.config import settings


# Palette : couleurs vives sur fond sombre, assez distinctes pour être lisibles
# Format : (background, border, font)
_FOLDER_PALETTE = [
    {"background": "#A78BFA", "border": "#7C3AED", "highlight": {"background": "#C4B5FD", "border": "#5B21B6"}},
    {"background": "#60A5FA", "border": "#2563EB", "highlight": {"background": "#93C5FD", "border": "#1D4ED8"}},
    {"background": "#34D399", "border": "#059669", "highlight": {"background": "#6EE7B7", "border": "#047857"}},
    {"background": "#FBBF24", "border": "#D97706", "highlight": {"background": "#FCD34D", "border": "#B45309"}},
    {"background": "#F87171", "border": "#DC2626", "highlight": {"background": "#FCA5A5", "border": "#B91C1C"}},
    {"background": "#38BDF8", "border": "#0891B2", "highlight": {"background": "#7DD3FC", "border": "#0E7490"}},
    {"background": "#F472B6", "border": "#BE185D", "highlight": {"background": "#F9A8D4", "border": "#9D174D"}},
    {"background": "#A3E635", "border": "#65A30D", "highlight": {"background": "#BEF264", "border": "#4D7C0F"}},
]


_pyvis_lock = threading.Lock()


@contextmanager
def _tmp_workdir(path: str):
    """Change temporairement de répertoire courant (pyvis exige un CWD accessible en écriture)."""
    orig = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(orig)


class GraphBuilder:
    def __init__(self) -> None:
        self._graph: nx.DiGraph | None = None
        self._last_build: datetime | None = None

    # ---- API publique ----

    def build(self, notes: list[dict]) -> nx.DiGraph:
        """Construit le graphe à partir des métadonnées ChromaDB."""
        logger.info(f"Construction du graphe ({len(notes)} notes)…")
        g = nx.DiGraph()

        # 1. Ajouter les nœuds
        folder_index: dict[str, int] = {}
        for note in notes:
            fp = note["file_path"]
            folder = str(Path(fp).parent)
            if folder not in folder_index:
                folder_index[folder] = len(folder_index)

            palette = _FOLDER_PALETTE[folder_index[folder] % len(_FOLDER_PALETTE)]
            title = note.get("title") or Path(fp).stem
            g.add_node(
                fp,
                label=title,
                title=self._node_tooltip(note),
                date_modified=note.get("date_modified", ""),
                tags=note.get("tags", []),
                folder=folder,
                color=palette,
                size=15,
            )

        note_lookup = {n["file_path"]: n for n in notes}
        title_lookup = {
            (n.get("title") or Path(n["file_path"]).stem).lower(): n["file_path"]
            for n in notes
        }

        # 2. Arêtes structurelles (wikilinks)
        for note in notes:
            for link in note.get("wikilinks", []):
                target_fp = self._resolve_link(link, title_lookup)
                if target_fp and target_fp in g.nodes:
                    if not g.has_edge(note["file_path"], target_fp):
                        g.add_edge(note["file_path"], target_fp, edge_type="wikilink", weight=1)

        # 3. Arêtes sémantiques (entités NER partagées)
        entity_map: dict[str, list[str]] = {}
        for note in notes:
            note_fp = note["file_path"]
            # Ici on pourrait utiliser les métadonnées NER stockées dans chroma
            # Pour l'instant on se base sur les wikilinks uniquement
            # (les entités NER seront exploitées dans une prochaine itération)

        # Augmenter la taille des nœuds selon leur degré
        for node in g.nodes():
            degree = g.in_degree(node) + g.out_degree(node)
            g.nodes[node]["size"] = max(10, min(40, 10 + degree * 2))

        self._graph = g
        self._last_build = datetime.now(timezone.utc)
        self._save_json(g)
        logger.info(
            f"Graphe construit : {g.number_of_nodes()} nœuds, "
            f"{g.number_of_edges()} arêtes"
        )
        return g

    def to_pyvis_html(self, graph: nx.DiGraph, height: int = 700, obsidian_vault: str = "") -> str:
        """Génère l'HTML interactif Pyvis."""
        net = Network(
            height=f"{height}px",
            width="100%",
            bgcolor="#0F0F1A",
            font_color="#E2E8F0",
            directed=True,
            notebook=False,
        )

        # Physique : Barnes-Hut pour grands graphes, repulsion pour lisibilité
        net.set_options("""{
            "physics": {
                "barnesHut": {
                    "gravitationalConstant": -8000,
                    "centralGravity": 0.3,
                    "springLength": 150,
                    "springConstant": 0.04,
                    "damping": 0.2,
                    "avoidOverlap": 0.8
                },
                "maxVelocity": 50,
                "minVelocity": 0.75,
                "stabilization": {"iterations": 200, "fit": true}
            },
            "edges": {
                "color": {"color": "#888888", "highlight": "#FFFFFF", "hover": "#FFFFFF"},
                "smooth": {"type": "continuous"},
                "arrows": {"to": {"enabled": true, "scaleFactor": 0.5}},
                "width": 1.5
            },
            "nodes": {
                "font": {"size": 13, "color": "#FFFFFF", "strokeWidth": 0},
                "borderWidth": 2,
                "borderWidthSelected": 4,
                "shadow": {"enabled": true, "color": "rgba(0,0,0,0.5)", "size": 8}
            },
            "interaction": {
                "hover": true,
                "tooltipDelay": 80,
                "navigationButtons": true,
                "keyboard": true,
                "multiselect": true
            }
        }""")

        for node_id, data in graph.nodes(data=True):
            net.add_node(
                node_id,
                label=data.get("label", node_id)[:40],
                title=data.get("title", ""),
                color=data.get("color", "#7C3AED"),
                size=data.get("size", 15),
            )

        for src, dst, data in graph.edges(data=True):
            color = "#7C3AED" if data.get("edge_type") == "wikilink" else "#059669"
            net.add_edge(src, dst, color=color)

        # Pyvis appelle os.makedirs("lib") relatif au CWD — on force le CWD sur /tmp
        tmp = Path("/tmp/brain_graph.html")
        with _pyvis_lock:
            with _tmp_workdir("/tmp"):
                net.write_html(str(tmp), local=False)

        html = tmp.read_text(encoding="utf-8")

        # Surcharge CSS des boutons de navigation pyvis + fix canvas HiDPI
        nav_css = """
<style>
div.vis-network div.vis-navigation div.vis-button {
    background-color: rgba(255,255,255,0.15) !important;
    border-radius: 4px !important;
    filter: invert(1) !important;
    opacity: 0.8 !important;
}
div.vis-network div.vis-navigation div.vis-button:hover {
    background-color: rgba(255,255,255,0.3) !important;
    opacity: 1 !important;
}
#obsirag-tooltip {
    position: fixed;
    z-index: 9999;
    background: #1E1E2E;
    color: #E2E8F0;
    border: 1px solid #7C3AED;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 13px;
    line-height: 1.6;
    max-width: 300px;
    white-space: normal;
    word-wrap: break-word;
    display: none;
    pointer-events: auto;
    box-shadow: 0 4px 16px rgba(0,0,0,0.5);
}
#obsirag-tooltip .obsirag-open-note,
#obsirag-tooltip .obsirag-open-obsidian {
    padding: 4px 10px;
    font-size: 12px;
    color: #fff;
    border: none;
    border-radius: 4px;
    cursor: pointer;
}
#obsirag-tooltip .obsirag-open-note { background: #7C3AED; }
#obsirag-tooltip .obsirag-open-note:hover { background: #6D28D9; }
#obsirag-tooltip .obsirag-open-obsidian { background: #4B2A7A; }
#obsirag-tooltip .obsirag-open-obsidian:hover { background: #3A1F5F; }
</style>
"""
        import json as _json
        vault_name_js = _json.dumps(obsidian_vault or settings.obsidian_vault)
        fixes = r"""
<script>
(function waitForNetwork() {
    if (typeof network === 'undefined') { setTimeout(waitForNetwork, 100); return; }

    // -- Tooltip custom persistant --
    // Construire un dictionnaire nodeId → HTML décodé
    var nodesData = network.body.data.nodes;
    var nodeTooltips = {};
    nodesData.forEach(function(node) {
        if (node.title && typeof node.title === 'string') {
            var ta = document.createElement('textarea');
            ta.innerHTML = node.title;
            nodeTooltips[node.id] = ta.value;
        }
    });

    // Supprimer les tooltips natifs de vis.js (ils disparaissent dès que le curseur bouge)
    var clears = Object.keys(nodeTooltips).map(function(id) {
        return { id: id, title: ' ' };
    });
    if (clears.length) nodesData.update(clears);

    // Créer le div tooltip HTML custom
    var tip = document.createElement('div');
    tip.id = 'obsirag-tooltip';
    document.body.appendChild(tip);

    var hideTimer = null;
    function startHide() {
        hideTimer = setTimeout(function() { tip.style.display = 'none'; }, 250);
    }
    tip.addEventListener('mouseenter', function() { clearTimeout(hideTimer); });
    tip.addEventListener('mouseleave', startHide);

    var OBSIDIAN_VAULT = __VAULT_NAME__;

    function openNote(fp) {
        // Écrit dans localStorage (partagé entre iframes same-origin)
        // Le composant bridge lit cette valeur et déclenche le rerun Python via Streamlit
        try {
            localStorage.setItem('obsirag_open_note', fp);
        } catch(e) {
            // Fallback postMessage si localStorage indisponible
            window.parent.postMessage({ obsirag_open_note: fp }, '*');
        }
    }

    function openObsidian(fp) {
        var relPath = fp.replace(/^\/?(vault\/)?/, '').replace(/\.md$/i, '');
        var url = 'obsidian://open?vault=' + encodeURIComponent(OBSIDIAN_VAULT)
                + '&file=' + encodeURIComponent(relPath);
        // iframe invisible : lance Obsidian sans ouvrir d'onglet vide
        var fr = document.createElement('iframe');
        fr.style.display = 'none';
        fr.src = url;
        document.body.appendChild(fr);
        setTimeout(function() { document.body.removeChild(fr); }, 2000);
    }

    network.on('hoverNode', function(params) {
        var html = nodeTooltips[params.node];
        if (!html) return;
        clearTimeout(hideTimer);
        tip.innerHTML = html;
        var btn = tip.querySelector('.obsirag-open-note');
        if (btn) {
            btn.onclick = function(e) {
                e.stopPropagation();
                openNote(this.getAttribute('data-fp'));
            };
        }
        var btnObs = tip.querySelector('.obsirag-open-obsidian');
        if (btnObs) {
            btnObs.onclick = function(e) {
                e.stopPropagation();
                openObsidian(this.getAttribute('data-fp'));
            };
        }
        // Positionner près du curseur (événement DOM)
        var e = params.event;
        var ex = e.clientX || (e.touches && e.touches[0].clientX) || 0;
        var ey = e.clientY || (e.touches && e.touches[0].clientY) || 0;
        tip.style.display = 'block';
        // Ajustement si débordement viewport
        setTimeout(function() {
            var r = tip.getBoundingClientRect();
            tip.style.left = (ex + 16 + r.width > window.innerWidth ? ex - r.width - 16 : ex + 16) + 'px';
            tip.style.top  = (ey + r.height > window.innerHeight ? ey - r.height : ey) + 'px';
        }, 0);
    });
    network.on('blurNode', startHide);

    // -- Fix texte flou après zoom (redraw différé pour ne pas interrompre l'animation) --
    network.on('zoom', function() {
        setTimeout(function() { network.redraw(); }, 80);
    });
})();
</script>
"""
        fixes = fixes.replace("__VAULT_NAME__", vault_name_js)
        return html.replace("</head>", nav_css + "</head>", 1).replace("</body>", fixes + "</body>", 1)

    def get_stats(self, graph: nx.DiGraph) -> dict:
        if graph.number_of_nodes() == 0:
            return {}
        undirected = graph.to_undirected()
        centrality = nx.degree_centrality(undirected)
        top_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:10]
        return {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "top_connected": [
                {"file_path": fp, "score": round(score, 3)}
                for fp, score in top_nodes
            ],
            "density": round(nx.density(graph), 4),
        }

    # ---- helpers ----

    @staticmethod
    def _node_tooltip(note: dict) -> str:
        import html as _html
        tags = ", ".join(note.get("tags", [])[:5])
        date = note.get("date_modified", "")[:10]
        fp = _html.escape(note.get("file_path", ""), quote=True)
        title = _html.escape(note.get("title") or Path(fp).stem or "Note", quote=False)
        return (
            f"<b>{title}</b><br>"
            f"📅 {date}<br>"
            f"{'🏷 ' + tags + '<br>' if tags else ''}"
            f'<div style="margin-top:8px;display:flex;gap:6px;">'
            f'<button class="obsirag-open-note" data-fp="{fp}">📖 Lire la note</button>'
            f'<button class="obsirag-open-obsidian" data-fp="{fp}">🟣 Obsidian</button>'
            f'</div>'
        )

    @staticmethod
    def _resolve_link(link: str, title_lookup: dict[str, str]) -> str | None:
        return title_lookup.get(link.lower())

    def _save_json(self, graph: nx.DiGraph) -> None:
        try:
            data = nx.node_link_data(graph)
            out = settings.graph_dir / "knowledge_graph.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(data, default=str, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Sauvegarde du graphe JSON échouée : {exc}")
