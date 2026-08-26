"""Flow block — Vue Flow node/edge graph example.

GET /api/flow/sample  returns a small directed graph (4 nodes, 3 edges).

Node positions (x/y) are baked in so no layout library is needed for the
hello-world.  To auto-layout large graphs, compute positions on the frontend
with @dagrejs/dagre — keep the backend model position-free in that case.

This route is intentionally **self-contained** (no DSS) so the block renders
with zero configuration.  To make it real, replace the static graph with e.g.
a DSS project's flow (project.get_flow() via the Python API) or any domain
graph structure you want to visualise.

Optional block — registered only when ENABLE_FLOW=1 (see backend/app.py).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/flow")


class FlowNode(BaseModel):
    id: str
    label: str
    node_type: str
    x: float
    y: float


class FlowEdge(BaseModel):
    id: str
    source: str
    target: str


class FlowSample(BaseModel):
    nodes: list[FlowNode]
    edges: list[FlowEdge]


@router.get("/sample", response_model=FlowSample)
def sample_flow() -> FlowSample:
    """Return a sample pipeline graph for the Flow view.

    This represents four stages: Raw Data → Process → Enrich → Output.
    Replace with your domain graph (DSS project flow, dependency tree, etc.).
    """
    return FlowSample(
        nodes=[
            FlowNode(id="1", label="Raw Data", node_type="source",    x=50,  y=120),
            FlowNode(id="2", label="Process",  node_type="transform", x=250, y=120),
            FlowNode(id="3", label="Enrich",   node_type="enrich",    x=450, y=120),
            FlowNode(id="4", label="Output",   node_type="output",    x=650, y=120),
        ],
        edges=[
            FlowEdge(id="e1-2", source="1", target="2"),
            FlowEdge(id="e2-3", source="2", target="3"),
            FlowEdge(id="e3-4", source="3", target="4"),
        ],
    )
