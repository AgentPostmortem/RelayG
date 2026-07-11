"""CLI demo: run 5 sample tickets through the graph with a step trace.

Usage: python -m relayg.demo
Works with no API key (mock classifier). Writes actions to audit.jsonl.
"""

from __future__ import annotations

import os
import sqlite3

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from .graph import build_graph

SAMPLE_TICKETS = [
    {
        "ticket_id": "T-1001",
        "subject": "Refund for duplicate charge",
        "body": "I was charged twice, please refund $25 for the duplicate charge.",
    },
    {
        "ticket_id": "T-1002",
        "subject": "Refund request",
        "body": "The product broke after a week. I want a refund of $120.",
    },
    {
        "ticket_id": "T-1003",
        "subject": "Urgent refund needed",
        "body": "This is urgent, I need my money back immediately, a refund of $450.",
    },
    {
        "ticket_id": "T-1004",
        "subject": "How do I reset my password?",
        "body": "Where can I find the password reset option?",
    },
    {
        "ticket_id": "T-1005",
        "subject": "Refund for wrong size",
        "body": "Ordered the wrong size, please refund $75 and I will reorder.",
    },
]

# Simulated reviewer verdicts for tickets that hit the human approval gate.
REVIEWER_VERDICTS = {
    "T-1002": {"approved": True, "approver": "demo-reviewer", "note": "Verified purchase, within policy."},
    "T-1005": {"approved": False, "approver": "demo-reviewer", "note": "Exchange offered instead of refund."},
}


def run_demo() -> None:
    mode = "GROQ (llama-3.3-70b-versatile)" if os.environ.get("GROQ_API_KEY") else "MOCK (no GROQ_API_KEY set)"
    print(f"RelayG demo | classifier: {mode}")
    print("=" * 72)

    conn = sqlite3.connect("relayg_checkpoints.sqlite", check_same_thread=False)
    serde = JsonPlusSerializer(allowed_msgpack_modules=[("relayg.state", "Classification")])
    checkpointer = SqliteSaver(conn, serde=serde)
    graph = build_graph(checkpointer)

    for ticket in SAMPLE_TICKETS:
        config = {"configurable": {"thread_id": ticket["ticket_id"]}}
        print(f"\n--- {ticket['ticket_id']}: {ticket['subject']}")
        result = graph.invoke(ticket, config)

        c = result["classification"]
        print(f"  classify     -> intent={c.intent} urgency={c.urgency} refund_amount={c.refund_amount}")
        print(f"  policy_check -> {result['policy_decision']}: {result['policy_reason']}")

        if "__interrupt__" in result:
            payload = result["__interrupt__"][0].value
            print(f"  INTERRUPT    -> graph paused, awaiting human: {payload['question']}")
            verdict = REVIEWER_VERDICTS[ticket["ticket_id"]]
            print(f"  resume       -> reviewer says approved={verdict['approved']} ({verdict['note']})")
            result = graph.invoke(Command(resume=verdict), config)

        for action in result.get("actions", []):
            detail = {k: v for k, v in action.items() if k not in ("ts", "action", "ticket_id")}
            print(f"  act          -> {action['action']} {detail}")

    conn.close()
    print("\n" + "=" * 72)
    print("Done. Actions were appended to audit.jsonl; checkpoints in relayg_checkpoints.sqlite.")


if __name__ == "__main__":
    run_demo()
