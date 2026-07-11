import pytest


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Force mock mode and redirect the audit log to a temp file."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("RELAYG_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
