// Types for the Flow building block — mirrors backend/routes/flow.py models.

export interface FlowNode {
  id: string
  label: string
  node_type: string
  x: number
  y: number
}

export interface FlowEdge {
  id: string
  source: string
  target: string
}

export interface FlowSample {
  nodes: FlowNode[]
  edges: FlowEdge[]
}
