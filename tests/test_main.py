import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.fetcher import ArxivPaper
from src.main import _score_color, build_report, load_seen_ids, save_seen_ids, run


@pytest.mark.unit
class TestBuildReport:
    def test_empty_summarized(self, temp_config_dir):
        report = build_report([])
        assert "Daily arXiv Digest" in report
        assert "0 papers" in report

    def test_report_structure(self, temp_config_dir, sample_arxiv_result):
        paper = ArxivPaper(sample_arxiv_result)
        report = build_report([(paper, 9, "Highly relevant")])
        assert paper.title in report
        assert "9/10" in report
        assert paper.arxiv_id in report
        assert "<html>" in report
        assert "class=\"card\"" in report
        assert _score_color(9) in report
        assert paper.abstract in report

    def test_report_with_comment(self, temp_config_dir, sample_arxiv_result):
        paper = ArxivPaper(sample_arxiv_result)
        report = build_report([(paper, 9, "R")])
        assert "ACL 2025" in report

    def test_score_color(self):
        assert _score_color(9) == "#2ecc71"
        assert _score_color(6) == "#f39c12"
        assert _score_color(3) == "#e74c3c"


@pytest.mark.unit
class TestSeenIds:
    def test_load_nonexistent(self, tmp_path, monkeypatch):
        import src.main
        monkeypatch.setattr(src.main, "SEEN_PATH", tmp_path / "nonexistent.json")
        assert load_seen_ids() == set()

    def test_load_valid(self, tmp_path, monkeypatch):
        import src.main
        seen_path = tmp_path / "seen.json"
        with open(seen_path, "w") as f:
            json.dump({"ids": ["2505.1"], "updated": "2025-05-28"}, f)
        monkeypatch.setattr(src.main, "SEEN_PATH", seen_path)
        assert load_seen_ids() == {"2505.1"}

    def test_load_corrupted(self, tmp_path, monkeypatch):
        import src.main
        seen_path = tmp_path / "seen.json"
        with open(seen_path, "w") as f:
            f.write("not json")
        monkeypatch.setattr(src.main, "SEEN_PATH", seen_path)
        assert load_seen_ids() == set()

    def test_save_seen_ids(self, tmp_path, monkeypatch, sample_arxiv_result):
        import src.main
        seen_path = tmp_path / "seen.json"
        monkeypatch.setattr(src.main, "SEEN_PATH", seen_path)
        paper = ArxivPaper(sample_arxiv_result)
        save_seen_ids([paper], {"2505.99999"})
        with open(seen_path) as f:
            data = json.load(f)
        assert "2505.12345" in data["ids"]
        assert "2505.99999" in data["ids"]


@pytest.mark.integration
class TestRun:
    def test_run_no_papers(self, temp_config_dir, mock_env):
        with patch("src.main.fetch_daily_papers", return_value=[]):
            run()

    def test_run_all_seen(self, temp_config_dir, mock_env, monkeypatch):
        import src.main
        monkeypatch.setattr(src.main, "SEEN_PATH", src.main.ROOT / "tests" / "fixture_seen.json")

        mock_paper = MagicMock()
        mock_paper.arxiv_id = "test1"
        mock_paper.title = "Test Paper About AI"
        mock_paper.abstract = "Abstract"
        mock_paper.categories = ["cs.AI"]

        with patch("src.main.fetch_daily_papers", return_value=[mock_paper]):
            with patch("src.main.load_seen_ids", return_value={"test1"}):
                run()

    def test_run_final_score_empty(self, temp_config_dir, mock_env, monkeypatch):
        import src.main
        monkeypatch.setattr(src.main, "SEEN_PATH", src.main.ROOT / "tests" / "fixture_seen.json")

        mock_paper = MagicMock()
        mock_paper.arxiv_id = "test1"
        mock_paper.title = "Test Paper About AI"
        mock_paper.abstract = "Abstract"
        mock_paper.categories = ["cs.AI"]

        with patch("src.main.fetch_daily_papers", return_value=[mock_paper]):
            with patch("src.main.load_seen_ids", return_value=set()):
                with patch("src.main.chat_final_score", return_value=[]):
                    with patch("src.main.save_seen_ids"):
                        run()

    def test_run_full_pipeline(self, temp_config_dir, mock_env, monkeypatch):
        import src.main
        monkeypatch.setattr(src.main, "SEEN_PATH", src.main.ROOT / "tests" / "fixture_seen.json")

        mock_paper = MagicMock()
        mock_paper.arxiv_id = "test1"
        mock_paper.title = "Test Paper"
        mock_paper.authors = []
        mock_paper.abstract = "Abstract"
        mock_paper.published = datetime.now(timezone.utc)
        mock_paper.url = "http://arxiv.org/abs/test1"
        mock_paper.pdf_url = "http://arxiv.org/pdf/test1"
        mock_paper.categories = ["cs.AI"]
        mock_paper.comment = ""

        with patch("src.main.fetch_daily_papers", return_value=[mock_paper]):
            with patch("src.main.load_seen_ids", return_value=set()):
                with patch("src.main.chat_final_score", return_value=[(mock_paper, 9, "ok")]):
                    with patch("src.main.send_report", return_value={"email": True}):
                        with patch("src.main.save_seen_ids"):
                            run()
