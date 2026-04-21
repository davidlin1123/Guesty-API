"""
lambda_handler.py

AWS Lambda entry point for the Guesty webhook receiver.
Replaces the Flask server in webhook_server.py — same business logic,
adapted to the API Gateway proxy event format.

API Gateway routes to configure:
    POST  /webhook  → this function
    GET   /health   → this function

Environment variables (set in Lambda console or template.yaml):
    GUESTY_CLIENT_ID
    GUESTY_CLIENT_SECRET
    GUESTY_WEBHOOK_SECRET   Svix signing secret (whsec_xxx) — retrieved from Guesty after
                            registering your webhook URL. Skip verification if not set.
    GUESTY_BASE_URL         (default: https://open-api.guesty.com)
    GUESTY_TOKEN_URL        (default: https://open-api.guesty.com/oauth2/token)
    TOKEN_SSM_PARAM         SSM parameter name for token cache (default: /guesty/token_cache)
    LOG_LEVEL               (default: INFO)

Guesty uses Svix for webhook delivery. Each request includes three headers:
    svix-id          unique message ID
    svix-timestamp   unix timestamp of delivery
    svix-signature   HMAC-SHA256 signature (base64, prefixed with "v1,")
"""

import json
import logging
import os

import blocklist_workflow
from settings import validate, WEBHOOK_SECRET

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

BLOCKLIST_TAG = blocklist_workflow.BLOCKLIST_TAG


# ── Response helpers ───────────────────────────────────────────────────────────

def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


# ── Signature verification (Svix) ─────────────────────────────────────────────

def _verify_signature(raw_body: bytes, headers: dict) -> bool:
    """
    Verify the Svix webhook signature Guesty attaches to every delivery.
    Requires three headers: svix-id, svix-timestamp, svix-signature.

    Skipped entirely if GUESTY_WEBHOOK_SECRET is not set (open mode for initial setup).
    Set the secret after registering your webhook URL with Guesty:
        GET https://open-api.guesty.com/v1/webhooks-v2/secret?url=<your-url>
    """
    if not WEBHOOK_SECRET:
        logger.debug("No GUESTY_WEBHOOK_SECRET set — skipping signature check.")
        return True

    try:
        from svix.webhooks import Webhook, WebhookVerificationError
        wh = Webhook(WEBHOOK_SECRET)
        wh.verify(raw_body, headers)
        return True
    except Exception as exc:
        logger.warning(f"Svix signature verification failed: {exc}")
        return False


# ── Helpers ────────────────────────────────────────────────────────────────────

def _has_tag(tags: list) -> bool:
    return BLOCKLIST_TAG in [t.lower() for t in (tags or [])]


def _process_guest(guest: dict, reason: str) -> None:
    guest_id = guest.get("_id")
    guest_name = guest.get("fullName", "Unknown")

    if not guest_id:
        logger.error(f"[{reason}] Guest payload has no _id — cannot process.")
        return

    logger.info(f"[{reason}] Processing: {guest_name} ({guest_id})")

    if not blocklist_workflow.confirm_blocklisted(guest_id):
        logger.warning(f"  Tag not confirmed on live record — skipping {guest_id}.")
        return

    guest_reservations = blocklist_workflow.get_reservations(guest_id)
    if not guest_reservations:
        logger.info(f"  No reservations found for {guest_id}.")
        return

    logger.info(f"  Found {len(guest_reservations)} reservation(s) — setting Blacklisted custom field on all.")

    for res in guest_reservations:
        res_id = res["_id"]
        conf_code = res.get("confirmationCode", res_id)
        try:
            blocklist_workflow.flag_reservation_custom_fields(res_id)
            logger.info(f"  [OK] {conf_code} ({res_id})")
        except Exception as exc:
            logger.error(f"  [FAIL] {conf_code} ({res_id}): {exc}")


def _process_new_reservation(reservation: dict) -> None:
    res_id = reservation.get("_id")
    conf_code = reservation.get("confirmationCode", res_id)
    guest_id = reservation.get("guestId") or reservation.get("guest", {}).get("_id")
    guest_name = reservation.get("guest", {}).get("fullName", "Unknown")

    if not guest_id:
        logger.error(f"reservation.new — no guestId found for reservation {res_id}")
        return

    logger.info(f"reservation.new — {conf_code} ({res_id}), guest: {guest_name} ({guest_id})")

    if not blocklist_workflow.confirm_blocklisted(guest_id):
        logger.debug(f"  Guest {guest_id} is not blocklisted — no action needed.")
        return

    logger.info(f"  Guest is blocklisted — setting Blacklisted custom field on {conf_code} ({res_id})")
    try:
        blocklist_workflow.flag_reservation_custom_fields(res_id)
        logger.info(f"  [OK] Blacklisted custom field set on {conf_code} ({res_id})")
    except Exception as exc:
        logger.error(f"  [FAIL] Could not update custom fields for {conf_code} ({res_id}): {exc}")


# ── Route handlers ─────────────────────────────────────────────────────────────

def _handle_webhook(event: dict) -> dict:
    raw_body = (event.get("body") or "").encode("utf-8")
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    if not _verify_signature(raw_body, headers):
        logger.warning("Webhook signature mismatch — request rejected.")
        return _response(401, {"error": "Unauthorized"})

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Webhook received with no JSON body.")
        return _response(200, {"status": "ignored", "reason": "empty or non-JSON body"})

    webhook_event = payload.get("event", "")
    logger.info(f"Webhook event received: {webhook_event!r}  by={payload.get('by', '?')}")

    if webhook_event == "guest.updated":
        guest = payload.get("guest", {})
        guest_before = payload.get("guestBefore", {})
        was_blocklisted = _has_tag(guest_before.get("tags", []))
        now_blocklisted = _has_tag(guest.get("tags", []))

        if not was_blocklisted and now_blocklisted:
            logger.info(f"  'blocklisted' tag newly added to {guest.get('fullName')} ({guest.get('_id')})")
            _process_guest(guest, reason="guest.updated — tag added")
        elif was_blocklisted and not now_blocklisted:
            logger.info(
                f"  'blocklisted' tag REMOVED from {guest.get('fullName')} ({guest.get('_id')}) "
                f"— no automatic reversal."
            )
        else:
            logger.debug("  Blocklist tag unchanged — no action needed.")

    elif webhook_event == "guest.created":
        guest = payload.get("guest", {})
        if _has_tag(guest.get("tags", [])):
            logger.info(f"  New guest already tagged 'blocklisted': {guest.get('fullName')} ({guest.get('_id')})")
            _process_guest(guest, reason="guest.created — pre-tagged")
        else:
            logger.debug("  New guest has no blocklist tag — no action needed.")

    elif webhook_event == "guest.deleted":
        guest = payload.get("guest", {})
        logger.info(
            f"  Guest record deleted: {guest.get('fullName', 'Unknown')} "
            f"({guest.get('_id', '?')})  tags={guest.get('tags', [])}  "
            f"by={payload.get('by', '?')}"
        )

    elif webhook_event == "reservation.new":
        _process_new_reservation(payload.get("reservation", {}))

    else:
        logger.info(f"  Unhandled event type {webhook_event!r} — ignored.")

    return _response(200, {"status": "ok", "event": webhook_event})


# ── Lambda entry point ─────────────────────────────────────────────────────────

def lambda_handler(event: dict, context) -> dict:
    """
    AWS Lambda handler. Triggered by API Gateway (proxy integration).

    Routing is based on httpMethod + path from the API Gateway event.
    """
    validate()

    method = event.get("httpMethod", "").upper()
    path = event.get("path", "/")

    if path == "/health" and method == "GET":
        return _response(200, {"status": "healthy"})

    if path == "/webhook" and method == "POST":
        return _handle_webhook(event)

    return _response(404, {"error": f"No route for {method} {path}"})
