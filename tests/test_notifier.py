import smtplib
from unittest.mock import MagicMock, patch

import pytest

import src.pipeline.notifier as notifier
import src.config


@pytest.mark.unit
class TestSendEmail:
    def test_disabled_in_config(self, temp_config_dir, mock_env):
        src.config.reload()
        src.config.set("notification.email.enabled", False)
        result = notifier.send_email("title", "content")
        assert result is False

    def test_no_password(self, temp_config_dir, monkeypatch):
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
        monkeypatch.setattr(src.config, "SMTP_PASSWORD", "")
        result = notifier.send_email("title", "content")
        assert result is False

    def test_no_sender_email(self, temp_config_dir, mock_env, monkeypatch):
        src.config.reload()
        src.config.set("user.email", "")
        result = notifier.send_email("title", "content")
        assert result is False

    def test_successful_send(self, temp_config_dir, mock_env):
        mock_server = MagicMock()
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_server

        with patch("src.pipeline.notifier.smtplib.SMTP", return_value=mock_smtp):
            result = notifier.send_email("Test Subject", "<p>content</p>")
            assert result is True
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once()
            mock_server.sendmail.assert_called_once()

    def test_smtp_error(self, temp_config_dir, mock_env):
        with patch("src.pipeline.notifier.smtplib.SMTP", side_effect=smtplib.SMTPException("error")):
            result = notifier.send_email("title", "content")
            assert result is False


@pytest.mark.unit
class TestSendReport:
    def test_send_report(self, temp_config_dir, mock_env):
        with patch("src.pipeline.notifier.send_email", return_value=True):
            results = notifier.send_report("title", "<p>html</p>")
            assert results["email"] is True
