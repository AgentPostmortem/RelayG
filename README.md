# RelayG

A support ticket triage agent built as a LangGraph state machine. It classifies incoming tickets with an LLM, applies pure Python refund policy rules, and takes mock actions with a full audit trail. Refunds between $50 and $200 pause the graph with a human-in-the-loop interrupt and resume only after a reviewer approves or denies, with state persisted by a SQLite checkpointer.

RelayG is a code-first rebuild of [Resolvd](https://resolvd.agentpostmortem.com), a production triage agent originally built on n8n and Claude. Same triage logic, different substrate, built to show what a code-first agent framework adds over a visual workflow tool.

## Architecture

```
                +-----------+     +--------------+     +---------+
  ticket -----> | classify  | --> | policy_check | --> |   act   | --> END
                | (LLM or   |     | (pure Python |     | (tools) |
                |  mock)    |     |  rules)      |     +----+----+
                +-----------+     +--------------+          |
                                                            | refund $50-$200
                                                            v
                                                   [ interrupt() ]
                                                   graph pauses, state
                                                   checkpointed (SQLite)
                                                            |
                                          human resumes with Command(resume=...)
                                                            |
                                                            v
                                              issue_refund / decline reply
```

Policy rules (in `relayg/policy.py`, no LLM involved):

| Refund amount | Decision |
| --- | --- |
| not a refund request | reply normally |
| under $50 | auto-approve and issue |
| $50 to $200 | pause for human approval |
| over $200 | escalate to a senior agent |

Every action (`send_reply`, `issue_refund`, `escalate`) is a mock tool that appends to `audit.jsonl`.

## Why LangGraph instead of a workflow tool

Visual workflow tools like n8n are excellent for wiring integrations quickly, and Resolvd runs fine on one. What they make awkward is exactly what this project showcases: typed state that flows through every node and is checked at development time rather than discovered at runtime, durable checkpointing so a paused run survives a process restart, and first-class interrupts where `interrupt()` suspends mid-node and `Command(resume=...)` continues from the same checkpoint with the human verdict injected. In a workflow tool you approximate this with webhooks, wait nodes, and state stuffed into a database by hand; in LangGraph it is the core execution model, plus the whole graph is plain Python you can unit test (this repo's interrupt and resume path is covered by pytest). The tradeoff is honest: you give up the visual editor and drag-and-drop integrations and take on code ownership.

## Quickstart

Requires Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# optional: real LLM classification via Groq free tier
export GROQ_API_KEY=your_key   # omit to run in deterministic MOCK mode

python -m relayg.demo   # runs 5 sample tickets with a step trace
pytest                  # policy rules, graph wiring, interrupt/resume
```

Without `GROQ_API_KEY` the classifier is a deterministic mock, so the demo and tests work offline with no key. With a key set, classification uses `langchain-groq` (`llama-3.3-70b-versatile`) with pydantic structured output.

## Layout

```
relayg/
  state.py    typed graph state and the Classification schema
  policy.py   pure refund policy rules
  nodes.py    classify, policy_check, act (with the interrupt)
  tools.py    mock actions plus the JSONL audit log
  graph.py    StateGraph wiring
  demo.py     CLI demo
tests/        pytest suite
```

## Relation to Resolvd

Resolvd (https://resolvd.agentpostmortem.com) is the original production triage agent, built on n8n with Claude doing classification. RelayG reimplements its triage flow on LangGraph to compare the two approaches directly: identical policy semantics, but with typed state, checkpointed execution, and a real human-in-the-loop interrupt instead of webhook-and-wait plumbing.
