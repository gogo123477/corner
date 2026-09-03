"""Expo push (design §4.4). Best-effort; failures are logged, never raised."""

from __future__ import annotations

import json
import logging
import urllib.request

log = logging.getLogger(__name__)
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def send_push(token: str, title: str, body: str) -> bool:
    if not token.startswith("ExponentPushToken"):
        log.info("skipping push: token is not an Expo push token")
        return False
    payload = json.dumps({"to": token, "title": title, "body": body, "sound": "default"}).encode()
    req = urllib.request.Request(
        EXPO_PUSH_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 (fixed https host)
            return resp.status == 200
    except OSError as exc:
        log.warning("push failed: %s", exc)
        return False
