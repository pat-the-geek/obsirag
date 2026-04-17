import { useEffect, useMemo, useRef, useState } from 'react';
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from 'd3-force';
import { Animated, Easing, Platform, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import Svg, { Circle, G, Line, Text as SvgText } from 'react-native-svg';
import { WebView } from 'react-native-webview';

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

type PositionedNode = {
  id: string;
  label: string;
  group: string;
  degree: number;
  noteType?: string;
  x: number;
  y: number;
  radius: number;
};

type ForceNode = SimulationNodeDatum & PositionedNode;
type ForceLink = SimulationLinkDatum<ForceNode> & {
  id: string;
  source: string | ForceNode;
  target: string | ForceNode;
};

const GROUP_COLORS = ['#2a5f95', '#c46a2f', '#4b7f52', '#875f9a', '#5a768d', '#9b4f46'];
const NOTE_TYPE_COLORS: Record<string, string> = {
  user: '#60a5fa',
  report: '#f59e0b',
  insight: '#facc15',
  synapse: '#c084fc',
};
const AnimatedLine = Animated.createAnimatedComponent(Line);
const AnimatedCircle = Animated.createAnimatedComponent(Circle);
const AnimatedSvgText = Animated.createAnimatedComponent(SvgText);

export function KnowledgeGraph({ data, focusedNodeId, onSelectNode, onOpenNode, onDetectSynapses, zoom = 1, onZoomChange: _onZoomChange, onZoomIn, onZoomOut, onZoomReset }: KnowledgeGraphProps) {
  const windowDimensions = useWindowDimensions();
  const edgeReveal = useRef(new Animated.Value(0)).current;
  const nodeReveal = useRef(new Animated.Value(0)).current;
  const motionProgress = useRef(new Animated.Value(1)).current;
  const fitScale = useRef(new Animated.Value(1)).current;
  const shouldAnimate = process.env.NODE_ENV !== 'test';
  const [motionValue, setMotionValue] = useState(1);
  const [fitScaleValue, setFitScaleValue] = useState(1);
  const renderData = useMemo(() => selectRenderableGraph(data, focusedNodeId), [data, focusedNodeId]);
  const scene = useMemo(() => buildGraphScene(renderData, windowDimensions.width), [renderData, windowDimensions.width]);
  const viewportWidth = scene.width;
  const viewportHeight = scene.height;
  const layout = useMemo(() => buildForceLayout(renderData, viewportWidth, viewportHeight), [renderData, viewportWidth, viewportHeight]);
  const groupColors = useMemo(() => buildGroupColorMap(renderData.nodes.map((node) => node.group)), [renderData]);
  const canvasWidth = Math.round(viewportWidth * zoom);
  const canvasHeight = Math.round(viewportHeight * zoom);
  const edgeStyle = useMemo(() => buildEdgeStyle(renderData.nodes.length), [renderData.nodes.length]);
  const labelMode = useMemo(() => buildLabelMode(renderData, focusedNodeId), [focusedNodeId, renderData]);
  const shouldUseHtmlGraph = process.env.NODE_ENV !== 'test';
  const htmlFrameId = useMemo(
    () => `graph-${focusedNodeId ?? 'overview'}-${zoom.toFixed(2)}-${renderData.nodes.length}-${renderData.edges.length}`,
    [focusedNodeId, renderData.edges.length, renderData.nodes.length, zoom],
  );
  const htmlGraph = useMemo(() => buildVisNetworkHtml(renderData, focusedNodeId, zoom, htmlFrameId), [focusedNodeId, renderData, zoom, htmlFrameId]);

  useEffect(() => {
    if (Platform.OS !== 'web' || !shouldUseHtmlGraph) {
      return undefined;
    }

    const handleMessage = (event: MessageEvent) => {
      const payload = typeof event.data === 'string' ? safeParseGraphMessage(event.data) : event.data;
      if (!payload || payload.frameId !== htmlFrameId) {
        return;
      }
      if (payload.type === 'nodePress' && payload.nodeId) {
        onSelectNode?.(payload.nodeId);
      }
      if (payload.type === 'nodeOpen' && payload.nodeId) {
        onOpenNode?.(payload.nodeId);
      }
      if (payload.type === 'nodeDetectSynapses' && payload.nodeId) {
        onDetectSynapses?.(payload.nodeId);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [htmlFrameId, onDetectSynapses, onOpenNode, onSelectNode, shouldUseHtmlGraph]);

  useEffect(() => {
    const motionId = motionProgress.addListener(({ value }) => setMotionValue(value));
    const fitId = fitScale.addListener(({ value }) => setFitScaleValue(value));
    return () => {
      motionProgress.removeListener(motionId);
      fitScale.removeListener(fitId);
    };
  }, [fitScale, motionProgress]);

  useEffect(() => {
    if (!shouldAnimate) {
      edgeReveal.setValue(1);
      nodeReveal.setValue(1);
      motionProgress.setValue(1);
      fitScale.setValue(1);
      return undefined;
    }

    edgeReveal.setValue(0);
    nodeReveal.setValue(0);
    motionProgress.setValue(0);
    fitScale.setValue(0.965);
    const animation = Animated.sequence([
      Animated.timing(edgeReveal, {
        toValue: 1,
        duration: 220,
        easing: Easing.out(Easing.quad),
        useNativeDriver: false,
      }),
      Animated.parallel([
        Animated.timing(motionProgress, {
          toValue: 1,
          duration: 650,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: false,
        }),
        Animated.timing(nodeReveal, {
          toValue: 1,
          duration: 340,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: false,
        }),
      ]),
      Animated.timing(fitScale, {
        toValue: 1,
        duration: 250,
        easing: Easing.inOut(Easing.quad),
        useNativeDriver: false,
      }),
    ]);
    animation.start();
    return () => animation.stop();
  }, [edgeReveal, fitScale, motionProgress, nodeReveal, focusedNodeId, layout, renderData, shouldAnimate]);

  const edgeOpacity = edgeReveal.interpolate({
    inputRange: [0, 1],
    outputRange: [0, edgeStyle.opacity],
  });
  const nodeOpacity = nodeReveal.interpolate({
    inputRange: [0, 1],
    outputRange: [0.2, 1],
  });
  const labelOpacity = nodeReveal.interpolate({
    inputRange: [0, 0.55, 1],
    outputRange: [0, 0, 1],
  });
  const animatedNodes = useMemo(() => {
    const sampleMaps = layout.samples.map((sample) => new Map(sample.map((node) => [node.id, node])));
    return layout.nodes.map((node) => {
      const sampled = interpolateNodeSample(node.id, sampleMaps, motionValue) ?? node;
      return {
        ...node,
        x: sampled.x,
        y: sampled.y,
        radius: sampled.radius,
      };
    });
  }, [layout.nodes, layout.samples, motionValue]);
  const animatedNodeMap = useMemo(() => new Map(animatedNodes.map((node) => [node.id, node])), [animatedNodes]);
  const fittedWidth = viewportWidth * fitScaleValue;
  const fittedHeight = viewportHeight * fitScaleValue;
  const fitOffsetX = (viewportWidth - fittedWidth) / 2;
  const fitOffsetY = (viewportHeight - fittedHeight) / 2;

  if (shouldUseHtmlGraph) {
    return (
      <View style={styles.container}>
        <View style={styles.graphFrame}>
          {Platform.OS === 'web' ? (
            <iframe
              key={htmlFrameId}
              srcDoc={htmlGraph}
              style={{
                width: '100%',
                height: viewportHeight,
                border: 'none',
                backgroundColor: '#12161c',
              }}
              sandbox="allow-scripts allow-same-origin"
              title="ObsiRAG Knowledge Graph"
            />
          ) : (
            <WebView
              key={htmlFrameId}
              originWhitelist={['*']}
              source={{ html: htmlGraph }}
              style={[styles.webview, { height: viewportHeight }]}
              scrollEnabled={false}
              nestedScrollEnabled={false}
              onMessage={(event) => {
                const payload = safeParseGraphMessage(event.nativeEvent.data);
                if (!payload) {
                  return;
                }
                if (payload.type === 'nodePress' && payload.nodeId) {
                  onSelectNode?.(payload.nodeId);
                }
                if (payload.type === 'nodeOpen' && payload.nodeId) {
                  onOpenNode?.(payload.nodeId);
                }
              }}
            />
          )}
          <View style={styles.zoomDock} pointerEvents="box-none">
            <Pressable style={styles.zoomButton} onPress={onZoomOut}>
              <Text style={styles.zoomButtonText}>-</Text>
            </Pressable>
            <Text style={styles.zoomDockLabel}>{zoom.toFixed(1)}x</Text>
            <Pressable style={styles.zoomButton} onPress={onZoomIn}>
              <Text style={styles.zoomButtonText}>+</Text>
            </Pressable>
            <Pressable style={styles.resetZoomDockButton} onPress={onZoomReset}>
              <Text style={styles.resetZoomDockButtonText}>Adapter</Text>
            </Pressable>
          </View>
        </View>
        <View style={styles.captionRow}>
          <Text style={styles.captionText}>{renderData.nodes.length} noeuds affiches sur {data.nodes.length}</Text>
          <Text style={styles.captionText}>Rendu type Obsidian: repulsion Barnes-Hut, liaisons elastiques, stabilisation puis recentrage anime.</Text>
          <Text style={styles.captionText}>Le zoom de l'ecran pilote la camera, le focus met le voisinage direct au premier plan, et un double-clic ouvre la note.</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.graphFrame}>
        <ScrollView horizontal nestedScrollEnabled contentContainerStyle={styles.scrollContent}>
          <ScrollView nestedScrollEnabled contentContainerStyle={styles.scrollContent}>
            <Svg width={canvasWidth} height={canvasHeight} viewBox={`0 0 ${viewportWidth} ${viewportHeight}`}>
              <G transform={`translate(${fitOffsetX} ${fitOffsetY}) scale(${fitScaleValue})`}>
            {renderData.edges.map((edge) => {
              const source = animatedNodeMap.get(edge.source);
              const target = animatedNodeMap.get(edge.target);
              if (!source || !target) {
                return null;
              }

              return (
                <AnimatedLine
                  key={edge.id}
                  x1={source.x}
                  y1={source.y}
                  x2={target.x}
                  y2={target.y}
                  stroke="#b9c8d5"
                  strokeWidth={edgeStyle.strokeWidth}
                  opacity={edgeOpacity}
                />
              );
            })}

              {animatedNodes.map((node) => {
                const isFocused = node.id === focusedNodeId;
                const fill = (node.noteType ? NOTE_TYPE_COLORS[node.noteType] : undefined) ?? groupColors.get(node.group) ?? GROUP_COLORS[0] ?? '#2a5f95';
                const showLabel = shouldShowLabel(node, labelMode, isFocused);
                return (
                  <G key={node.id} testID={`graph-node-${node.id}`} onPress={() => onSelectNode?.(node.id)}>
                    <AnimatedCircle
                      cx={node.x}
                      cy={node.y}
                      r={node.radius}
                      fill={fill}
                      stroke={isFocused ? '#1a1a1a' : '#ffffff'}
                      strokeWidth={isFocused ? 3 : 2}
                      opacity={nodeOpacity}
                    />
                    {showLabel ? (
                      <AnimatedSvgText
                        x={node.x}
                        y={node.y + node.radius + 14}
                        fontSize={node.radius > 16 ? '12' : '11'}
                        fontWeight="700"
                        fill="#dce8f2"
                        textAnchor="middle"
                        opacity={labelOpacity}
                      >
                        {truncateLabel(node.label)}
                      </AnimatedSvgText>
                    ) : null}
                  </G>
                );
              })}
              </G>
            </Svg>
          </ScrollView>
        </ScrollView>
        <View style={styles.zoomDock} pointerEvents="box-none">
          <Pressable style={styles.zoomButton} onPress={onZoomOut}>
            <Text style={styles.zoomButtonText}>-</Text>
          </Pressable>
          <Text style={styles.zoomDockLabel}>{zoom.toFixed(1)}x</Text>
          <Pressable style={styles.zoomButton} onPress={onZoomIn}>
            <Text style={styles.zoomButtonText}>+</Text>
          </Pressable>
          <Pressable style={styles.resetZoomDockButton} onPress={onZoomReset}>
            <Text style={styles.resetZoomDockButtonText}>Adapter</Text>
          </Pressable>
        </View>
      </View>

      <View style={styles.captionRow}>
        <Text style={styles.captionText}>
          {renderData.nodes.length} noeuds affiches sur {data.nodes.length}
        </Text>
        <Text style={styles.captionText}>Le diagramme organise automatiquement les noeuds pour garder l'ensemble des elements dans la zone visible.</Text>
        {labelMode.mode !== 'all' ? <Text style={styles.captionText}>Les libelles secondaires sont reduits pour garder une vue lisible. Touchez un noeud pour le mettre au premier plan.</Text> : null}
      </View>
    </View>
  );
}

function selectRenderableGraph(data: GraphData, focusedNodeId?: string) {
  return data;
}

function buildGraphScene(data: GraphData, windowWidth: number) {
  const baseWidth = Math.max(320, Math.min(windowWidth - 72, 980));
  const heightBase = Math.max(360, Math.min(620, Math.round(baseWidth * 0.72)));
  return { width: baseWidth, height: heightBase };
}

function buildForceLayout(data: GraphData, width: number, height: number) {
  const sortedNodes = [...data.nodes].sort((left, right) => right.degree - left.degree || left.label.localeCompare(right.label));
  const simulationNodes: ForceNode[] = sortedNodes.map((node, index) => {
    const angle = stableHash(node.id) * Math.PI * 2;
    const radial = Math.min(width, height) * (0.12 + (index / Math.max(1, sortedNodes.length)) * 0.24);
    return {
      ...node,
      x: width / 2 + Math.cos(angle) * radial,
      y: height / 2 + Math.sin(angle) * radial,
      radius: buildNodeRadius(node.degree, sortedNodes.length),
    };
  });
  const simulationLinks: ForceLink[] = data.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
  }));
  const repulsion = buildRepulsionStrength(simulationNodes.length);
  const linkDistance = buildLinkDistance(simulationNodes.length);
  const tickCount = buildTickCount(simulationNodes.length);

  const simulation = forceSimulation(simulationNodes)
    .force('charge', forceManyBody<ForceNode>().strength(repulsion))
    .force('link', forceLink<ForceNode, ForceLink>(simulationLinks).id((node) => node.id).distance(linkDistance).strength(0.08))
    .force('center', forceCenter(width / 2, height / 2))
    .force('collision', forceCollide<ForceNode>().radius((node) => node.radius + 8).strength(0.9).iterations(2))
    .stop();

  const samples: PositionedNode[][] = [
    simulationNodes.map((node, index) => {
      const angle = stableHash(node.id) * Math.PI * 2 + index * 0.08;
      const radial = Math.min(width, height) * (0.08 + (index / Math.max(1, simulationNodes.length)) * 0.18);
      return {
        ...node,
        x: width / 2 + Math.cos(angle) * radial,
        y: height / 2 + Math.sin(angle) * radial,
        radius: Math.max(2.5, node.radius * 0.92),
      };
    }),
  ];
  const sampleStep = Math.max(10, Math.round(tickCount / 12));

  for (let tick = 0; tick < tickCount; tick += 1) {
    simulation.tick();
    if ((tick + 1) % sampleStep === 0 || tick === tickCount - 1) {
      samples.push(
        simulationNodes.map((node) => ({
          ...node,
          x: node.x ?? width / 2,
          y: node.y ?? height / 2,
          radius: node.radius,
        })),
      );
    }
  }

  simulation.stop();

  const fittedNodes = fitNodesToViewport(
    simulationNodes.map((node) => ({
      ...node,
      x: node.x ?? width / 2,
      y: node.y ?? height / 2,
    })),
    width,
    height,
  );

  return {
    samples: samples.map((sample) => fitNodesToViewport(sample, width, height)),
    nodes: fittedNodes,
    nodeMap: new Map(fittedNodes.map((node) => [node.id, node])),
  };
}

function buildNodeRadius(degree: number, nodeCount: number) {
  const base = nodeCount > 120 ? 3 : nodeCount > 64 ? 3.5 : 5;
  const scale = nodeCount > 120 ? 0.34 : nodeCount > 64 ? 0.48 : 0.85;
  return base + Math.min(nodeCount > 120 ? 5 : 8, Math.max(0, degree) * scale);
}

function buildRepulsionStrength(nodeCount: number) {
  if (nodeCount > 140) {
    return -260;
  }
  if (nodeCount > 80) {
    return -340;
  }
  return -420;
}

function buildLinkDistance(nodeCount: number) {
  if (nodeCount > 140) {
    return 26;
  }
  if (nodeCount > 80) {
    return 34;
  }
  return 42;
}

function buildTickCount(nodeCount: number) {
  if (nodeCount > 140) {
    return 260;
  }
  if (nodeCount > 80) {
    return 220;
  }
  return 180;
}

function buildEdgeStyle(nodeCount: number) {
  if (nodeCount > 120) {
    return { strokeWidth: 0.9, opacity: 0.42 };
  }
  if (nodeCount > 64) {
    return { strokeWidth: 1.1, opacity: 0.56 };
  }
  return { strokeWidth: 1.5, opacity: 0.9 };
}

function buildLabelMode(data: GraphData, focusedNodeId?: string) {
  if (focusedNodeId) {
    return { mode: 'all' as const, threshold: 0 };
  }
  if (data.nodes.length > 120) {
    return { mode: 'priority' as const, threshold: 7 };
  }
  if (data.nodes.length > 64) {
    return { mode: 'priority' as const, threshold: 5 };
  }
  return { mode: 'all' as const, threshold: 0 };
}

function shouldShowLabel(node: PositionedNode, labelMode: ReturnType<typeof buildLabelMode>, isFocused: boolean) {
  if (isFocused || labelMode.mode === 'all') {
    return true;
  }
  return node.degree >= labelMode.threshold;
}

function fitNodesToViewport(nodes: PositionedNode[], width: number, height: number) {
  if (!nodes.length) {
    return nodes;
  }

  const paddingX = 28;
  const paddingTop = 24;
  const paddingBottom = 40;
  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;

  for (const node of nodes) {
    minX = Math.min(minX, node.x - node.radius);
    maxX = Math.max(maxX, node.x + node.radius);
    minY = Math.min(minY, node.y - node.radius);
    maxY = Math.max(maxY, node.y + node.radius + 16);
  }

  const sourceWidth = Math.max(1, maxX - minX);
  const sourceHeight = Math.max(1, maxY - minY);
  const targetWidth = Math.max(1, width - paddingX * 2);
  const targetHeight = Math.max(1, height - paddingTop - paddingBottom);
  const scale = Math.min(targetWidth / sourceWidth, targetHeight / sourceHeight, 1);
  const scaledWidth = sourceWidth * scale;
  const scaledHeight = sourceHeight * scale;
  const offsetX = (width - scaledWidth) / 2 - minX * scale;
  const offsetY = (height - scaledHeight) / 2 - minY * scale;

  return nodes.map((node) => ({
    ...node,
    x: clamp(node.x * scale + offsetX, paddingX, width - paddingX),
    y: clamp(node.y * scale + offsetY, paddingTop, height - paddingBottom),
    radius: Math.max(2.5, node.radius * Math.max(0.72, scale)),
  }));
}

function stableHash(value: string) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967295;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function lerp(start: number, end: number, progress: number) {
  return start + (end - start) * progress;
}

function interpolateNodeSample(nodeId: string, sampleMaps: Array<Map<string, PositionedNode>>, progress: number) {
  if (!sampleMaps.length) {
    return undefined;
  }
  if (sampleMaps.length === 1) {
    return sampleMaps[0]?.get(nodeId);
  }

  const scaled = progress * (sampleMaps.length - 1);
  const leftIndex = Math.floor(scaled);
  const rightIndex = Math.min(sampleMaps.length - 1, leftIndex + 1);
  const localProgress = scaled - leftIndex;
  const left = sampleMaps[leftIndex]?.get(nodeId);
  const right = sampleMaps[rightIndex]?.get(nodeId) ?? left;

  if (!left || !right) {
    return left ?? right;
  }

  return {
    ...right,
    x: lerp(left.x, right.x, localProgress),
    y: lerp(left.y, right.y, localProgress),
    radius: lerp(left.radius, right.radius, localProgress),
  };
}

function buildGroupColorMap(groups: string[]) {
  const uniqueGroups = [...new Set(groups)].sort();
  return new Map(uniqueGroups.map((group, index) => [group, GROUP_COLORS[index % GROUP_COLORS.length]]));
}

function truncateLabel(value: string) {
  return value.length > 18 ? `${value.slice(0, 17)}…` : value;
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#2f3e4d',
    backgroundColor: '#12161c',
    padding: 10,
    gap: 8,
  },
  graphFrame: {
    position: 'relative',
  },
  scrollContent: {
    minWidth: '100%',
  },
  webview: {
    width: '100%',
    backgroundColor: '#12161c',
  },
  zoomDock: {
    position: 'absolute',
    right: 14,
    bottom: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 8,
    paddingVertical: 8,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: 'rgba(148, 163, 184, 0.18)',
    backgroundColor: 'rgba(15, 23, 42, 0.84)',
  },
  zoomDockLabel: {
    minWidth: 52,
    color: '#f8fafc',
    fontSize: 13,
    fontWeight: '700',
    textAlign: 'center',
  },
  resetZoomDockButton: {
    borderRadius: 999,
    backgroundColor: '#e8ddd0',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  resetZoomDockButtonText: {
    color: '#3d2e20',
    fontWeight: '700',
  },
  captionRow: {
    gap: 4,
  },
  captionText: {
    color: '#9bb2c7',
    fontSize: 12,
    lineHeight: 18,
  },
});

function buildVisNetworkHtml(data: GraphData, focusedNodeId?: string, zoom = 1, frameId?: string) {
  const groupColors = buildGroupColorMap(data.nodes.map((node) => node.group));
  const physics = buildVisPhysics(data.nodes.length);
  const performanceProfile = buildGraphPerformanceProfile(data.nodes.length);
  const hoverEnabled = performanceProfile.enableHover || performanceProfile.enableTooltipHover;
  const scale = clamp(zoom, 0.75, 2.2);
  const labelBehavior = buildLabelBehavior(data.nodes.length);
  const neighborhoodFade = buildNeighborhoodFade(data.nodes.length);
  const edgeSmoothing = performanceProfile.enableEdgeSmoothing ? '{ enabled: true, type: \'continuous\' }' : 'false';
  const nodes = data.nodes.map((node) => ({
    id: node.id,
    fullLabel: node.label,
    label: shouldRenderInitialLabel(node.degree, focusedNodeId ? 0 : labelBehavior.threshold)
      ? (node.label.length > 40 ? `${node.label.slice(0, 39)}…` : node.label)
      : '',
    title: buildNodeTooltipHtml(node),
    group: node.group,
    tags: node.tags,
    dateModified: node.dateModified,
    degree: node.degree,
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
  const edges = data.edges.map((edge) => ({
    id: edge.id,
    from: edge.source,
    to: edge.target,
    color: { color: 'rgba(148, 163, 184, 0.42)', highlight: '#f8fafc', hover: '#f8fafc', inherit: false },
    smooth: { type: 'continuous' },
    arrows: { to: { enabled: false, scaleFactor: 0 } },
    width: 1,
    selectionWidth: 2.4,
  }));

  return `<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <link rel="stylesheet" href="https://unpkg.com/vis-network/styles/vis-network.min.css" />
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
      * { box-sizing: border-box; }
      html, body {
        margin: 0;
        padding: 0;
        width: 100%;
        height: 100%;
        overflow: hidden;
        background: #12161c;
        color: #e2e8f0;
        font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      }
      #network {
        width: 100%;
        height: 100vh;
        background: radial-gradient(circle at 20% 20%, rgba(96,165,250,0.08), transparent 32%),
                    radial-gradient(circle at 80% 10%, rgba(192,132,252,0.08), transparent 30%),
                    linear-gradient(180deg, #12161c 0%, #0b0f14 100%);
      }
      .vis-network:focus { outline: none; }
      .vis-manipulation, .vis-edit-mode, .vis-navigation { display: none !important; }
      .vis-tooltip {
        background: rgba(15, 23, 42, 0.96) !important;
        border: 1px solid rgba(148, 163, 184, 0.28) !important;
        color: #e2e8f0 !important;
        border-radius: 10px !important;
        padding: 10px 12px !important;
        box-shadow: 0 18px 50px rgba(0,0,0,0.35) !important;
      }
    </style>
  </head>
  <body>
    <div id="network"></div>
    <script>
      (function () {
        const initialNodes = ${JSON.stringify(nodes)};
        const initialEdges = ${JSON.stringify(edges)};
        const nodes = new vis.DataSet(initialNodes);
        const edges = new vis.DataSet(initialEdges);
        const nodeById = new Map(initialNodes.map(function(node) { return [node.id, node]; }));
        const edgeById = new Map(initialEdges.map(function(edge) { return [edge.id, edge]; }));
        const focusedNodeId = ${JSON.stringify(focusedNodeId ?? null)};
        const frameId = ${JSON.stringify(frameId ?? null)};
        const preferredScale = ${JSON.stringify(scale)};
        const labelBehavior = ${JSON.stringify(labelBehavior)};
        const neighborhoodFade = ${JSON.stringify(neighborhoodFade)};
        const performanceProfile = ${JSON.stringify(performanceProfile)};
        const container = document.getElementById('network');
        let activeNodeId = focusedNodeId;
        let hoveredNodeId = null;
        let overviewStateDirty = false;
        const network = new vis.Network(container, { nodes, edges }, {
          autoResize: true,
          layout: {
            improvedLayout: !performanceProfile.heavy,
            randomSeed: 7,
          },
          physics: {
            barnesHut: {
              gravitationalConstant: ${physics.gravitationalConstant},
              centralGravity: ${physics.centralGravity},
              springLength: ${physics.springLength},
              springConstant: ${physics.springConstant},
              damping: ${physics.damping},
              avoidOverlap: ${physics.avoidOverlap},
            },
            maxVelocity: ${physics.maxVelocity},
            minVelocity: ${physics.minVelocity},
            stabilization: { iterations: ${physics.iterations}, fit: true },
          },
          interaction: {
            hover: ${JSON.stringify(hoverEnabled)},
            tooltipDelay: 80,
            navigationButtons: false,
            keyboard: false,
            multiselect: false,
            zoomView: true,
            dragView: true,
            dragNodes: ${JSON.stringify(performanceProfile.enableNodeDrag)},
            hideEdgesOnDrag: ${JSON.stringify(performanceProfile.hideEdgesWhileInteracting)},
            hideEdgesOnZoom: ${JSON.stringify(performanceProfile.hideEdgesWhileInteracting)},
          },
          edges: {
            smooth: ${edgeSmoothing},
            arrows: { to: { enabled: false, scaleFactor: 0 } },
          },
          nodes: {
            shape: 'dot',
            borderWidth: 2,
            borderWidthSelected: 4,
            shadow: { enabled: ${JSON.stringify(!performanceProfile.heavy)}, color: 'rgba(0,0,0,0.55)', size: 10 },
          },
        });

        function shouldShowLabel(node, scaleValue, relatedNodeIds, emphasizedNodeId) {
          if (node.id === emphasizedNodeId) {
            return true;
          }
          if (relatedNodeIds && relatedNodeIds.has(node.id) && scaleValue >= labelBehavior.relatedThreshold) {
            return true;
          }
          if ((node.degree || 0) >= labelBehavior.priorityDegree && scaleValue >= labelBehavior.priorityThreshold) {
            return true;
          }
          return scaleValue >= labelBehavior.globalThreshold;
        }

        function collectRelatedNodes(nodeId) {
          if (!nodeId) {
            return null;
          }
          const relatedNodeIds = new Set(network.getConnectedNodes(nodeId));
          relatedNodeIds.add(nodeId);
          return relatedNodeIds;
        }

        function applyVisualState() {
          const emphasizedNodeId = hoveredNodeId || activeNodeId;
          if (performanceProfile.skipIdleVisualRefresh && !emphasizedNodeId) {
            if (overviewStateDirty) {
              nodes.update(initialNodes);
              edges.update(initialEdges);
              overviewStateDirty = false;
            }
            return;
          }

          overviewStateDirty = true;
          const relatedNodeIds = collectRelatedNodes(emphasizedNodeId);
          const scaleValue = network.getScale();

          initialNodes.forEach(function(baseNode) {
            const isActive = baseNode.id === activeNodeId;
            const isHovered = baseNode.id === hoveredNodeId;
            const isRelated = relatedNodeIds ? relatedNodeIds.has(baseNode.id) : true;
            const isMuted = !isRelated;
            const nodeOpacity = isMuted ? neighborhoodFade.nodeOpacity : 1;
            const fontColor = isMuted
              ? 'rgba(226,232,240,' + neighborhoodFade.fontOpacity + ')'
              : isActive || isHovered
                ? '#f8fafc'
                : '#cbd5e1';
            nodes.update({
              id: baseNode.id,
              label: shouldShowLabel(baseNode, scaleValue, relatedNodeIds, emphasizedNodeId) ? baseNode.fullLabel : '',
              opacity: nodeOpacity,
              borderWidth: isActive ? 5 : isHovered ? 4 : isRelated ? 2.5 : 1,
              font: Object.assign({}, baseNode.font, {
                color: fontColor,
                size: isActive ? 15 : isHovered ? 14 : 13,
              }),
              shadow: isActive
                ? { enabled: true, color: 'rgba(255,255,255,0.45)', size: 32, x: 0, y: 0 }
                : isHovered
                  ? { enabled: true, color: 'rgba(96,165,250,0.32)', size: 24, x: 0, y: 0 }
                  : { enabled: false, color: 'rgba(0,0,0,0.55)', size: 10, x: 0, y: 0 },
            });
          });

          initialEdges.forEach(function(baseEdge) {
            const isRelated = !relatedNodeIds || (relatedNodeIds.has(baseEdge.from) && relatedNodeIds.has(baseEdge.to));
            const isConnectedToActive = activeNodeId && (baseEdge.from === activeNodeId || baseEdge.to === activeNodeId);
            const isConnectedToHovered = hoveredNodeId && (baseEdge.from === hoveredNodeId || baseEdge.to === hoveredNodeId);
            edges.update({
              id: baseEdge.id,
              hidden: false,
              color: isConnectedToActive || isConnectedToHovered
                ? { color: 'rgba(248,250,252,0.82)', highlight: '#ffffff', hover: '#ffffff', inherit: false }
                : isRelated
                  ? { color: 'rgba(148,163,184,0.36)', highlight: '#f8fafc', hover: '#f8fafc', inherit: false }
                  : { color: 'rgba(71,85,105,' + neighborhoodFade.edgeOpacity + ')', highlight: 'rgba(71,85,105,' + neighborhoodFade.edgeOpacity + ')', hover: 'rgba(71,85,105,' + neighborhoodFade.edgeOpacity + ')', inherit: false },
              width: isConnectedToActive ? 2.2 : isConnectedToHovered ? 1.8 : isRelated ? 1 : neighborhoodFade.edgeWidth,
            });
          });
        }

        function applyNeighborhoodFocus(nodeId) {
          if (!nodeId) {
            activeNodeId = null;
            applyVisualState();
            return;
          }
          activeNodeId = nodeId;
          applyVisualState();
          network.selectNodes([nodeId]);
          network.focus(nodeId, {
            scale: Math.max(1.1, preferredScale),
            locked: false,
            animation: {
              duration: 420,
              easingFunction: 'easeInOutQuad',
            },
          });
        }

        function fitOverview() {
          var animation = performanceProfile.enableAnimatedFit
            ? { duration: 250, easingFunction: 'easeInOutQuad' }
            : false;
          var baseFitOptions = {
            animation: false,
            nodes: initialNodes.map(function(node) { return node.id; }),
          };

          try {
            network.fit(baseFitOptions);
            var fittedScale = network.getScale();
            var viewPosition = network.getViewPosition();
            var targetScale = Math.min(2.2, fittedScale * preferredScale);
            network.moveTo({
              position: viewPosition,
              scale: targetScale,
              animation: animation,
            });
          } catch (error) {
            network.fit(baseFitOptions);
          }
        }

        network.on('click', function(params) {
          if (!params.nodes || !params.nodes.length) {
            hoveredNodeId = null;
            applyNeighborhoodFocus(null);
            fitOverview();
            return;
          }
          const nodeId = params.nodes[0];
          applyNeighborhoodFocus(nodeId);
          const payload = JSON.stringify({ frameId: frameId, type: 'nodePress', nodeId: nodeId });
          if (window.ReactNativeWebView && typeof window.ReactNativeWebView.postMessage === 'function') {
            window.ReactNativeWebView.postMessage(payload);
          } else if (window.parent && window.parent !== window) {
            window.parent.postMessage({ frameId: frameId, type: 'nodePress', nodeId: nodeId }, '*');
          }
        });

        network.on('doubleClick', function(params) {
          if (!params.nodes || !params.nodes.length) {
            return;
          }
          const nodeId = params.nodes[0];
          applyNeighborhoodFocus(nodeId);
          const payload = JSON.stringify({ frameId: frameId, type: 'nodeOpen', nodeId: nodeId });
          if (window.ReactNativeWebView && typeof window.ReactNativeWebView.postMessage === 'function') {
            window.ReactNativeWebView.postMessage(payload);
          } else if (window.parent && window.parent !== window) {
            window.parent.postMessage({ frameId: frameId, type: 'nodeOpen', nodeId: nodeId }, '*');
          }
        });

        if (${JSON.stringify(hoverEnabled)}) {
          network.on('hoverNode', function(params) {
            hoveredNodeId = params.node;
            if (performanceProfile.enableHover) {
              applyVisualState();
            }
          });

          network.on('blurNode', function() {
            hoveredNodeId = null;
            if (performanceProfile.enableHover) {
              applyVisualState();
            }
          });
        }

        network.on('zoom', function() {
          if (performanceProfile.skipIdleVisualRefresh && !activeNodeId && !hoveredNodeId) {
            return;
          }
          applyVisualState();
          setTimeout(function() { network.redraw(); }, 80);
        });

        network.once('stabilizationIterationsDone', function() {
          if (performanceProfile.disablePhysicsAfterStabilization) {
            network.setOptions({ physics: false });
          }
          fitOverview();
          applyVisualState();
          if (focusedNodeId) {
            setTimeout(function() {
              applyNeighborhoodFocus(focusedNodeId);
            }, 120);
          }
        });

        window.addEventListener('resize', function() {
          if (activeNodeId || hoveredNodeId) {
            return;
          }
          fitOverview();
        });
      })();
    </script>
  </body>
</html>`;
}

function buildNodeTooltipHtml(node: GraphData['nodes'][number]) {
  const date = node.dateModified ? String(node.dateModified).slice(0, 10) : 'date inconnue';
  const tags = node.tags.length ? `🏷 ${node.tags.slice(0, 5).map((tag) => `#${tag}`).join(' · ')}` : '';
  return `<div><strong>${escapeHtml(node.label)}</strong><br/>📅 ${escapeHtml(date)}${tags ? `<br/>${escapeHtml(tags)}` : ''}</div>`;
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
function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function safeParseGraphMessage(raw: unknown) {
  if (typeof raw !== 'string') {
    return raw as { frameId?: string; type?: string; nodeId?: string } | null;
  }

  try {
    return JSON.parse(raw) as { frameId?: string; type?: string; nodeId?: string };
  } catch {
    return null;
  }
}