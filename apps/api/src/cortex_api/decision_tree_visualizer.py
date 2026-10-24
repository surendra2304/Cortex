"""
Cortex/apps/api/src/cortex_api/decision_tree_visualizer.py — Cortex Decision Tree Visualizer.

Decision tree generation, visualization data, branch analysis,
and decision path exploration.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()


@dataclass
class TreeNode:
    """A node in a decision tree."""
    node_id: str
    label: str
    node_type: str = "decision"  # decision, chance, end, action
    children: list[str] = field(default_factory=list)
    probabilities: dict[str, float] = field(default_factory=dict)
    expected_value: float = 0.0
    depth: int = 0


@dataclass
class DecisionTree:
    """A decision tree."""
    tree_id: str
    name: str
    root: str = ""
    nodes: dict[str, TreeNode] = field(default_factory=dict)
    description: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class TreeAnalysis:
    """Analysis of a decision tree."""
    analysis_id: str
    tree_id: str
    total_nodes: int = 0
    total_leaves: int = 0
    max_depth: int = 0
    expected_value: float = 0.0
    best_path: list[str] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)


class DecisionTreeVisualizer:
    """Engine for decision tree visualization and analysis."""

    def __init__(self) -> None:
        self._trees: dict[str, DecisionTree] = {}
        self._analyses: list[TreeAnalysis] = []

    def create_tree(self, name: str, description: str = "") -> DecisionTree:
        """Create a new decision tree."""
        tree_id = f"tree_{uuid.uuid4().hex[:12]}"
        tree = DecisionTree(tree_id=tree_id, name=name, description=description)
        root_id = f"n_{uuid.uuid4().hex[:8]}"
        root = TreeNode(node_id=root_id, label=name, depth=0)
        tree.nodes[root_id] = root
        tree.root = root_id
        self._trees[tree_id] = tree
        return tree

    def add_node(self, tree_id: str, parent_id: str, label: str,
                 node_type: str = "decision",
                 probabilities: dict[str, float] | None = None) -> TreeNode:
        """Add a node to a tree."""
        tree = self._trees.get(tree_id)
        if not tree:
            raise HTTPException(status_code=404, detail="Tree not found")
        parent = tree.nodes.get(parent_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent node not found")

        node_id = f"n_{uuid.uuid4().hex[:8]}"
        node = TreeNode(
            node_id=node_id, label=label, node_type=node_type,
            depth=parent.depth + 1, probabilities=probabilities or {},
        )
        tree.nodes[node_id] = node
        parent.children.append(node_id)
        return node

    def analyze_tree(self, tree_id: str) -> TreeAnalysis:
        """Analyze a decision tree."""
        tree = self._trees.get(tree_id)
        if not tree:
            raise HTTPException(status_code=404, detail="Tree not found")

        analysis_id = f"ana_{uuid.uuid4().hex[:12]}"
        analysis = TreeAnalysis(analysis_id=analysis_id, tree_id=tree_id)
        analysis.total_nodes = len(tree.nodes)
        analysis.max_depth = max(n.depth for n in tree.nodes.values())

        # Count leaves (nodes with no children)
        analysis.total_leaves = sum(1 for n in tree.nodes.values() if not n.children)

        # Calculate expected values (bottom-up)
        for node in sorted(tree.nodes.values(), key=lambda n: -n.depth):
            if not node.children:
                node.expected_value = node.probabilities.get("value", 0.0)
            else:
                total_prob = sum(node.probabilities.values())
                if total_prob > 0:
                    node.expected_value = sum(
                        tree.nodes[c].expected_value * node.probabilities.get(c, 0) / total_prob
                        for c in node.children
                    )

        analysis.expected_value = tree.nodes[tree.root].expected_value

        # Find best path
        current = tree.root
        analysis.best_path = []
        while current:
            analysis.best_path.append(tree.nodes[current].label)
            node = tree.nodes[current]
            if not node.children:
                break
            best_child = max(node.children, key=lambda c: tree.nodes[c].expected_value)
            current = best_child

        analysis.insights = [
            f"Tree has {analysis.total_nodes} nodes and {analysis.total_leaves} leaves",
            f"Maximum depth: {analysis.max_depth}",
            f"Expected value: {analysis.expected_value:.2f}",
            f"Best path: {' -> '.join(analysis.best_path[:3])}",
        ]

        self._analyses.append(analysis)
        return analysis

    def get_tree(self, tree_id: str) -> dict[str, Any]:
        """Get a decision tree."""
        tree = self._trees.get(tree_id)
        if not tree:
            raise HTTPException(status_code=404, detail="Tree not found")
        return {
            "tree_id": tree.tree_id, "name": tree.name,
            "node_count": len(tree.nodes),
            "nodes": [
                {"label": n.label, "type": n.node_type, "depth": n.depth,
                 "children": len(n.children)}
                for n in tree.nodes.values()[:10]
            ],
        }

    def get_report(self) -> dict[str, Any]:
        """Get engine report."""
        return {
            "total_trees": len(self._trees),
            "total_analyses": len(self._analyses),
            "engine_status": "operational",
        }


engine = DecisionTreeVisualizer()


@router.post("/cortex/trees/create")
async def create_tree(name: str, description: str = ""):
    """Create a decision tree."""
    tree = engine.create_tree(name, description)
    return {"tree_id": tree.tree_id, "name": tree.name}


@router.post("/cortex/trees/{tree_id}/nodes")
async def add_node(tree_id: str, parent_id: str, label: str, node_type: str = "decision",
                   probabilities: dict[str, float] | None = None):
    """Add a node to a tree."""
    node = engine.add_node(tree_id, parent_id, label, node_type, probabilities)
    return {"node_id": node.node_id, "label": node.label, "depth": node.depth}


@router.post("/cortex/trees/{tree_id}/analyze")
async def analyze_tree(tree_id: str):
    """Analyze a decision tree."""
    analysis = engine.analyze_tree(tree_id)
    return {
        "analysis_id": analysis.analysis_id,
        "total_nodes": analysis.total_nodes,
        "expected_value": analysis.expected_value,
        "best_path": analysis.best_path,
        "insights": analysis.insights,
    }


@router.get("/cortex/trees/{tree_id}")
async def get_tree(tree_id: str):
    """Get a decision tree."""
    return engine.get_tree(tree_id)


@router.get("/cortex/trees/report")
async def tree_report():
    """Get decision tree visualizer report."""
    return engine.get_report()
