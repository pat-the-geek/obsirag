"""
Constructeur du graphe de connaissances (le "Cerveau").

Trois types d'arêtes :
  - Structurelles : [[wikilinks]] entre notes
  - Tags partagés : notes ayant ≥2 tags significatifs en commun
  - Entités NER partagées : notes mentionnant les mêmes personnes / orgs / lieux

Exportation :
  - HTML interactif (Pyvis) pour l'affichage dans Streamlit
  - JSON (NetworkX node-link) sauvegardé dans obsirag/data/graph/
"""
from __future__ import annotations

import json
import os
import re
import threading
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
from loguru import logger
from pyvis.network import Network

from src.config import settings
from src.storage.safe_read import read_text_file


from src.ui.note_badges import get_note_graph_color, get_note_type_meta


_pyvis_lock = threading.Lock()

# Tags exclus des arêtes de co-tagging : préfixes NER, nombres purs, dates, codes courts
_NER_TAG_PREFIX_RE = re.compile(
    r"^(personne|person|lieu|org|produit|groupe|concept|oeuvre|evenement|event|entity)/", re.I
)
_GARBAGE_TAG_RE = re.compile(
    r"^("
    r"\d[\w\-/]*"                                           # chiffre en tête
    r"|\d{4}(-\d{2}(-\d{2})?)?"                            # dates ISO
    r"|[A-Z0-9/\-]{2,8}"                                   # sigle tout-caps
    r"|\w{1,2}"                                             # 1-2 chars
    r"|(?:de|du|des|en|le|la|les|au|aux|un|une|par|sur|sous|dans|vers|et|ou|avec)-\S+"  # fragment prépositionnel
    r"|[^/]{31,}"                                           # > 30 chars
    r"|(?:\w+-){3,}\w+"                                     # 4+ mots tiretés
    r")$",
    re.I,
)
# Tags apparaissant dans trop de notes sont trop génériques pour créer des arêtes significatives
_TAG_MAX_NOTE_FREQ = 20
# Minimum de tags partagés pour créer une arête entre deux notes
_MIN_SHARED_TAGS = 2
# Entités NER : connexions significatives seulement (2-5 notes, pas trop génériques)
_NER_MAX_NOTE_FREQ = 5
# Plafond global d'arêtes tag+NER pour garder le graphe renderable
_MAX_DERIVED_EDGES = 500


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

    def build(
        self,
        notes: list[dict],
        entity_index: dict[str, list[str]] | None = None,
    ) -> nx.DiGraph:
        """Construit le graphe à partir des métadonnées vectorielles.

        entity_index: {entity_name → [file_path, ...]} pour les arêtes NER.
        Si None, les arêtes NER sont ignorées.
        """
        logger.info(f"Construction du graphe ({len(notes)} notes)…")
        g = nx.DiGraph()

        # 1. Ajouter les nœuds
        for note in notes:
            fp = note["file_path"]
            folder = str(Path(fp).parent)
            title = note.get("title") or Path(fp).stem
            type_meta = get_note_type_meta(fp)
            g.add_node(
                fp,
                label=title,
                title=self._node_tooltip(note),
                date_modified=note.get("date_modified", ""),
                tags=note.get("tags", []),
                folder=folder,
                note_type=type_meta["key"],
                note_type_label=type_meta["label"],
                color=get_note_graph_color(fp),
                size=15,
            )

        title_lookup = {
            (n.get("title") or Path(n["file_path"]).stem).lower(): n["file_path"]
            for n in notes
        }
        # Fallback : résolution par stem (nom de fichier sans extension)
        # Obsidian résout [[NomFichier]] par stem — le titre dans les métadonnées peut différer.
        stem_lookup = {
            Path(n["file_path"]).stem.lower(): n["file_path"]
            for n in notes
        }

        # 2. Arêtes structurelles (wikilinks [[note]])
        wikilink_count = 0
        for note in notes:
            for link in note.get("wikilinks", []):
                target_fp = self._resolve_link(link, title_lookup, stem_lookup)
                if target_fp and target_fp in g.nodes and target_fp != note["file_path"]:
                    if not g.has_edge(note["file_path"], target_fp):
                        g.add_edge(note["file_path"], target_fp, edge_type="wikilink", weight=2)
                        wikilink_count += 1

        # 3. Arêtes par tags partagés (≥2 tags significatifs en commun)
        tag_count = self._add_shared_tag_edges(g, notes, budget=_MAX_DERIVED_EDGES)

        # 4. Arêtes par co-occurrence d'entités NER validées
        ner_count = 0
        if entity_index:
            remaining = max(0, _MAX_DERIVED_EDGES - tag_count)
            ner_count = self._add_ner_edges(g, entity_index, budget=remaining)

        # Ajuster la taille des nœuds selon leur degré
        for node in g.nodes():
            degree = g.in_degree(node) + g.out_degree(node)
            g.nodes[node]["size"] = max(10, min(40, 10 + degree * 2))

        self._graph = g
        self._last_build = datetime.now(timezone.utc)
        self._save_json(g)
        logger.info(
            f"Graphe construit : {g.number_of_nodes()} nœuds, "
            f"{g.number_of_edges()} arêtes "
            f"(wikilinks={wikilink_count}, tags={tag_count}, ner={ner_count})"
        )
        return g

    @staticmethod
    def _is_garbage_tag(tag: str) -> bool:
        return bool(_NER_TAG_PREFIX_RE.match(tag) or _GARBAGE_TAG_RE.match(tag))

    def _add_shared_tag_edges(self, g: nx.DiGraph, notes: list[dict], budget: int = 500) -> int:
        """Ajoute des arêtes entre notes partageant ≥2 tags significatifs (plafonné à budget)."""
        tag_to_fps: dict[str, set[str]] = defaultdict(set)
        for note in notes:
            fp = note["file_path"]
            if fp not in g.nodes:
                continue
            for tag in note.get("tags", []):
                if not self._is_garbage_tag(tag):
                    tag_to_fps[tag].add(fp)

        pair_count: dict[tuple[str, str], int] = defaultdict(int)
        for tag, fps in tag_to_fps.items():
            fps_list = sorted(fps)
            if len(fps_list) > _TAG_MAX_NOTE_FREQ:
                continue
            for i, fp_a in enumerate(fps_list):
                for fp_b in fps_list[i + 1:]:
                    pair_count[(fp_a, fp_b)] += 1

        # Trier par nombre de tags partagés (les plus forts d'abord)
        sorted_pairs = sorted(pair_count.items(), key=lambda x: x[1], reverse=True)
        added = 0
        for (fp_a, fp_b), count in sorted_pairs:
            if added >= budget:
                break
            if count >= _MIN_SHARED_TAGS and not g.has_edge(fp_a, fp_b) and not g.has_edge(fp_b, fp_a):
                g.add_edge(fp_a, fp_b, edge_type="shared_tag", weight=count)
                added += 1
        return added

    def _add_ner_edges(self, g: nx.DiGraph, entity_index: dict[str, list[str]], budget: int = 300) -> int:
        """Ajoute des arêtes entre notes co-mentionnant la même entité NER (plafonné à budget)."""
        added = 0
        for entity_name, fps in entity_index.items():
            if added >= budget:
                break
            valid_fps = [fp for fp in fps if fp in g.nodes]
            if len(valid_fps) < 2 or len(valid_fps) > _NER_MAX_NOTE_FREQ:
                continue
            for i, fp_a in enumerate(valid_fps):
                for fp_b in valid_fps[i + 1:]:
                    if added >= budget:
                        break
                    if not g.has_edge(fp_a, fp_b) and not g.has_edge(fp_b, fp_a):
                        g.add_edge(fp_a, fp_b, edge_type="ner_entity", weight=1)
                        added += 1
        return added

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

        html = read_text_file(tmp, default="")

        # Surcharge CSS des boutons de navigation pyvis + fix canvas HiDPI
        nav_css = """
<style>
html, body {
    width: 100%;
    max-width: 100%;
    overflow: hidden;
    margin: 0;
    padding: 0;
    -webkit-text-size-adjust: 100%;
}
body {
    touch-action: manipulation;
}
@media (max-width: 768px) {
    div.vis-network div.vis-navigation {
        display: none !important;
    }
}
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
    var isMobile = window.matchMedia('(max-width: 768px)').matches;

    if (isMobile) {
        network.setOptions({
            interaction: {
                navigationButtons: false,
                keyboard: false,
                multiselect: false
            },
            physics: {
                stabilization: { fit: true }
            }
        });
    }

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
    network.once('stabilizationIterationsDone', function() {
        try {
            network.fit({ animation: isMobile ? false : { duration: 250, easingFunction: 'easeInOutQuad' } });
        } catch (e) {
            network.fit();
        }
    });
})();
</script>
"""
        fixes = fixes.replace("__VAULT_NAME__", vault_name_js)
        viewport = '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        return html.replace("</head>", viewport + nav_css + "</head>", 1).replace("</body>", fixes + "</body>", 1)

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
        type_meta = get_note_type_meta(note.get("file_path", ""))
        return (
            f"<b>{title}</b><br>"
            f"{type_meta['icon']} {type_meta['label']}<br>"
            f"📅 {date}<br>"
            f"{'🏷 ' + tags + '<br>' if tags else ''}"
            f'<div style="margin-top:8px;display:flex;gap:6px;">'
            f'<button class="obsirag-open-note" data-fp="{fp}">📖 Lire la note</button>'
            f'<button class="obsirag-open-obsidian" data-fp="{fp}">🟣 Obsidian</button>'
            f'</div>'
        )

    @staticmethod
    def _resolve_link(
        link: str,
        title_lookup: dict[str, str],
        stem_lookup: dict[str, str] | None = None,
    ) -> str | None:
        key = link.lower().strip()
        return title_lookup.get(key) or (stem_lookup.get(key) if stem_lookup else None)

    def _save_json(self, graph: nx.DiGraph) -> None:
        try:
            data = nx.node_link_data(graph)
            out = settings.graph_dir / "knowledge_graph.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(data, default=str, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Sauvegarde du graphe JSON échouée : {exc}")
