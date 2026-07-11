"""Graph nodes: classify, policy_check, act.

The classifier uses Groq (llama-3.3-70b-versatile) with pydantic structured
output when GROQ_API_KEY is set, and a deterministic mock otherwise so the
demo and tests run without any key.
"""

from __future__ import annotations

import os
import re
from typing import Callable

from langgraph.types import interrupt

from . import tools
from .policy import decide
from .state import Classification, TicketState

Classifier = Callable[[str, str], Classification]

_AMOUNT_RE = re.compile(r"\$\s*([0-9]+(?:\.[0-9]{1,2})?)")


def mock_classify(subject: str, body: str) -> Classification:
    """Deterministic keyword classifier used when no GROQ_API_KEY is set."""
    text = f"{subject} {body}".lower()
    amount_match = _AMOUNT_RE.search(f"{subject} {body}")
    amount = float(amount_match.group(1)) if amount_match else None

    if "refund" in text or "money back" in text or "charge" in text:
        intent: str = "refund_request"
    elif "bug" in text or "error" in text or "crash" in text:
        intent = "bug_report"
    elif "angry" in text or "unacceptable" in text or "terrible" in text:
        intent = "complaint"
    elif "?" in body or "how" in text or "where" in text:
        intent = "question"
    else:
        intent = "other"

    if "urgent" in text or "asap" in text or "immediately" in text:
        urgency: str = "high"
    elif intent in ("complaint", "refund_request"):
        urgency = "medium"
    else:
        urgency = "low"

    refund_amount = amount if intent == "refund_request" else None
    return Classification(intent=intent, urgency=urgency, refund_amount=refund_amount)


def _groq_classify(subject: str, body: str) -> Classification:
    from langchain_groq import ChatGroq

    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
    structured = llm.with_structured_output(Classification)
    prompt = (
        "You are a support ticket triage classifier. Classify this ticket.\n"
        "Extract the refund amount in USD only if the customer explicitly asks "
        "for a refund; otherwise leave it null.\n\n"
        f"Subject: {subject}\n\nBody: {body}"
    )
    result = structured.invoke(prompt)
    assert isinstance(result, Classification)
    return result


def get_classifier() -> Classifier:
    """Return the Groq classifier if a key is configured, else the mock."""
    if os.environ.get("GROQ_API_KEY"):
        return _groq_classify
    return mock_classify


def classify(state: TicketState) -> dict:
    """Node: classify intent, urgency, and any requested refund amount."""
    classifier = get_classifier()
    classification = classifier(state["subject"], state["body"])
    return {"classification": classification}


def policy_check(state: TicketState) -> dict:
    """Node: apply pure Python refund policy rules."""
    decision, reason = decide(state["classification"])
    return {"policy_decision": decision, "policy_reason": reason}


def act(state: TicketState) -> dict:
    """Node: take the action the policy allows.

    For refunds over $50 that need human approval, this node pauses the
    graph with interrupt(). The checkpointer persists the state; the run
    resumes when a human replies with Command(resume={...}).
    """
    ticket_id = state["ticket_id"]
    decision = state["policy_decision"]
    classification = state["classification"]
    actions: list[dict] = []
    update: dict = {}

    if decision == "no_refund":
        actions.append(tools.send_reply(ticket_id, "Thanks for reaching out. A support agent has replied to your ticket."))
    elif decision == "auto_approve":
        amount = classification.refund_amount or 0.0
        actions.append(tools.issue_refund(ticket_id, amount, approved_by="policy:auto"))
        actions.append(tools.send_reply(ticket_id, f"Your refund of ${amount:.2f} has been issued automatically."))
    elif decision == "needs_approval":
        amount = classification.refund_amount or 0.0
        # Human in the loop: pause here until a reviewer approves or denies.
        verdict = interrupt(
            {
                "ticket_id": ticket_id,
                "question": f"Approve refund of ${amount:.2f}?",
                "reason": state["policy_reason"],
            }
        )
        approved = bool(verdict.get("approved"))
        note = str(verdict.get("note", ""))
        update["approved"] = approved
        update["approver_note"] = note
        if approved:
            actions.append(tools.issue_refund(ticket_id, amount, approved_by=verdict.get("approver", "human")))
            actions.append(tools.send_reply(ticket_id, f"Your refund of ${amount:.2f} was approved and issued."))
        else:
            actions.append(tools.send_reply(ticket_id, f"Your refund request for ${amount:.2f} was reviewed and declined. {note}".strip()))
    else:  # escalate
        actions.append(tools.escalate(ticket_id, state["policy_reason"]))
        actions.append(tools.send_reply(ticket_id, "Your request has been escalated to a senior agent."))

    update["actions"] = actions
    return update
