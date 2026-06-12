import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml


@pytest.fixture
def temp_config_dir(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    test_config = {
        "user": {"name": "Test User", "email": "test@example.com"},
        "profile": {"name": "Test User", "affiliation": "", "interests": [], "recent_papers": [], "scholar_url": ""},
        "interests": {
            "keywords_include": ["large language model", "agent"],
            "keywords_exclude": ["survey"],
            "categories": ["cs.AI", "cs.CL"],
        },
        "notification": {
            "email": {"enabled": True, "smtp_host": "smtp.gmail.com", "smtp_port": 587, "timeout": 15},
        },
        "daily": {
            "max_papers": 10,
            "min_relevance_score": 7,
            "lookback_days": 1,
            "keyword_prefilter_top": 60,
            "title_score_top": 25,
        },
        "llm": {
            "api_key_env": "OPENAI_API_KEY",
            "base_url": "https://api.deepseek.com",
            "fast_model": "deepseek-v4-flash",
            "pro_model": "deepseek-v4-pro",
        },
        "arxiv": {"page_size": 100, "delay_seconds": 10.0, "num_retries": 2, "trust_env": False},
        "external": {"semantic_scholar_timeout": 15, "user_agent": "DailyPapers/1.0"},
        "keyword_prefilter": {"title_exact_weight": 3, "title_partial_weight": 2, "abstract_weight": 1},
        "report": {"score_green": 8, "score_orange": 5},
        "paths": {"seen_papers": "seen_papers.json", "cache_dir": ".cache"},
    }
    with open(config_path, "w") as f:
        yaml.dump(test_config, f)

    import src.config
    monkeypatch.setattr(src.config, "_ROOT", tmp_path)
    monkeypatch.setattr(src.config, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(src.config, "_CONFIG", None)

    yield tmp_path

    monkeypatch.setattr(src.config, "_CONFIG", None)


@pytest.fixture
def mock_env(monkeypatch):
    import src.config
    import src.pipeline.notifier

    for mod in (src.config, src.pipeline.notifier):
        monkeypatch.setattr(mod, "SMTP_PASSWORD", "test-password")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("SMTP_PASSWORD", "test-password")


@pytest.fixture
def sample_arxiv_result():
    author1 = MagicMock()
    author1.name = "Author One"
    author2 = MagicMock()
    author2.name = "Author Two"

    result = MagicMock()
    result.get_short_id.return_value = "2505.12345"
    result.title = "A Novel Approach to Large Language Models"
    result.authors = [author1, author2]
    result.summary = "This paper presents a new method for training language models."
    result.published = datetime(2025, 5, 28, tzinfo=timezone.utc)
    result.entry_id = "https://arxiv.org/abs/2505.12345"
    result.pdf_url = "https://arxiv.org/pdf/2505.12345"
    result.categories = ["cs.CL", "cs.AI"]
    result.comment = "Accepted at ACL 2025"
    return result


def make_mock_openai_response(content: str):
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


def setup_mock_llm(monkeypatch, model="fast"):
    mock_client = MagicMock()

    def _make_stream_chunks(content_text):
        chunk = MagicMock()
        delta = MagicMock()
        delta.reasoning_content = "thinking..."
        delta.content = content_text
        chunk.choices = [MagicMock(delta=delta)]
        return [chunk]

    mock_client.model = f"deepseek-v4-{model}" if model == "fast" else "deepseek-v4-pro"
    mock_client.call.return_value = make_mock_openai_response('{"test": true}')
    mock_client.parse_json.side_effect = lambda s: __import__("json").loads(
        s.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    )

    if model == "fast":
        monkeypatch.setattr("src.llm.get_fast", lambda: mock_client)
    else:
        monkeypatch.setattr("src.llm.get_pro", lambda: mock_client)

    return mock_client
