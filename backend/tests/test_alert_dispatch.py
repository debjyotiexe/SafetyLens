import os
import pytest
import logging
from unittest.mock import patch, MagicMock

import config
from alert_dispatch import AlertDispatcher, LogHandler, EmailHandler, WebhookHandler

def test_log_handler(caplog):
    handler = LogHandler()
    with caplog.at_level(logging.INFO):
        res = handler.send({"type": "NO_HELMET"}, "dummy.jpg", "cam_01")
        assert res == "ok"
        assert "ALERT: Violation NO_HELMET detected on camera cam_01" in caplog.text

def test_log_handler_error(caplog):
    handler = LogHandler()
    with patch("alert_dispatch.logging.info", side_effect=Exception("mocked error")):
        with caplog.at_level(logging.ERROR):
            res = handler.send({"type": "NO_HELMET"}, "dummy.jpg", "cam_01")
            assert res.startswith("error: mocked error")
            assert "LogHandler error: mocked error" in caplog.text

def test_email_handler_disabled():
    handler = EmailHandler({"enabled": False})
    assert handler.send({}, "", "cam_01") == "skipped: not enabled"

@patch("alert_dispatch.smtplib.SMTP")
@patch("alert_dispatch.os.path.exists")
@patch("builtins.open", new_callable=MagicMock)
def test_email_handler_success(mock_open, mock_exists, mock_smtp):
    mock_exists.return_value = True
    mock_open.return_value.__enter__.return_value.read.return_value = b"fake_img"
    
    settings = {
        "enabled": True, "smtp_host": "test.com", "smtp_port": 587,
        "from_addr": "a@a.com", "to_addrs": "b@b.com",
        "username": "u", "password": "p"
    }
    handler = EmailHandler(settings)
    res = handler.send({"type": "NO_HELMET", "conf": 0.8}, "dummy.jpg", "cam_01")
    
    assert res == "ok"
    mock_smtp.assert_called_with("test.com", 587, timeout=10)
    mock_smtp.return_value.__enter__.return_value.send_message.assert_called_once()

@patch("alert_dispatch.smtplib.SMTP", side_effect=Exception("smtp fail"))
def test_email_handler_error(mock_smtp, caplog):
    handler = EmailHandler({"enabled": True, "smtp_host": "test.com", "smtp_port": 587})
    with caplog.at_level(logging.ERROR):
        res = handler.send({"type": "NO_HELMET"}, "", "cam_01")
        assert res == "error: smtp fail"
        assert "EmailHandler error: smtp fail" in caplog.text

def test_webhook_handler_disabled():
    handler = WebhookHandler({"enabled": False})
    assert handler.send({}, "", "cam_01") == "skipped: not enabled"

@patch("alert_dispatch.httpx.post")
def test_webhook_handler_success(mock_post):
    mock_post.return_value.raise_for_status = MagicMock()
    handler = WebhookHandler({"enabled": True, "url": "http://test"})
    res = handler.send({"type": "NO_HELMET", "conf": 0.5}, "", "cam_01")
    
    assert res == "ok"
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert kwargs["json"]["type"] == "NO_HELMET"

@patch("alert_dispatch.httpx.post", side_effect=Exception("http fail"))
def test_webhook_handler_error(mock_post, caplog):
    handler = WebhookHandler({"enabled": True, "url": "http://test"})
    with caplog.at_level(logging.ERROR):
        res = handler.send({"type": "NO_HELMET"}, "", "cam_01")
        assert res == "error: http fail"
        assert "WebhookHandler error: http fail" in caplog.text

def test_dispatcher_thread_pool():
    settings = {
        "log": {"enabled": True},
        "email": {"enabled": True},
        "webhook": {"enabled": True}
    }
    dispatcher = AlertDispatcher(settings)
    
    with patch.object(dispatcher.log_handler, 'send') as m_log, \
         patch.object(dispatcher.email_handler, 'send') as m_email, \
         patch.object(dispatcher.webhook_handler, 'send') as m_hook:
        
        dispatcher.dispatch({"type": "NO_HELMET"}, "", "cam_01")
        
        # wait for threads
        dispatcher.shutdown()
        
        m_log.assert_called_once()
        m_email.assert_called_once()
        m_hook.assert_called_once()
