import os
import pytest

@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Enable mock flags by default during testing for deterministic offline runs."""
    monkeypatch.setenv("DEVSNAP_MOCK_AGE", "1")
    monkeypatch.setenv("DEVSNAP_MOCK_TUNNEL", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "TestUser")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "TestUser")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")
