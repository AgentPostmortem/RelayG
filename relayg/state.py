"""Typed state shared by every node in the RelayG graph."""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field

Intent = Literal["refund_request", "question", "complaint", "bug_report", "other"]
Urgency = Literal["low", "medium", "high"]
PolicyDecision = Literal["auto_approve", "needs_approval", "escalate", "no_refund"]


class Classification(BaseModel):
    """Structured output produced by the classifier (LLM or mock)."""

    intent: Intent = Field(description="The customer's primary intent.")
    urgency: Urgency = Field(description="How urgent the ticket is.")
    refund_amount: float | None = Field(
        default=None,
        description="Refund amount in USD if the customer asks for one, else null.",
    )


class TicketState(TypedDict, total=False):
    """State carried through the graph for a single ticket."""

    ticket_id: str
    subject: str
    body: str
    classification: Classification
    policy_decision: PolicyDecision
    policy_reason: str
    approved: bool
    approver_note: str
    actions: Annotated[list[dict], operator.add]
