import json
import os
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from relayg.graph import build_graph
from relayg.nodes import mock_classify


def _saver() -> SqliteSaver:
    return SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False))


def test_mock_classifier_extracts_amount() -> None:
    c = mock_classify("Refund", "Please refund $25 for the duplicate charge.")
    assert c.intent == "refund_request"
    assert c.refund_amount == 25.0


def test_small_refund_auto_approved_end_to_end() -> None:
    graph = build_graph(_saver())
    config = {"configurable": {"thread_id": "t1"}}
    result = graph.invoke(
        {"ticket_id": "t1", "subject": "Refund", "body": "Please refund $20."},
        config,
    )
    assert result["policy_decision"] == "auto_approve"
    actions = [a["action"] for a in result["actions"]]
    assert actions == ["issue_refund", "send_reply"]


def test_question_gets_reply_only() -> None:
    graph = build_graph(_saver())
    config = {"configurable": {"thread_id": "t2"}}
    result = graph.invoke(
        {"ticket_id": "t2", "subject": "Help", "body": "How do I reset my password?"},
        config,
    )
    assert result["policy_decision"] == "no_refund"
    assert [a["action"] for a in result["actions"]] == ["send_reply"]


def test_missing_subject_and_body_classifies_as_other() -> None:
    graph = build_graph(_saver())
    config = {"configurable": {"thread_id": "missing-fields"}}
    result = graph.invoke({"ticket_id": "missing-fields"}, config)

    assert result["classification"].intent == "other"
    assert result["policy_decision"] == "no_refund"


def test_large_refund_escalates() -> None:
    graph = build_graph(_saver())
    config = {"configurable": {"thread_id": "t3"}}
    result = graph.invoke(
        {"ticket_id": "t3", "subject": "Refund", "body": "I want a refund of $450."},
        config,
    )
    assert result["policy_decision"] == "escalate"
    assert [a["action"] for a in result["actions"]] == ["escalate", "send_reply"]


def test_mid_refund_interrupts_then_resumes_approved() -> None:
    graph = build_graph(_saver())
    config = {"configurable": {"thread_id": "t4"}}
    result = graph.invoke(
        {"ticket_id": "t4", "subject": "Refund", "body": "Please refund $120."},
        config,
    )
    # Graph paused at the human approval gate; no actions taken yet.
    assert result["policy_decision"] == "needs_approval"
    assert "__interrupt__" in result
    assert "actions" not in result or result["actions"] == []
    assert "$120.00" in result["__interrupt__"][0].value["question"]

    resumed = graph.invoke(Command(resume={"approved": True, "approver": "qa"}), config)
    assert resumed["approved"] is True
    actions = [a["action"] for a in resumed["actions"]]
    assert actions == ["issue_refund", "send_reply"]
    refund = next(a for a in resumed["actions"] if a["action"] == "issue_refund")
    assert refund["amount"] == 120.0
    assert refund["approved_by"] == "qa"


def test_mid_refund_denied_sends_decline_reply() -> None:
    graph = build_graph(_saver())
    config = {"configurable": {"thread_id": "t5"}}
    graph.invoke(
        {"ticket_id": "t5", "subject": "Refund", "body": "Refund $75 please."},
        config,
    )
    resumed = graph.invoke(Command(resume={"approved": False, "note": "Out of window."}), config)
    assert resumed["approved"] is False
    assert [a["action"] for a in resumed["actions"]] == ["send_reply"]
    assert "declined" in resumed["actions"][0]["message"]


def test_mid_refund_malformed_verdict_fails_closed() -> None:
    verdict = "yes"
    graph = build_graph(_saver())
    config = {"configurable": {"thread_id": "malformed-verdict"}}
    graph.invoke(
        {"ticket_id": "malformed-verdict", "subject": "Refund", "body": "Refund $75 please."},
        config,
    )

    resumed = graph.invoke(Command(resume=verdict), config)

    assert resumed["approved"] is False
    assert [a["action"] for a in resumed["actions"]] == ["send_reply"]
    assert "declined" in resumed["actions"][0]["message"]


def test_actions_are_written_to_audit_log() -> None:
    graph = build_graph(_saver())
    config = {"configurable": {"thread_id": "t6"}}
    graph.invoke(
        {"ticket_id": "t6", "subject": "Refund", "body": "Refund $10 please."},
        config,
    )
    path = os.environ["RELAYG_AUDIT_PATH"]
    entries = [json.loads(line) for line in open(path, encoding="utf-8")]
    assert any(e["action"] == "issue_refund" and e["ticket_id"] == "t6" for e in entries)
