"""
lambda_handler.py

AWS Lambda entry point for Guesty webhook events.
Invoked by API Gateway; supports both payload formats:
  v1 (REST API):  event["httpMethod"], event["path"]
  v2 (HTTP API):  event["requestContext"]["http"]["method/path"]

Bridges two Guesty concepts:
  - "blocklisted" tag    : guest-level, cannot be used as an automation condition.
  - "Blacklisted" custom : reservation-level, blocks automated messages (access
    field                  codes) but must otherwise be ticked manually.

This handler automates that link via two triggers:

  TRIGGER 1 — guest.updated (blocklisted tag newly added)
    → Confirm the tag is still present via a live GET /v1/guests-crud/{id}
    → Fetch CURRENT and FUTURE reservations only (past stays are not affected)
    → Set Blacklisted custom field = yes on each qualifying reservation
    → Automated messages blocked by the custom field condition going forward

  TRIGGER 2 — reservation.new (new booking arrives)
    → Check if the guest already carries the "blocklisted" tag
    → If yes: set Blacklisted custom field = yes on that reservation immediately,
      before any automated messages (access codes) can be sent

Payload shapes (confirmed from Guesty docs):
  guest.updated:    { "event": "guest.updated", "by": "...",
                      "guest": {...}, "guestBefore": {...} }
  guest.created:    { "event": "guest.created", "by": "...", "guest": {...} }
  guest.deleted:    { "event": "guest.deleted", "by": "...", "guest": {...} }
  reservation.new:  { "event": "reservation.new", "reservation": {...} }

Routes:
  POST /webhook  — receives all Guesty webhook events listed above
  GET  /health   — liveness probe for load balancers / uptime monitors

Handler reference for Lambda console:
  lambda_handler.handler
"""

import base64
import hashlib
import hmac
import json
import logging
import os

import blocklist_workflow
from settings import WEBHOOK_SECRET

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

BLOCKLIST_TAG = blocklist_workflow.BLOCKLIST_TAG


# ── Signature verification ─────────────────────────────────────────────────────

def _verify_signature(raw_body: bytes, header_sig: str) -> bool:
    """
    Verify an optional HMAC-SHA256 webhook signature.
    If GUESTY_WEBHOOK_SECRET is not set, verification is skipped (open mode).
    """
    if not WEBHOOK_SECRET:
        logger.debug("No GUESTY_WEBHOOK_SECRET set — skipping signature check.")
        return True

    if not header_sig:
        logger.warning("Signature expected but header is missing — rejecting.")
        return False

    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, header_sig)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _has_tag(tags: list) -> bool:
    """Return True if the blocklist tag is present (case-insensitive)."""
    return BLOCKLIST_TAG in [t.lower() for t in (tags or [])]


def _process_guest(guest: dict, reason: str) -> None:
    """
    Trigger 1 handler — runs when the 'blocklisted' tag is newly added to a guest.

    Steps:
      1. Confirm the tag is still present via a live GET /v1/guests-crud/{id}
         (guards against webhook replays or race conditions).
      2. Fetch CURRENT and FUTURE reservations only (checkOut >= today).
         Past reservations are intentionally skipped — flagging a completed
         stay has no operational effect and could cause confusion.
      3. Set Blacklisted custom field = yes on each qualifying reservation
         so that automated messages (access codes) are blocked going forward.
    """
    guest_id = guest.get("_id")
    guest_name = guest.get("fullName", "Unknown")

    if not guest_id:
        logger.error(f"[{reason}] Guest payload has no _id — cannot process.")
        return

    logger.info(f"[{reason}] Processing: {guest_name} ({guest_id})")

    # Step 1: re-confirm the tag via a fresh live fetch to guard against replays
    if not blocklist_workflow.confirm_blocklisted(guest_id):
        logger.warning(f"  Tag not confirmed on live record — skipping {guest_id}.")
        return

    # Step 2: fetch only current and future reservations (past stays are excluded)
    guest_reservations = blocklist_workflow.get_current_and_future_reservations(guest_id)
    if not guest_reservations:
        logger.info(f"  No current or future reservations found for {guest_id}.")
        return

    logger.info(
        f"  Found {len(guest_reservations)} current/future reservation(s) "
        f"— setting Blacklisted custom field on each."
    )

    # Step 3: set Blacklisted custom field = yes on every qualifying reservation
    for res in guest_reservations:
        res_id = res["_id"]
        conf_code = res.get("confirmationCode", res_id)
        try:
            blocklist_workflow.flag_reservation_custom_fields(res_id)
            logger.info(f"  [OK] {conf_code} ({res_id})")
        except Exception as exc:
            logger.error(f"  [FAIL] {conf_code} ({res_id}): {exc}")


def _process_new_reservation(reservation: dict) -> None:
    """
    Trigger 2 handler — runs when a new reservation arrives (reservation.new).

    Checks whether the guest already carries the 'blocklisted' tag.
    If yes: sets Blacklisted custom field = yes immediately, before any
    automated messages (access codes) can be sent.
    """
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


# ── Response helpers ───────────────────────────────────────────────────────────

def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


# ── Lambda entry point ─────────────────────────────────────────────────────────

def handler(event, context):
    """
    AWS Lambda entry point. Called by API Gateway for every inbound request.

    Always returns HTTP 200 on business-logic paths so Guesty does not retry
    on expected non-action cases (e.g. tag unchanged, guest with no reservations).
    Only returns non-200 on auth failures or unrecognised routes.
    """
    # Normalise API Gateway payload format v1 (REST) and v2 (HTTP API)
    req_ctx = event.get("requestContext", {})
    method = (
        req_ctx.get("http", {}).get("method")
        or event.get("httpMethod", "")
    ).upper()
    path = (
        req_ctx.get("http", {}).get("path")
        or event.get("path", "")
    )

    # ── Health check ──────────────────────────────────────────────────────────
    if method == "GET" and path == "/health":
        return _response(200, {"status": "healthy"})

    # ── Route guard ───────────────────────────────────────────────────────────
    if method != "POST" or path != "/webhook":
        return _response(404, {"status": "error", "message": "Not found"})

    # ── Decode body ───────────────────────────────────────────────────────────
    # API Gateway may base64-encode the body for binary content types
    raw_body_str = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body_str)
    else:
        raw_body = raw_body_str.encode()

    # ── Signature check ───────────────────────────────────────────────────────
    # API Gateway HTTP API (v2) lowercases all header names
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    sig_header = headers.get("x-guesty-signature", "")

    if not _verify_signature(raw_body, sig_header):
        logger.warning("Webhook signature mismatch — request rejected.")
        return _response(401, {"status": "error", "message": "Unauthorized"})

    # ── Parse JSON ────────────────────────────────────────────────────────────
    try:
        payload = json.loads(raw_body or b"{}")
    except json.JSONDecodeError:
        logger.warning("Webhook received with non-JSON body.")
        return _response(200, {"status": "ignored", "reason": "non-JSON body"})

    event_type = payload.get("event", "")
    logger.info(f"Webhook event received: {event_type!r}  by={payload.get('by', '?')}")

    # ── guest.updated ─────────────────────────────────────────────────────────
    if event_type == "guest.updated":
        guest = payload.get("guest", {})
        guest_before = payload.get("guestBefore", {})

        was_blocklisted = _has_tag(guest_before.get("tags", []))
        now_blocklisted = _has_tag(guest.get("tags", []))

        if not was_blocklisted and now_blocklisted:
            # Tag was just added — flag all current and future reservations
            logger.info(f"  'blocklisted' tag newly added to {guest.get('fullName')} ({guest.get('_id')})")
            _process_guest(guest, reason="guest.updated — tag added")
        elif was_blocklisted and not now_blocklisted:
            logger.info(
                f"  'blocklisted' tag REMOVED from {guest.get('fullName')} ({guest.get('_id')}) "
                f"— no automatic reversal."
            )
        else:
            logger.debug("  Blocklist tag unchanged — no action needed.")

    # ── guest.created ─────────────────────────────────────────────────────────
    elif event_type == "guest.created":
        guest = payload.get("guest", {})
        if _has_tag(guest.get("tags", [])):
            logger.info(f"  New guest already tagged 'blocklisted': {guest.get('fullName')} ({guest.get('_id')})")
            _process_guest(guest, reason="guest.created — pre-tagged")
        else:
            logger.debug("  New guest has no blocklist tag — no action needed.")

    # ── guest.deleted ─────────────────────────────────────────────────────────
    elif event_type == "guest.deleted":
        guest = payload.get("guest", {})
        logger.info(
            f"  Guest record deleted: {guest.get('fullName', 'Unknown')} "
            f"({guest.get('_id', '?')})  tags={guest.get('tags', [])}  "
            f"by={payload.get('by', '?')}"
        )

    # ── reservation.new ───────────────────────────────────────────────────────
    elif event_type == "reservation.new":
        reservation = payload.get("reservation", {})
        _process_new_reservation(reservation)

    # ── unknown event ─────────────────────────────────────────────────────────
    else:
        logger.info(f"  Unhandled event type {event_type!r} — ignored.")

    return _response(200, {"status": "ok", "event": event_type})
