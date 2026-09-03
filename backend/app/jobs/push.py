"""Web Push (design §4.4). Best-effort; failures are logged, never raised.

The browser subscribes via the service worker (`web/public/sw.js`) and posts the
subscription to `POST /v1/push/subscribe`; the morning job sends through it.

    python -m app.jobs.push keygen   # prints CORNER_VAPID_PUBLIC_KEY / CORNER_VAPID_PRIVATE_KEY
"""

from __future__ import annotations

import base64
import json
import logging
import sys

from app.config import get_settings

log = logging.getLogger(__name__)


def send_push(subscription: dict, title: str, body: str) -> bool:
    """`subscription` is the PushSubscription JSON the browser produced."""
    settings = get_settings()
    if not (settings.vapid_private_key and subscription.get("endpoint")):
        log.info("skipping push: no VAPID key or no subscription")
        return False
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps({"title": title, "body": body, "url": "/"}),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=6 * 3600,
        )
        return True
    except WebPushException as exc:
        log.warning("push failed: %s", exc)
        return False


def keygen() -> tuple[str, str]:
    """Return (public, private) VAPID keys as base64url strings the browser and pywebpush accept."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    private = ec.generate_private_key(ec.SECP256R1())
    priv_raw = private.private_numbers().private_value.to_bytes(32, "big")
    pub_raw = private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")  # noqa: E731
    return b64(pub_raw), b64(priv_raw)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "keygen":
        pub, priv = keygen()
        print(f"CORNER_VAPID_PUBLIC_KEY={pub}\nCORNER_VAPID_PRIVATE_KEY={priv}")
    else:
        print(__doc__)
