"""Wire the RelayG state machine: classify -> policy_check -> act."""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from .nodes import act, classify, policy_check
from .state import TicketState


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Build and compile the triage graph.

    Pass a checkpointer (e.g. SqliteSaver) to enable durable interrupt and
    resume for human-in-the-loop refund approvals.
    """
    builder = StateGraph(TicketState)
    builder.add_node("classify", classify)
    builder.add_node("policy_check", policy_check)
    builder.add_node("act", act)

    builder.add_edge(START, "classify")
    builder.add_edge("classify", "policy_check")
    builder.add_edge("policy_check", "act")
    builder.add_edge("act", END)

    return builder.compile(checkpointer=checkpointer)
