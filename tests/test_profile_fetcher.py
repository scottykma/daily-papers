from unittest.mock import MagicMock, patch

import pytest

from src.profile.fetcher import (
    ScholarProfile,
    extract_user_id,
    fetch_profile,
)


@pytest.mark.unit
class TestExtractUserId:
    def test_full_url_with_user_id(self):
        url = "https://scholar.google.com/citations?user=ABC123&hl=en"
        assert extract_user_id(url) == "ABC123"

    def test_url_with_only_user_param(self):
        url = "https://scholar.google.com/citations?user=DEF456"
        assert extract_user_id(url) == "DEF456"

    def test_non_scholar_url(self):
        assert extract_user_id("https://arxiv.org/abs/2505.1") is None

    def test_empty_url(self):
        assert extract_user_id("") is None


@pytest.mark.unit
class TestScholarProfile:
    def test_init_defaults(self):
        profile = ScholarProfile()
        assert profile.name == ""
        assert profile.affiliation == ""
        assert profile.interests == []
        assert profile.publications == []

    def test_to_dict(self):
        profile = ScholarProfile()
        profile.name = "Test Author"
        profile.publications = [{"title": "Test Paper"}]
        d = profile.to_dict()
        assert d["name"] == "Test Author"
        assert d["total_papers"] == 1


@pytest.mark.unit
class TestFetchProfile:
    def test_semantic_scholar_success(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"authorId": "123", "name": "Test Author"}],
        }
        mock_resp.raise_for_status.return_value = None

        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {
            "name": "Test Author",
            "affiliations": ["Test University"],
            "papers": [
                {
                    "title": "Paper 1",
                    "year": 2025,
                    "abstract": "Test abstract",
                    "citationCount": 50,
                }
            ],
        }
        mock_resp2.raise_for_status.return_value = None

        with patch("src.profile.fetcher.requests.get") as mock_get:
            mock_get.side_effect = [mock_resp, mock_resp2]
            profile = fetch_profile("https://scholar.google.com/citations?user=ABC")
            assert profile.name == "Test Author"
            assert profile.affiliation == "Test University"
            assert len(profile.publications) == 1
            assert profile.publications[0]["title"] == "Paper 1"
            assert profile.publications[0]["citation_count"] == 50

    def test_semantic_scholar_empty_falls_back(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": []}
        mock_resp.raise_for_status.return_value = None

        mock_gs = MagicMock()
        mock_author = {
            "name": "GS Author",
            "affiliation": "GS Univ",
            "interests": [],
            "publications": [],
        }
        mock_gs.search_author_id.return_value = mock_author
        mock_gs.fill.return_value = mock_author

        with patch("src.profile.fetcher.requests.get", return_value=mock_resp):
            with patch("src.profile.fetcher._fetch_from_google_scholar", return_value=None):
                with pytest.raises(ValueError):
                    fetch_profile("https://scholar.google.com/citations?user=ABC")

    def test_semantic_scholar_exception(self, monkeypatch):
        with patch("src.profile.fetcher.requests.get", side_effect=Exception("network error")):
            with patch("src.profile.fetcher._fetch_from_google_scholar", return_value=None):
                with pytest.raises(ValueError):
                    fetch_profile("https://scholar.google.com/citations?user=ABC")

    def test_no_author_id_in_response(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"name": "Author"}]}
        mock_resp.raise_for_status.return_value = None

        with patch("src.profile.fetcher.requests.get", return_value=mock_resp):
            with patch("src.profile.fetcher._fetch_from_google_scholar", return_value=None):
                with pytest.raises(ValueError):
                    fetch_profile("https://scholar.google.com/citations?user=ABC")
