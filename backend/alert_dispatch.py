import os
import smtplib
from email.message import EmailMessage
import httpx
import logging
import concurrent.futures
import time
import config

class LogHandler:
    def send(self, violation: dict, snapshot_path: str, camera_id: str) -> str:
        try:
            timestamp = violation.get('timestamp', time.time())
            logging.info(f"ALERT: Violation {violation['type']} detected on camera {camera_id} at {timestamp}")
            return "ok"
        except Exception as e:
            err = f"error: {e}"
            logging.error(f"LogHandler {err}")
            return err

class EmailHandler:
    def __init__(self, settings: dict):
        self.settings = settings

    def send(self, violation: dict, snapshot_path: str, camera_id: str) -> str:
        if not self.settings.get("enabled"):
            return "skipped: not enabled"
        
        try:
            msg = EmailMessage()
            msg['Subject'] = f"SafetyLens Alert: {violation['type']} on {camera_id}"
            msg['From'] = self.settings.get("from_addr")
            msg['To'] = self.settings.get("to_addrs")
            
            timestamp = violation.get('timestamp', time.time())
            confidence = violation.get('conf', 'N/A')
            if isinstance(confidence, float):
                confidence = f"{confidence:.2f}"

            body = f"Violation details:\nType: {violation['type']}\nCamera: {camera_id}\nConfidence: {confidence}\nTimestamp: {timestamp}"
            msg.set_content(body)
            
            if snapshot_path and os.path.exists(snapshot_path):
                with open(snapshot_path, 'rb') as f:
                    img_data = f.read()
                msg.add_attachment(img_data, maintype='image', subtype='jpeg', filename=os.path.basename(snapshot_path))
                
            with smtplib.SMTP(self.settings.get("smtp_host"), self.settings.get("smtp_port"), timeout=10) as s:
                s.starttls()
                user = self.settings.get("username")
                pw = self.settings.get("password")
                if user and pw:
                    s.login(user, pw)
                s.send_message(msg)
                
            return "ok"
        except Exception as e:
            err = f"error: {e}"
            logging.error(f"EmailHandler {err}")
            return err

class WebhookHandler:
    def __init__(self, settings: dict):
        self.settings = settings

    def send(self, violation: dict, snapshot_path: str, camera_id: str) -> str:
        if not self.settings.get("enabled"):
            return "skipped: not enabled"
            
        try:
            url = self.settings.get("url")
            timestamp = violation.get('timestamp', time.time())
            payload = {
                "type": violation["type"],
                "camera": camera_id,
                "confidence": violation.get("conf"),
                "timestamp": timestamp
            }
            # Snapshot not sent via webhook per instructions
            response = httpx.post(url, json=payload, timeout=5.0)
            response.raise_for_status()
            return "ok"
        except Exception as e:
            err = f"error: {e}"
            logging.error(f"WebhookHandler {err}")
            return err

class AlertDispatcher:
    def __init__(self, settings: dict):
        self.settings = settings
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.log_handler = LogHandler()
        self.email_handler = EmailHandler(settings.get("email", {}))
        self.webhook_handler = WebhookHandler(settings.get("webhook", {}))

    def update_settings(self, settings: dict):
        self.settings = settings
        self.email_handler.settings = settings.get("email", {})
        self.webhook_handler.settings = settings.get("webhook", {})

    def dispatch(self, violation: dict, snapshot_path: str, camera_id: str):
        # Fire and forget
        self.thread_pool.submit(self.log_handler.send, violation, snapshot_path, camera_id)
        if self.settings.get("email", {}).get("enabled"):
            self.thread_pool.submit(self.email_handler.send, violation, snapshot_path, camera_id)
        if self.settings.get("webhook", {}).get("enabled"):
            self.thread_pool.submit(self.webhook_handler.send, violation, snapshot_path, camera_id)

    def shutdown(self):
        self.thread_pool.shutdown(wait=False)

dispatcher = AlertDispatcher(config.ALERT_SETTINGS)
