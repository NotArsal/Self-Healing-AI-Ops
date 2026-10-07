import React, { useMemo } from "react";

interface ServiceDef {
  role: string;
  depends_on?: string[];
}

interface TopologyGraphProps {
  services?: Record<string, ServiceDef>;
}

interface NodeData {
  id: string;
  role: string;
  depends_on: string[];
  layer: number;
  x: number;
  y: number;
}

export function TopologyGraph({ services }: TopologyGraphProps) {
  const { nodes, edges, width, height } = useMemo(() => {
    if (!services || Object.keys(services).length === 0) {
      return { nodes: [], edges: [], width: 0, height: 0 };
    }

    // 1. Calculate layers
    const layerMap = new Map<string, number>();
    const getLayer = (id: string, visited = new Set<string>()): number => {
      if (layerMap.has(id)) return layerMap.get(id)!;
      if (visited.has(id)) return 0; // Handle cycle fallback gracefully
      visited.add(id);

      const srv = services[id];
      if (!srv || !srv.depends_on || srv.depends_on.length === 0) {
        layerMap.set(id, 0);
        return 0;
      }

      let maxDepLayer = 0;
      for (const dep of srv.depends_on) {
        const depLayer = getLayer(dep, visited);
        if (depLayer > maxDepLayer) maxDepLayer = depLayer;
      }

      const layer = maxDepLayer + 1;
      layerMap.set(id, layer);
      return layer;
    };

    const nodeIds = Object.keys(services);
    nodeIds.forEach((id) => getLayer(id));

    // Group by layer
    const byLayer: Record<number, string[]> = {};
    let maxLayer = 0;
    for (const [id, layer] of layerMap.entries()) {
      if (!byLayer[layer]) byLayer[layer] = [];
      byLayer[layer].push(id);
      if (layer > maxLayer) maxLayer = layer;
    }

    // 2. Assign coordinates
    const NODE_WIDTH = 120;
    const NODE_HEIGHT = 40;
    const LAYER_SPACING = 180;
    const NODE_SPACING = 80;
    
    // We want the graph to flow left-to-right or top-to-bottom.
    // Let's do left-to-right. Layer 0 (no dependencies) on the right?
    // Wait, if A depends on B, layer(A) > layer(B).
    // So layer 0 (B) is on the right, layer 1 (A) is on the left.
    // Traffic flows left to right (A -> B).
    // So X = (maxLayer - layer) * LAYER_SPACING + 20
    
    const nodeCoords = new Map<string, NodeData>();
    let maxHeight = 0;

    for (let l = 0; l <= maxLayer; l++) {
      const layerNodes = byLayer[l] || [];
      const totalInLayer = layerNodes.length;
      const startY = 40; // top padding
      
      const layerHeight = startY + totalInLayer * NODE_SPACING;
      if (layerHeight > maxHeight) maxHeight = layerHeight;

      layerNodes.forEach((id, idx) => {
        // Center nodes vertically if a layer has fewer nodes
        const yOffset = startY + idx * NODE_SPACING;
        const xOffset = 20 + (maxLayer - l) * LAYER_SPACING;
        
        nodeCoords.set(id, {
          id,
          role: services[id].role,
          depends_on: services[id].depends_on || [],
          layer: l,
          x: xOffset,
          y: yOffset,
        });
      });
    }

    const finalWidth = maxLayer * LAYER_SPACING + NODE_WIDTH + 40;
    const finalHeight = maxHeight;

    // 3. Build edges
    const generatedEdges: { id: string; x1: number; y1: number; x2: number; y2: number }[] = [];
    nodeCoords.forEach((node) => {
      node.depends_on.forEach((depId) => {
        const depNode = nodeCoords.get(depId);
        if (depNode) {
          generatedEdges.push({
            id: `${node.id}->${depId}`,
            // Arrow goes from right side of node to left side of depNode
            x1: node.x + NODE_WIDTH,
            y1: node.y + NODE_HEIGHT / 2,
            x2: depNode.x,
            y2: depNode.y + NODE_HEIGHT / 2,
          });
        }
      });
    });

    return {
      nodes: Array.from(nodeCoords.values()),
      edges: generatedEdges,
      width: finalWidth,
      height: finalHeight,
    };
  }, [services]);

  if (!services || Object.keys(services).length === 0) {
    return null;
  }

  return (
    <div className="bg-k-surface rounded border border-k-hairline p-5 shadow-sm mt-4">
      <h3 className="font-semibold mb-4 text-[11px] uppercase tracking-wider text-k-muted border-b border-k-hairline pb-2">
        Service Topology
      </h3>
      <div className="overflow-x-auto">
        <svg width={width} height={height} className="min-w-full">
          <defs>
            <marker
              id="arrowhead"
              markerWidth="8"
              markerHeight="6"
              refX="8"
              refY="3"
              orient="auto"
            >
              <polygon points="0 0, 8 3, 0 6" fill="var(--color-k-hairline-strong)" />
            </marker>
          </defs>
          
          {/* Edges */}
          {edges.map((edge) => {
            // A simple bezier curve for visual appeal
            const dx = Math.abs(edge.x2 - edge.x1);
            const pathData = `M ${edge.x1} ${edge.y1} C ${edge.x1 + dx/2} ${edge.y1}, ${edge.x2 - dx/2} ${edge.y2}, ${edge.x2} ${edge.y2}`;
            
            return (
              <path
                key={edge.id}
                d={pathData}
                fill="none"
                stroke="var(--color-k-hairline-strong)"
                strokeWidth="2"
                markerEnd="url(#arrowhead)"
              />
            );
          })}
          
          {/* Nodes */}
          {nodes.map((node) => (
            <g key={node.id} transform={`translate(${node.x}, ${node.y})`}>
              <rect
                width={120}
                height={40}
                rx={6}
                className="fill-k-canvas stroke-k-hairline"
                strokeWidth={1}
              />
              <text
                x={60}
                y={18}
                textAnchor="middle"
                className="fill-k-ink text-xs font-medium font-sans"
              >
                {node.id}
              </text>
              <text
                x={60}
                y={32}
                textAnchor="middle"
                className="fill-k-muted text-[9px] uppercase tracking-wider font-sans"
              >
                {node.role}
              </text>
            </g>
          ))}
        </svg>
      </div>
    </div>
  );
}
