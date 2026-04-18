import type { CSSProperties } from 'react';
import { useEffect, useMemo, useRef } from 'react';
import { useWindowDimensions } from 'react-native';
import { DataSet, Network } from 'vis-network/standalone';

import { GraphData } from '../../types/domain';

type KnowledgeGraphProps = {
  data: GraphData;
  focusedNodeId?: string;
  onSelectNode?: (nodeId: string) => void;
  onOpenNode?: (nodeId: string) => void;
  onDetectSynapses?: (nodeId: string) => void;
  zoom?: number;
  onZoomChange?: (zoom: number) => void;
  onZoomIn?: () => void;
  onZoomOut?: () => void;
  onZoomReset?: () => void;
};

type GraphNodeRecord = GraphData['nodes'][number] & {
  fullLabel: string;
  tooltipHtml: string;
  color: {
    background: string;
    border: string;
    highlight: {
      background: string;
      border: string;
    };
  };
  value: number;
  mass: number;
  font: {
    color: string;
    size: number;
    face: string;
  };
  labelHighlightBold: boolean;
  borderWidth?: number;
  shadow: {
    enabled: boolean;
    color: string;
    size: number;
    x: number;
    y: number;
  };
  title: string;
};

type GraphEdgeRecord = GraphData['edges'][number] & {
  from: string;
  to: string;
  color: {
    color: string;
    highlight: string;
    hover: string;
    inherit: false;
  };
  smooth: {
    type: 'continuous';
  };
  arrows: {
    to: {
      enabled: false;
      scaleFactor: 0;
    };
  };
  width: number;
  selectionWidth: number;
  hidden?: boolean;
};

const GROUP_COLORS = ['#2a5f95', '#c46a2f', '#4b7f52', '#875f9a', '#5a768d', '#9b4f46'];
const NOTE_TYPE_COLORS: Record<string, string> = {
  user: '#60a5fa',
  report: '#f59e0b',
  insight: '#facc15',
  synapse: '#c084fc',
};
const MIN_GRAPH_ZOOM = 0.2;
const MAX_GRAPH_ZOOM = 10;
const MIN_BASE_SCALE = 0.01;

export function KnowledgeGraph({ data, focusedNodeId, onSelectNode, onOpenNode, onDetectSynapses, zoom = 1, onZoomChange, onZoomIn, onZoomOut, onZoomReset }: KnowledgeGraphProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const networkRef = useRef<Network | null>(null);
  const zoomSyncTimerRef = useRef<number | null>(null);
  const redrawTimerRef = useRef<number | null>(null);
  const focusTimerRef = useRef<number | null>(null);
  const suppressZoomSyncRef = useRef(false);
  const fitScaleRef = useRef(1);
  const preferredScaleRef = useRef(clamp(zoom, MIN_GRAPH_ZOOM, MAX_GRAPH_ZOOM));
  const windowDimensions = useWindowDimensions();
  const scene = useMemo(() => buildGraphScene(data, windowDimensions.width), [data, windowDimensions.width]);
  const viewportHeight = scene.height;
  const preparedGraph = useMemo(() => buildPreparedGraph(data, focusedNodeId), [data, focusedNodeId]);

  useEffect(() => {
    preferredScaleRef.current = clamp(zoom, MIN_GRAPH_ZOOM, MAX_GRAPH_ZOOM);
  }, [zoom]);

  useEffect(() => {
    const network = networkRef.current;
    if (!network) {
      return undefined;
    }

    const targetScale = clamp(zoom, MIN_GRAPH_ZOOM, MAX_GRAPH_ZOOM);
    const baseScale = Math.max(fitScaleRef.current, MIN_BASE_SCALE);
    const absoluteTargetScale = clamp(baseScale * targetScale, MIN_BASE_SCALE, baseScale * MAX_GRAPH_ZOOM);
    const currentScale = Math.max(network.getScale(), MIN_BASE_SCALE);
    if (Math.abs(currentScale - absoluteTargetScale) < 0.01) {
      return undefined;
    }

    suppressZoomSyncRef.current = true;
    network.moveTo({
      position: network.getViewPosition(),
      scale: absoluteTargetScale,
      animation: {
        duration: 180,
        easingFunction: 'easeInOutQuad',
      },
    });

    if (zoomSyncTimerRef.current) {
      window.clearTimeout(zoomSyncTimerRef.current);
    }
    zoomSyncTimerRef.current = window.setTimeout(() => {
      suppressZoomSyncRef.current = false;
    }, 220);

    return () => {
      if (zoomSyncTimerRef.current) {
        window.clearTimeout(zoomSyncTimerRef.current);
        zoomSyncTimerRef.current = null;
      }
    };
  }, [zoom]);

  useEffect(() => {
    if (!containerRef.current) {
      return undefined;
    }

    let destroyed = false;
    let networkInstance: { destroy: () => void } | null = null;

    const styleTag = ensureVisTooltipStyles();
    const tooltipElement = ensureGraphTooltipElement();
    let hideTooltipTimer: number | null = null;

    if (destroyed || !containerRef.current) {
      return undefined;
    }

    const physics = buildVisPhysics(preparedGraph.nodes.length);
    const performanceProfile = buildGraphPerformanceProfile(preparedGraph.nodes.length);
    const hoverEnabled = performanceProfile.enableHover || performanceProfile.enableTooltipHover;
    const labelBehavior = buildLabelBehavior(preparedGraph.nodes.length);
    const neighborhoodFade = buildNeighborhoodFade(preparedGraph.nodes.length);
    const emitZoomChange = (value: number) => {
      const baseScale = Math.max(fitScaleRef.current, MIN_BASE_SCALE);
      const multiplier = clamp(value / baseScale, MIN_GRAPH_ZOOM, MAX_GRAPH_ZOOM);
      onZoomChange?.(Number(multiplier.toFixed(2)));
    };
    let activeNodeId = focusedNodeId ?? null;
    let hoveredNodeId: string | null = null;

    const baseNodes = preparedGraph.nodes;
    const baseEdges = preparedGraph.edges;
    const nodesData = new DataSet(baseNodes);
    const edgesData = new DataSet(baseEdges);
    let overviewStateDirty = false;
    const tooltipByNodeId = new Map(baseNodes.map((node) => [node.id, node.tooltipHtml]));

    const network = new Network(
      containerRef.current,
      { nodes: nodesData as never, edges: edgesData as never },
      {
        autoResize: true,
        layout: {
          improvedLayout: !performanceProfile.heavy,
          randomSeed: 7,
        },
        physics: {
          barnesHut: {
            gravitationalConstant: physics.gravitationalConstant,
            centralGravity: physics.centralGravity,
            springLength: physics.springLength,
            springConstant: physics.springConstant,
            damping: physics.damping,
            avoidOverlap: physics.avoidOverlap,
          },
          maxVelocity: physics.maxVelocity,
          minVelocity: physics.minVelocity,
          stabilization: { iterations: physics.iterations, fit: true },
        },
        interaction: {
          hover: hoverEnabled,
          tooltipDelay: 80,
          navigationButtons: false,
          keyboard: false,
          multiselect: false,
          zoomView: true,
          dragView: true,
          dragNodes: performanceProfile.enableNodeDrag,
          hideEdgesOnDrag: performanceProfile.hideEdgesWhileInteracting,
          hideEdgesOnZoom: performanceProfile.hideEdgesWhileInteracting,
        },
        edges: {
          smooth: performanceProfile.enableEdgeSmoothing ? { enabled: true, type: 'continuous', roundness: 0.5 } : false,
          arrows: { to: { enabled: false, scaleFactor: 0 } },
        },
        nodes: {
          shape: 'dot',
          borderWidth: 2,
          borderWidthSelected: 4,
          shadow: { enabled: !performanceProfile.heavy, color: 'rgba(0,0,0,0.55)', size: 10 },
        },
      },
    );

    networkInstance = network;
  networkRef.current = network;

    const hideTooltip = () => {
      if (hideTooltipTimer) {
        window.clearTimeout(hideTooltipTimer);
        hideTooltipTimer = null;
      }
      tooltipElement.style.display = 'none';
    };

    const keepTooltipOpen = () => {
      if (hideTooltipTimer) {
        window.clearTimeout(hideTooltipTimer);
        hideTooltipTimer = null;
      }
    };

    const scheduleHideTooltip = () => {
      if (hideTooltipTimer) {
        window.clearTimeout(hideTooltipTimer);
      }
      hideTooltipTimer = window.setTimeout(() => {
        tooltipElement.style.display = 'none';
      }, 160);
    };

    const updateTooltipPosition = (clientX: number, clientY: number) => {
      const margin = 18;
      const bounds = tooltipElement.getBoundingClientRect();
      const left = clientX + margin + bounds.width > window.innerWidth
        ? Math.max(12, clientX - bounds.width - margin)
        : clientX + margin;
      const top = clientY + margin + bounds.height > window.innerHeight
        ? Math.max(12, clientY - bounds.height - margin)
        : clientY + margin;
      tooltipElement.style.left = `${left}px`;
      tooltipElement.style.top = `${top}px`;
    };

    const showTooltip = (nodeId: string, event: unknown) => {
      const html = tooltipByNodeId.get(nodeId);
      if (!html) {
        return;
      }

      if (hideTooltipTimer) {
        window.clearTimeout(hideTooltipTimer);
        hideTooltipTimer = null;
      }

      tooltipElement.innerHTML = html;
      tooltipElement.style.display = 'block';

      const pointerEvent = extractPointerEvent(event);
      updateTooltipPosition(pointerEvent.clientX, pointerEvent.clientY);
    };

    const handleTooltipClick = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }

      const actionButton = target.closest<HTMLButtonElement>('[data-graph-action]');
      const nodeId = actionButton?.dataset.nodeId;
      if (!nodeId) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();
      hideTooltip();
      if (actionButton?.dataset.graphAction === 'open-node') {
        onOpenNode?.(nodeId);
        return;
      }
      if (actionButton?.dataset.graphAction === 'detect-synapses') {
        onDetectSynapses?.(nodeId);
      }
    };

    tooltipElement.addEventListener('mouseenter', keepTooltipOpen);
    tooltipElement.addEventListener('mouseleave', scheduleHideTooltip);
    tooltipElement.addEventListener('click', handleTooltipClick);

    const collectRelatedNodes = (nodeId: string | null) => {
      if (!nodeId) {
        return null;
      }
      const relatedNodeIds = new Set(network.getConnectedNodes(nodeId) as string[]);
      relatedNodeIds.add(nodeId);
      return relatedNodeIds;
    };

    const shouldShowLabel = (node: GraphNodeRecord, scaleValue: number, relatedNodeIds: Set<string> | null, emphasizedNodeId: string | null) => {
      if (node.id === emphasizedNodeId) {
        return true;
      }
      if (relatedNodeIds && relatedNodeIds.has(node.id) && scaleValue >= labelBehavior.relatedThreshold) {
        return true;
      }
      if (node.degree >= labelBehavior.priorityDegree && scaleValue >= labelBehavior.priorityThreshold) {
        return true;
      }
      return scaleValue >= labelBehavior.globalThreshold;
    };

    const applyVisualState = () => {
      const emphasizedNodeId = hoveredNodeId ?? activeNodeId;
      if (performanceProfile.skipIdleVisualRefresh && !emphasizedNodeId) {
        if (overviewStateDirty) {
          nodesData.update(baseNodes);
          edgesData.update(baseEdges);
          overviewStateDirty = false;
        }
        return;
      }

      overviewStateDirty = true;
      const relatedNodeIds = collectRelatedNodes(emphasizedNodeId);
      const scaleValue = network.getScale();

      for (const baseNode of baseNodes) {
        const isActive = baseNode.id === activeNodeId;
        const isHovered = baseNode.id === hoveredNodeId;
        const isRelated = relatedNodeIds ? relatedNodeIds.has(baseNode.id) : true;
        const isMuted = !isRelated;
        nodesData.update({
          id: baseNode.id,
          label: shouldShowLabel(baseNode, scaleValue, relatedNodeIds, emphasizedNodeId) ? baseNode.fullLabel : '',
          borderWidth: isActive ? 5 : isHovered ? 4 : isRelated ? 2.5 : 1,
          color: {
            background: isMuted ? fadeColor(baseNode.color.background, neighborhoodFade.nodeOpacity) : baseNode.color.background,
            border: isMuted ? fadeColor(baseNode.color.border, neighborhoodFade.fontOpacity) : baseNode.color.border,
            highlight: baseNode.color.highlight,
          },
          font: {
            ...baseNode.font,
            color: isMuted
              ? `rgba(226,232,240,${neighborhoodFade.fontOpacity})`
              : isActive || isHovered
                ? '#f8fafc'
                : '#cbd5e1',
            size: isActive ? 15 : isHovered ? 14 : 13,
          },
          shadow: isActive
            ? { enabled: true, color: 'rgba(255,255,255,0.45)', size: 32, x: 0, y: 0 }
            : isHovered
              ? { enabled: true, color: 'rgba(96,165,250,0.32)', size: 24, x: 0, y: 0 }
              : { enabled: false, color: 'rgba(0,0,0,0.55)', size: 10, x: 0, y: 0 },
        });
      }

      for (const baseEdge of baseEdges) {
        const isRelated = !relatedNodeIds || (relatedNodeIds.has(baseEdge.from) && relatedNodeIds.has(baseEdge.to));
        const isConnectedToActive = Boolean(activeNodeId) && (baseEdge.from === activeNodeId || baseEdge.to === activeNodeId);
        const isConnectedToHovered = Boolean(hoveredNodeId) && (baseEdge.from === hoveredNodeId || baseEdge.to === hoveredNodeId);
        edgesData.update({
          id: baseEdge.id,
          hidden: false,
          color: isConnectedToActive || isConnectedToHovered
            ? { color: 'rgba(248,250,252,0.82)', highlight: '#ffffff', hover: '#ffffff', inherit: false }
            : isRelated
              ? { color: 'rgba(148,163,184,0.36)', highlight: '#f8fafc', hover: '#f8fafc', inherit: false }
              : {
                  color: `rgba(71,85,105,${neighborhoodFade.edgeOpacity})`,
                  highlight: `rgba(71,85,105,${neighborhoodFade.edgeOpacity})`,
                  hover: `rgba(71,85,105,${neighborhoodFade.edgeOpacity})`,
                  inherit: false,
                },
          width: isConnectedToActive ? 2.2 : isConnectedToHovered ? 1.8 : isRelated ? 1 : neighborhoodFade.edgeWidth,
        });
      }
    };

    const fitOverview = () => {
      const animation = performanceProfile.enableAnimatedFit
        ? { duration: 250, easingFunction: 'easeInOutQuad' as const }
        : false;
      const baseFitOptions = { animation: false, nodes: baseNodes.map((node) => node.id) };

      try {
        network.fit(baseFitOptions);
        const fittedScale = Math.max(network.getScale(), MIN_BASE_SCALE);
        fitScaleRef.current = fittedScale;
        const viewPosition = network.getViewPosition();
        const targetScale = clamp(fittedScale * preferredScaleRef.current, MIN_BASE_SCALE, fittedScale * MAX_GRAPH_ZOOM);
        suppressZoomSyncRef.current = true;
        network.moveTo({
          position: viewPosition,
          scale: targetScale,
          animation,
        });
        emitZoomChange(targetScale);
        if (zoomSyncTimerRef.current) {
          window.clearTimeout(zoomSyncTimerRef.current);
        }
        zoomSyncTimerRef.current = window.setTimeout(() => {
          suppressZoomSyncRef.current = false;
        }, animation ? 280 : 0);
      } catch {
        network.fit(baseFitOptions);
        fitScaleRef.current = Math.max(network.getScale(), MIN_BASE_SCALE);
        emitZoomChange(network.getScale());
      }
    };

    const applyNeighborhoodFocus = (nodeId: string | null) => {
      if (!nodeId) {
        activeNodeId = null;
        applyVisualState();
        return;
      }

      activeNodeId = nodeId;
      applyVisualState();
      network.selectNodes([nodeId]);
      const baseScale = Math.max(fitScaleRef.current, MIN_BASE_SCALE);
      network.focus(nodeId, {
        scale: Math.max(baseScale * 1.1, baseScale * preferredScaleRef.current),
        locked: false,
        animation: {
          duration: 420,
          easingFunction: 'easeInOutQuad',
        },
      });
    };

    network.on('click', (params) => {
      const nodes = params.nodes as string[];
      if (!nodes.length) {
        hoveredNodeId = null;
        applyNeighborhoodFocus(null);
        fitOverview();
        return;
      }

      const nodeId = nodes[0];
      if (!nodeId) {
        return;
      }
      applyNeighborhoodFocus(nodeId);
      onSelectNode?.(nodeId);
    });

    network.on('doubleClick', (params) => {
      const nodes = params.nodes as string[];
      const nodeId = nodes[0];
      if (!nodeId) {
        return;
      }

      applyNeighborhoodFocus(nodeId);
      onOpenNode?.(nodeId);
    });

    if (hoverEnabled) {
      network.on('hoverNode', (params) => {
        hoveredNodeId = params.node as string;
        showTooltip(hoveredNodeId, params.event);
        if (performanceProfile.enableHover) {
          applyVisualState();
        }
      });

      network.on('blurNode', () => {
        hoveredNodeId = null;
        scheduleHideTooltip();
        if (performanceProfile.enableHover) {
          applyVisualState();
        }
      });
    }

    network.on('zoom', () => {
      const currentScale = Math.max(network.getScale(), MIN_BASE_SCALE);
      if (!suppressZoomSyncRef.current) {
        emitZoomChange(currentScale);
      }
      if (performanceProfile.skipIdleVisualRefresh && !activeNodeId && !hoveredNodeId) {
        return;
      }
      applyVisualState();
      if (redrawTimerRef.current) {
        window.clearTimeout(redrawTimerRef.current);
      }
      redrawTimerRef.current = window.setTimeout(() => {
        if (destroyed || networkRef.current !== network) {
          return;
        }
        try {
          network.redraw();
        } catch {
          // vis-network may tear down its renderer during unmount; ignore late redraws.
        }
      }, 80);
    });

    network.once('stabilizationIterationsDone', () => {
      if (performanceProfile.disablePhysicsAfterStabilization) {
        network.setOptions({ physics: false });
      }
      fitOverview();
      applyVisualState();
      if (focusedNodeId) {
        if (focusTimerRef.current) {
          window.clearTimeout(focusTimerRef.current);
        }
        focusTimerRef.current = window.setTimeout(() => {
          if (destroyed || networkRef.current !== network) {
            return;
          }
          applyNeighborhoodFocus(focusedNodeId);
        }, 120);
      }
    });

    applyVisualState();

    const handleResize = () => {
      if (activeNodeId || hoveredNodeId) {
        return;
      }
      fitOverview();
    };

    window.addEventListener('resize', handleResize);

    return () => {
      destroyed = true;
      networkInstance?.destroy();
      networkRef.current = null;
      hideTooltip();
      if (zoomSyncTimerRef.current) {
        window.clearTimeout(zoomSyncTimerRef.current);
        zoomSyncTimerRef.current = null;
      }
      if (redrawTimerRef.current) {
        window.clearTimeout(redrawTimerRef.current);
        redrawTimerRef.current = null;
      }
      if (focusTimerRef.current) {
        window.clearTimeout(focusTimerRef.current);
        focusTimerRef.current = null;
      }
      tooltipElement.removeEventListener('mouseenter', keepTooltipOpen);
      tooltipElement.removeEventListener('mouseleave', scheduleHideTooltip);
      tooltipElement.removeEventListener('click', handleTooltipClick);
      window.removeEventListener('resize', handleResize);
      if (styleTag && document.head.contains(styleTag)) {
        document.head.removeChild(styleTag);
      }
      if (tooltipElement.parentElement) {
        tooltipElement.parentElement.removeChild(tooltipElement);
      }
    };
  }, [focusedNodeId, onDetectSynapses, onOpenNode, onSelectNode, onZoomChange, preparedGraph]);

  return (
    <div style={styles.container}>
      <div style={styles.graphFrame}>
        <div ref={containerRef} style={{ ...styles.graphSurface, height: viewportHeight }} />
        <div style={styles.zoomDock}>
          <button type="button" style={styles.zoomButton} onClick={onZoomOut} aria-label="Zoom arriere">-</button>
          <div style={styles.zoomLabel}>{zoom.toFixed(1)}x</div>
          <button type="button" style={styles.zoomButton} onClick={onZoomIn} aria-label="Zoom avant">+</button>
          <button type="button" style={styles.resetButton} onClick={onZoomReset}>Adapter</button>
        </div>
      </div>
      <div style={styles.captionRow}>
        <p style={styles.captionText}>{preparedGraph.nodes.length} noeuds affiches sur {data.nodes.length}</p>
        <p style={styles.captionText}>Rendu type Obsidian: repulsion Barnes-Hut, liaisons elastiques, stabilisation puis recentrage anime.</p>
        <p style={styles.captionText}>Le zoom de l'ecran pilote la camera, le focus met le voisinage direct au premier plan, et un double-clic ouvre la note.</p>
      </div>
    </div>
  );
}

function buildPreparedGraph(data: GraphData, focusedNodeId?: string) {
  const groupColors = buildGroupColorMap(data.nodes.map((node) => node.group));
  const labelBehavior = buildLabelBehavior(data.nodes.length);
  const heavyProfile = buildGraphPerformanceProfile(data.nodes.length);
  const nodes: GraphNodeRecord[] = data.nodes.map((node) => ({
    ...node,
    fullLabel: node.label,
    tooltipHtml: buildNodeTooltipHtml(node),
    label: shouldRenderInitialLabel(
      node.degree,
      focusedNodeId ? 0 : heavyProfile.skipIdleVisualRefresh ? Math.max(labelBehavior.priorityDegree + 2, 12) : labelBehavior.priorityDegree,
    ) ? node.label : '',
    title: ' ',
    color: {
      background: node.noteType ? (NOTE_TYPE_COLORS[node.noteType] ?? '#60a5fa') : (groupColors.get(node.group) ?? '#2a5f95'),
      border: focusedNodeId === node.id ? '#f8fafc' : 'rgba(15, 23, 42, 0.82)',
      highlight: {
        background: node.noteType ? (NOTE_TYPE_COLORS[node.noteType] ?? '#93c5fd') : (groupColors.get(node.group) ?? '#60a5fa'),
        border: '#f8fafc',
      },
    },
    value: Math.max(12, Math.min(36, 12 + node.degree * 1.7)),
    mass: Math.max(1, Math.min(6, 1 + node.degree / 4)),
    font: { color: '#e2e8f0', size: 13, face: 'Inter, system-ui, sans-serif' },
    labelHighlightBold: true,
    shadow: {
      enabled: focusedNodeId === node.id,
      color: 'rgba(255,255,255,0.35)',
      size: 28,
      x: 0,
      y: 0,
    },
  }));

  const edges: GraphEdgeRecord[] = data.edges.map((edge) => ({
    ...edge,
    from: edge.source,
    to: edge.target,
    color: { color: 'rgba(148, 163, 184, 0.42)', highlight: '#f8fafc', hover: '#f8fafc', inherit: false },
    smooth: { type: 'continuous' },
    arrows: { to: { enabled: false, scaleFactor: 0 } },
    width: 1,
    selectionWidth: 2.4,
  }));

  return { nodes, edges };
}

function buildGraphScene(data: GraphData, windowWidth: number) {
  const baseWidth = Math.max(320, Math.min(windowWidth - 72, 980));
  const heightBase = Math.max(360, Math.min(620, Math.round(baseWidth * 0.72)));
  return { width: baseWidth, height: heightBase };
}

function buildVisPhysics(nodeCount: number) {
  if (nodeCount > 700) {
    return {
      gravitationalConstant: -7600,
      centralGravity: 0.16,
      springLength: 84,
      springConstant: 0.028,
      damping: 0.38,
      avoidOverlap: 0.98,
      maxVelocity: 20,
      minVelocity: 0.9,
      iterations: 60,
    };
  }
  if (nodeCount > 320) {
    return {
      gravitationalConstant: -10400,
      centralGravity: 0.12,
      springLength: 96,
      springConstant: 0.03,
      damping: 0.32,
      avoidOverlap: 0.96,
      maxVelocity: 28,
      minVelocity: 0.68,
      iterations: 120,
    };
  }
  if (nodeCount > 220) {
    return {
      gravitationalConstant: -9200,
      centralGravity: 0.16,
      springLength: 118,
      springConstant: 0.038,
      damping: 0.25,
      avoidOverlap: 0.94,
      maxVelocity: 40,
      minVelocity: 0.7,
      iterations: 280,
    };
  }
  if (nodeCount > 120) {
    return {
      gravitationalConstant: -7600,
      centralGravity: 0.2,
      springLength: 128,
      springConstant: 0.041,
      damping: 0.22,
      avoidOverlap: 0.9,
      maxVelocity: 44,
      minVelocity: 0.72,
      iterations: 240,
    };
  }
  return {
    gravitationalConstant: -6200,
    centralGravity: 0.26,
    springLength: 148,
    springConstant: 0.043,
    damping: 0.18,
    avoidOverlap: 0.82,
    maxVelocity: 50,
    minVelocity: 0.75,
    iterations: 180,
  };
}

function buildGraphPerformanceProfile(nodeCount: number) {
  if (nodeCount > 700) {
    return {
      heavy: true,
      enableHover: false,
      enableNodeDrag: false,
      enableEdgeSmoothing: false,
      disablePhysicsAfterStabilization: true,
      skipIdleVisualRefresh: true,
      hideEdgesWhileInteracting: true,
      enableAnimatedFit: false,
      enableTooltipHover: true,
    };
  }

  if (nodeCount > 480) {
    return {
      heavy: true,
      enableHover: false,
      enableNodeDrag: false,
      enableEdgeSmoothing: false,
      disablePhysicsAfterStabilization: true,
      skipIdleVisualRefresh: true,
      hideEdgesWhileInteracting: true,
      enableAnimatedFit: false,
      enableTooltipHover: true,
    };
  }

  if (nodeCount > 320) {
    return {
      heavy: true,
      enableHover: false,
      enableNodeDrag: false,
      enableEdgeSmoothing: true,
      disablePhysicsAfterStabilization: true,
      skipIdleVisualRefresh: true,
      hideEdgesWhileInteracting: true,
      enableAnimatedFit: false,
      enableTooltipHover: true,
    };
  }

  return {
    heavy: false,
    enableHover: true,
    enableNodeDrag: true,
    enableEdgeSmoothing: true,
    disablePhysicsAfterStabilization: false,
    skipIdleVisualRefresh: false,
    hideEdgesWhileInteracting: false,
    enableAnimatedFit: true,
    enableTooltipHover: true,
  };
}

function shouldRenderInitialLabel(degree: number, threshold: number) {
  return degree >= threshold;
}

function buildLabelBehavior(nodeCount: number) {
  if (nodeCount > 320) {
    return {
      globalThreshold: 1.32,
      relatedThreshold: 1.02,
      priorityThreshold: 0.98,
      priorityDegree: 12,
    };
  }
  if (nodeCount > 180) {
    return {
      globalThreshold: 1.2,
      relatedThreshold: 0.98,
      priorityThreshold: 0.94,
      priorityDegree: 9,
    };
  }
  if (nodeCount > 96) {
    return {
      globalThreshold: 1.08,
      relatedThreshold: 0.92,
      priorityThreshold: 0.88,
      priorityDegree: 7,
    };
  }
  return {
    globalThreshold: 0.94,
    relatedThreshold: 0.84,
    priorityThreshold: 0.82,
    priorityDegree: 4,
  };
}

function buildNeighborhoodFade(nodeCount: number) {
  if (nodeCount > 320) {
    return {
      nodeOpacity: 0.22,
      fontOpacity: 0.28,
      edgeOpacity: 0.16,
      edgeWidth: 0.55,
    };
  }
  if (nodeCount > 180) {
    return {
      nodeOpacity: 0.26,
      fontOpacity: 0.32,
      edgeOpacity: 0.18,
      edgeWidth: 0.58,
    };
  }
  if (nodeCount > 96) {
    return {
      nodeOpacity: 0.3,
      fontOpacity: 0.36,
      edgeOpacity: 0.2,
      edgeWidth: 0.62,
    };
  }
  return {
    nodeOpacity: 0.36,
    fontOpacity: 0.42,
    edgeOpacity: 0.24,
    edgeWidth: 0.68,
  };
}

function buildGroupColorMap(groups: string[]) {
  const uniqueGroups = [...new Set(groups)].sort();
  return new Map(uniqueGroups.map((group, index) => [group, GROUP_COLORS[index % GROUP_COLORS.length]]));
}

function buildNodeTooltipHtml(node: GraphData['nodes'][number]) {
  const date = node.dateModified ? String(node.dateModified).slice(0, 10) : 'date inconnue';
  const tags = node.tags.slice(0, 5);
  const noteType = node.noteType ? `<span class="obsirag-graph-tooltip__badge">${escapeHtml(node.noteType)}</span>` : '';
  const tagHtml = tags.length
    ? `<div class="obsirag-graph-tooltip__tags">${tags.map((tag) => `<span class="obsirag-graph-tooltip__tag">#${escapeHtml(tag)}</span>`).join('')}</div>`
    : '';
  const openAction = `<button type="button" class="obsirag-graph-tooltip__action" data-graph-action="open-node" data-node-id="${escapeHtml(node.id)}">Ouvrir l'element</button>`;
  const synapseAction = `<button type="button" class="obsirag-graph-tooltip__action obsirag-graph-tooltip__action--secondary" data-graph-action="detect-synapses" data-node-id="${escapeHtml(node.id)}">Detecter des synapses</button>`;

  return `
    <div class="obsirag-graph-tooltip__card">
      <div class="obsirag-graph-tooltip__title">${escapeHtml(node.label)}</div>
      <div class="obsirag-graph-tooltip__meta">
        <span>${escapeHtml(date)}</span>
        ${noteType}
      </div>
      ${tagHtml}
      <div class="obsirag-graph-tooltip__actions">
        ${openAction}
        ${synapseAction}
      </div>
    </div>
  `;
}

function ensureVisTooltipStyles() {
  const existing = document.head.querySelector<HTMLStyleElement>('style[data-obsirag-vis]');
  if (existing) {
    return existing;
  }

  const styleTag = document.createElement('style');
  styleTag.dataset.obsiragVis = 'true';
  styleTag.textContent = `
    .vis-network:focus { outline: none; }
    #obsirag-graph-tooltip {
      position: fixed;
      z-index: 9999;
      min-width: 240px;
      max-width: min(520px, calc(100vw - 24px));
      display: none;
      pointer-events: auto;
      border-radius: 16px;
      border: 1px solid rgba(96, 165, 250, 0.22);
      background: rgba(15, 23, 42, 0.96);
      box-shadow: 0 24px 80px rgba(0,0,0,0.42);
      backdrop-filter: blur(16px);
      color: #e2e8f0;
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    .obsirag-graph-tooltip__card {
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 14px 16px;
    }
    .obsirag-graph-tooltip__title {
      font-size: 17px;
      line-height: 1.35;
      font-weight: 700;
      color: #f8fafc;
      word-break: break-word;
    }
    .obsirag-graph-tooltip__meta {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      color: #cbd5e1;
      font-size: 13px;
    }
    .obsirag-graph-tooltip__badge {
      display: inline-flex;
      align-items: center;
      padding: 4px 9px;
      border-radius: 999px;
      background: rgba(96, 165, 250, 0.16);
      border: 1px solid rgba(96, 165, 250, 0.28);
      color: #bfdbfe;
      font-size: 12px;
      font-weight: 700;
      text-transform: capitalize;
    }
    .obsirag-graph-tooltip__tags {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .obsirag-graph-tooltip__tag {
      display: inline-flex;
      align-items: center;
      padding: 5px 10px;
      border-radius: 999px;
      background: rgba(148, 163, 184, 0.14);
      border: 1px solid rgba(148, 163, 184, 0.2);
      color: #e2e8f0;
      font-size: 12px;
      line-height: 1;
    }
    .obsirag-graph-tooltip__actions {
      display: flex;
      justify-content: flex-start;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 2px;
    }
    .obsirag-graph-tooltip__action {
      border: none;
      border-radius: 999px;
      padding: 9px 14px;
      background: linear-gradient(135deg, #60a5fa 0%, #2563eb 100%);
      color: #eff6ff;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 10px 24px rgba(37, 99, 235, 0.32);
    }
    .obsirag-graph-tooltip__action:hover {
      filter: brightness(1.05);
    }
    .obsirag-graph-tooltip__action--secondary {
      background: rgba(148, 163, 184, 0.16);
      color: #e2e8f0;
      border: 1px solid rgba(148, 163, 184, 0.28);
      box-shadow: none;
    }
  `;
  document.head.appendChild(styleTag);
  return styleTag;
}

function ensureGraphTooltipElement() {
  const existing = document.body.querySelector<HTMLDivElement>('#obsirag-graph-tooltip');
  if (existing) {
    return existing;
  }

  const tooltipElement = document.createElement('div');
  tooltipElement.id = 'obsirag-graph-tooltip';
  document.body.appendChild(tooltipElement);
  return tooltipElement;
}

function extractPointerEvent(event: unknown) {
  const candidate = event as {
    clientX?: number;
    clientY?: number;
    pointer?: { DOM?: { x?: number; y?: number } };
    srcEvent?: { clientX?: number; clientY?: number };
  } | null;

  const clientX = candidate?.clientX
    ?? candidate?.srcEvent?.clientX
    ?? candidate?.pointer?.DOM?.x
    ?? window.innerWidth / 2;
  const clientY = candidate?.clientY
    ?? candidate?.srcEvent?.clientY
    ?? candidate?.pointer?.DOM?.y
    ?? window.innerHeight / 2;

  return { clientX, clientY };
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function fadeColor(color: string, alpha: number) {
  if (color.startsWith('rgba(')) {
    return color.replace(/rgba\(([^,]+),([^,]+),([^,]+),[^)]+\)/, `rgba($1,$2,$3,${alpha})`);
  }
  if (color.startsWith('rgb(')) {
    return color.replace(/rgb\(([^,]+),([^,]+),([^)]+)\)/, `rgba($1,$2,$3,${alpha})`);
  }
  if (color.startsWith('#') && (color.length === 7 || color.length === 4)) {
    const hex = color.length === 4
      ? color.split('').map((value, index) => (index === 0 ? '' : value + value)).join('')
      : color.slice(1);
    const red = Number.parseInt(hex.slice(0, 2), 16);
    const green = Number.parseInt(hex.slice(2, 4), 16);
    const blue = Number.parseInt(hex.slice(4, 6), 16);
    return `rgba(${red},${green},${blue},${alpha})`;
  }
  return color;
}

const styles: Record<string, CSSProperties> = {
  container: {
    borderRadius: 16,
    border: '1px solid #2f3e4d',
    backgroundColor: '#12161c',
    padding: 10,
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  graphFrame: {
    position: 'relative',
  },
  graphSurface: {
    width: '100%',
    minHeight: 360,
    background: 'radial-gradient(circle at 20% 20%, rgba(96,165,250,0.08), transparent 32%), radial-gradient(circle at 80% 10%, rgba(192,132,252,0.08), transparent 30%), linear-gradient(180deg, #12161c 0%, #0b0f14 100%)',
  },
  zoomDock: {
    position: 'absolute',
    right: 14,
    bottom: 14,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: 8,
    borderRadius: 14,
    border: '1px solid rgba(148, 163, 184, 0.18)',
    background: 'rgba(15, 23, 42, 0.84)',
    boxShadow: '0 18px 40px rgba(0,0,0,0.28)',
    backdropFilter: 'blur(12px)',
  },
  zoomButton: {
    width: 34,
    height: 34,
    border: 'none',
    borderRadius: 999,
    background: '#263e5f',
    color: '#f9f6f0',
    fontSize: 18,
    fontWeight: 700,
    cursor: 'pointer',
  },
  zoomLabel: {
    minWidth: 52,
    textAlign: 'center',
    color: '#f8fafc',
    fontSize: 13,
    fontWeight: 700,
  },
  resetButton: {
    border: 'none',
    borderRadius: 999,
    padding: '8px 12px',
    background: '#e8ddd0',
    color: '#3d2e20',
    fontSize: 13,
    fontWeight: 700,
    cursor: 'pointer',
  },
  captionRow: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  captionText: {
    margin: 0,
    color: '#9bb2c7',
    fontSize: 12,
    lineHeight: 1.5,
  },
};