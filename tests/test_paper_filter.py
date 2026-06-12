import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.fetcher import ArxivPaper
from src.pipeline.filter import (
    chat_final_score,
    flash_title_score,
    keyword_prefilter,
)


def _setup_mock_llm(monkeypatch, model="fast"):
    mock_client = MagicMock()
    mock_client.model = "deepseek-v4-flash" if model == "fast" else "deepseek-v4-pro"
    mock_client.call.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content="{}"))])
    mock_client.parse_json.side_effect = lambda s: json.loads(
        s.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    )
    monkeypatch.setattr("src.pipeline.filter.get_fast", lambda: mock_client)
    monkeypatch.setattr("src.pipeline.filter.get_pro", lambda: mock_client)
    return mock_client


@pytest.mark.unit
class TestKeywordPrefilter:
    def test_title_match_boosts_score(self, temp_config_dir, sample_arxiv_result):
        paper = ArxivPaper(sample_arxiv_result)
        result = keyword_prefilter([paper], include_keywords=["language model"], exclude_keywords=[])
        assert len(result) == 1
        assert result[0] is paper

    def test_exclude_discards(self, temp_config_dir, sample_arxiv_result):
        paper = ArxivPaper(sample_arxiv_result)
        result = keyword_prefilter([paper], include_keywords=["language"], exclude_keywords=["novel"])
        assert len(result) == 0

    def test_truncates_to_top_n(self, temp_config_dir):
        from src.pipeline.fetcher import ArxivPaper
        papers = []
        for i in range(10):
            result = MagicMock()
            result.title = f"Deep Learning Paper {i}"
            result.summary = "This is an abstract about deep learning"
            result.get_short_id.return_value = f"2505.{i}"
            result.published = datetime.now(timezone.utc)
            result.entry_id = f"url{i}"
            result.pdf_url = f"pdf{i}"
            result.authors = []
            result.categories = ["cs.AI"]
            result.comment = None
            papers.append(ArxivPaper(result))
        result = keyword_prefilter(papers, include_keywords=["deep learning"], exclude_keywords=[], top_n=3)
        assert len(result) == 3

    def test_empty_input(self):
        result = keyword_prefilter([], include_keywords=["test"], exclude_keywords=[])
        assert result == []

    def test_uses_config_defaults(self, temp_config_dir, sample_arxiv_result):
        paper = ArxivPaper(sample_arxiv_result)
        result = keyword_prefilter([paper])
        assert len(result) == 1


@pytest.mark.unit
class TestFlashTitleScore:
    def test_empty_papers(self, temp_config_dir, mock_env):
        result = flash_title_score([])
        assert result == []

    def test_batch_scoring(self, temp_config_dir, mock_env, sample_arxiv_result, monkeypatch):
        mock_client = _setup_mock_llm(monkeypatch, "fast")
        mock_client.call.return_value = MagicMock(choices=[
            MagicMock(message=MagicMock(content=json.dumps([
                {"index": 0, "score": 9, "reason": "Highly relevant"}
            ])))
        ])

        paper = ArxivPaper(sample_arxiv_result)
        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = flash_title_score(
                [paper],
                include_keywords=["llm"],
                exclude_keywords=["survey"],
            )
            assert len(result) == 1
            assert result[0][1] == 9

    def test_sort_and_truncate(self, temp_config_dir, mock_env, monkeypatch):
        mock_client = _setup_mock_llm(monkeypatch, "fast")
        mock_client.call.return_value = MagicMock(choices=[
            MagicMock(message=MagicMock(content=json.dumps([
                {"index": j, "score": (5 - j), "reason": "ok"}
                for j in range(5)
            ])))
        ])

        papers = []
        for i in range(5):
            r = MagicMock()
            r.title = f"Paper {i}"
            r.abstract = f"Abstract {i}"
            r.get_short_id.return_value = f"2505.{i}"
            r.authors = []
            r.categories = ["cs.AI"]
            papers.append(ArxivPaper(r))

        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = flash_title_score(papers, include_keywords=["paper"], exclude_keywords=[], top_n=2)
            assert len(result) == 2
            assert result[0][1] > result[1][1]

    def test_batch_error_falls_back(self, temp_config_dir, mock_env, sample_arxiv_result, monkeypatch):
        mock_client = _setup_mock_llm(monkeypatch, "fast")
        mock_client.call.side_effect = [
            Exception("batch fail"),
            MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                "score": 7, "reason": "fallback"
            })))]),
        ]

        paper = ArxivPaper(sample_arxiv_result)
        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = flash_title_score(
                [paper],
                include_keywords=["llm"],
                exclude_keywords=["survey"],
                batch_size=1,
            )
            assert len(result) == 1

    def test_fallback_continues_on_error(self, temp_config_dir, mock_env, sample_arxiv_result, monkeypatch):
        mock_client = _setup_mock_llm(monkeypatch, "fast")
        mock_client.call.side_effect = Exception("fail")

        paper = ArxivPaper(sample_arxiv_result)
        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = flash_title_score(
                [paper],
                include_keywords=["llm"],
                exclude_keywords=["survey"],
                batch_size=1,
            )
            assert result == []


@pytest.mark.unit
class TestChatFinalScore:
    def test_empty_papers(self, temp_config_dir, mock_env):
        result = chat_final_score([])
        assert result == []

    def test_pro_batch_scoring(self, temp_config_dir, mock_env, sample_arxiv_result, monkeypatch):
        mock_pro = _setup_mock_llm(monkeypatch, "pro")
        mock_pro.call.return_value = MagicMock(choices=[
            MagicMock(message=MagicMock(content=json.dumps([
                {"index": 0, "score": 8, "reason": "relevant"}
            ])))
        ])

        paper = ArxivPaper(sample_arxiv_result)
        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = chat_final_score(
                [(paper, 9, "pre-reason")],
                min_score=5,
                max_papers=5,
            )
            assert len(result) == 1
            assert result[0][1] == 8

    def test_below_threshold(self, temp_config_dir, mock_env, sample_arxiv_result, monkeypatch):
        mock_pro = _setup_mock_llm(monkeypatch, "pro")
        mock_pro.call.return_value = MagicMock(choices=[
            MagicMock(message=MagicMock(content=json.dumps([
                {"index": 0, "score": 3, "reason": "irrelevant"}
            ])))
        ])

        paper = ArxivPaper(sample_arxiv_result)
        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = chat_final_score(
                [(paper, 9, "pre-reason")],
                min_score=7,
                max_papers=5,
            )
            assert len(result) == 0

    def test_truncates_to_max(self, temp_config_dir, mock_env, monkeypatch):
        mock_pro = _setup_mock_llm(monkeypatch, "pro")
        mock_pro.call.return_value = MagicMock(choices=[
            MagicMock(message=MagicMock(content=json.dumps([
                {"index": j, "score": 10 - j, "reason": "good"}
                for j in range(5)
            ])))
        ])

        papers = []
        for i in range(5):
            r = MagicMock()
            r.title = f"Paper {i}"
            r.abstract = f"Abstract {i}"
            r.get_short_id.return_value = f"2505.{i}"
            r.authors = []
            r.categories = ["cs.AI"]
            papers.append((ArxivPaper(r), 10 - i, "reason"))

        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = chat_final_score(papers, min_score=0, max_papers=2)
            assert len(result) == 2

    def test_pro_error_falls_to_flash(self, temp_config_dir, mock_env, sample_arxiv_result, monkeypatch):
        mock_pro = _setup_mock_llm(monkeypatch, "pro")
        mock_pro.call.side_effect = Exception("pro fail")

        mock_fast = _setup_mock_llm(monkeypatch, "fast")
        mock_fast.call.return_value = MagicMock(choices=[
            MagicMock(message=MagicMock(content=json.dumps([
                {"index": 0, "score": 7, "reason": "flash fallback"}
            ])))
        ])

        paper = ArxivPaper(sample_arxiv_result)
        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = chat_final_score(
                [(paper, 9, "pre")],
                min_score=5,
                max_papers=5,
                batch_size=1,
            )
            assert len(result) == 1
