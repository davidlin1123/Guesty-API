"""
webhook_server.py

Flask webhook receiver for Guesty guest and reservation events.

Bridges the gap between two Guesty concepts:
  - "blocklisted" tag     : guest-level, follows the guest, but CANNOT be used
                            as an automation condition (e.g. to block access codes).
  - "Blacklisted" custom  : reservation-level, CAN block automated messages,
    field                   but must currently be ticked manually per reservation.

This server automates that link via two triggers:

  TRIGGER 1 — guest.updated (blocklisted tag newly added)
    → Find ALL past/current/future reservations for that guest
    → Set Blacklisted custom field = yes on every one of them
    → Automated messages (access codes) blocked by the custom field condition

  TRIGGER 2 — reservation.new (new booking arrives)
    → Check if the guest already carries the "blocklisted" tag
    → If yes: set Blacklisted custom field = yes on that reservation immediately
    → Automated messages blocked before any codes go out

Payload shapes (confirmed from Guesty docs):
  guest.updated:    { "event": "guest.updated", "by": "...",
                      "guest": {...}, "guestBefore": {...} }
  guest.created:    { "event": "guest.created", "by": "...", "guest": {...} }
  guest.deleted:    { "event": "guest.deleted", "by": "...", "guest": {...} }
  reservation.new:  { "event": "reservation.new", "reservation": {...} }

Run (development):
    python webhook_server.py

Expose publicly so Guesty can reach it:
    ngrok http 5000
    → copy the https URL and register it in Guesty Dashboard → Integrations → Webhooks
    → subscribe to: guest.updated, guest.created, guest.deleted, reservation.new

Environment variables (add to .env):
    WEBHOOK_PORT          Port to listen on (default: 5000)
    GUESTY_WEBHOOK_SECRET Optional HMAC secret for request verification.
                          Set this if/when Guesty adds signature support.
"""

import hashlib
import hmac
import logging
import os

from flask import Flask, abort, jsonify, request
from dotenv import load_dotenv

import blocklist_workflow
from settings import validate, WEBHOOK_SECRET, WEBHOOK_PORT

load_dotenv()

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Mirror the tag constant so both modules stay in sync
BLOCKLIST_TAG = blocklist_workflow.BLOCKLIST_TAG


# ── Signature verification ─────────────────────────────────────────────────────

def _verify_signature(raw_body: bytes, header_sig: str) -> bool:
    """
    Verify an optional HMAC-SHA256 webhook signature.

    If GUESTY_WEBHOOK_SECRET is not set, verification is skipped (open mode).
    If it is set, the header must match sha256=<hex>.
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
      1. Confirm tag is still present via a live GET /v1/guests-crud/{id}
      2. Fetch ALL reservations for that guest (past, current, future)
      3. Set Blacklisted custom field = yes on every reservation
    """
    guest_id = guest.get("_id")
    guest_name = guest.get("fullName", "Unknown")

    if not guest_id:
        logger.error(f"[{reason}] Guest payload has no _id — cannot process.")
        return

    logger.info(f"[{reason}] Processing: {guest_name} ({guest_id})")

    # Step 1: re-confirm the tag via a fresh guest record fetch
    if not blocklist_workflow.confirm_blocklisted(guest_id):
        logger.warning(f"  Tag not confirmed on live record — skipping {guest_id}.")
        return

    # Step 2: fetch ALL reservations (past, current, future)
    guest_reservations = blocklist_workflow.get_reservations(guest_id)
    if not guest_reservations:
        logger.info(f"  No reservations found for {guest_id}.")
        return

    logger.info(f"  Found {len(guest_reservations)} reservation(s) — setting Blacklisted custom field on all.")

    # Step 3: set Blacklisted custom field = yes on every reservation
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
    If yes: sets Blacklisted custom field = yes on this reservation immediately,
    before any automated messages (access codes) can be sent.
    """
    res_id = reservation.get("_id")
    conf_code = reservation.get("confirmationCode", res_id)

    # guestId is a top-level field; fall back to the nested guest object
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


# ── Webhook endpoint ───────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Main webhook receiver.

    Always returns HTTP 200 on business-logic paths so Guesty does not
    retry on expected non-action cases (e.g. tag unchanged, guest with no
    reservations). Only returns non-200 on auth failures or bad payloads.
    """
    raw_body = request.get_data()

    # ── Signature check ────────────────────────────────────────────────────────
    sig_header = request.headers.get("X-Guesty-Signature", "")
    if not _verify_signature(raw_body, sig_header):
        logger.warning("Webhook signature mismatch — request rejected.")
        abort(401)

    # ── Parse body ─────────────────────────────────────────────────────────────
    payload = request.get_json(force=True, silent=True)
    if not payload:
        logger.warning("Webhook received with no JSON body.")
        return jsonify({"status": "ignored", "reason": "empty or non-JSON body"}), 200

    event = payload.get("event", "")
    logger.info(f"Webhook event received: {event!r}  by={payload.get('by', '?')}")

    # ── guest.updated ──────────────────────────────────────────────────────────
    if event == "guest.updated":
        guest = payload.get("guest", {})
        guest_before = payload.get("guestBefore", {})

        tags_before = guest_before.get("tags", [])
        tags_after = guest.get("tags", [])

        was_blocklisted = _has_tag(tags_before)
        now_blocklisted = _has_tag(tags_after)

        if not was_blocklisted and now_blocklisted:
            # Tag was just added — act immediately
            logger.info(
                f"  'blocklisted' tag newly added to {guest.get('fullName')} ({guest.get('_id')})"
            )
            _process_guest(guest, reason="guest.updated — tag added")

        elif was_blocklisted and not now_blocklisted:
            # Tag was removed — log only (no reversal of flagged reservations)
            logger.info(
                f"  'blocklisted' tag REMOVED from {guest.get('fullName')} ({guest.get('_id')}) "
                f"— no automatic reversal."
            )

        else:
            logger.debug("  Blocklist tag unchanged — no action needed.")

    # ── guest.created ──────────────────────────────────────────────────────────
    elif event == "guest.created":
        guest = payload.get("guest", {})
        tags = guest.get("tags", [])

        if _has_tag(tags):
            # New guest already carries the blocklist tag (e.g. imported record)
            logger.info(
                f"  New guest already tagged 'blocklisted': "
                f"{guest.get('fullName')} ({guest.get('_id')})"
            )
            _process_guest(guest, reason="guest.created — pre-tagged")
        else:
            logger.debug("  New guest has no blocklist tag — no action needed.")

    # ── guest.deleted ──────────────────────────────────────────────────────────
    elif event == "guest.deleted":
        guest = payload.get("guest", {})
        logger.info(
            f"  Guest record deleted: {guest.get('fullName', 'Unknown')} "
            f"({guest.get('_id', '?')})  tags={guest.get('tags', [])}  "
            f"by={payload.get('by', '?')}"
        )
        # No API action possible — the guest record is gone.

    # ── reservation.new ────────────────────────────────────────────────────────
    elif event == "reservation.new":
        reservation = payload.get("reservation", {})
        _process_new_reservation(reservation)

    # ── unknown event ──────────────────────────────────────────────────────────
    else:
        logger.info(f"  Unhandled event type {event!r} — ignored.")

    return jsonify({"status": "ok", "event": event}), 200


# ── Health check ───────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    """Simple liveness probe. Useful for load balancers and uptime monitors."""
    return jsonify({"status": "healthy"}), 200


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    validate()
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"Starting Guesty webhook server on port {WEBHOOK_PORT}")
    logger.info(f"Endpoint: POST http://0.0.0.0:{WEBHOOK_PORT}/webhook")
    logger.info(f"Health:   GET  http://0.0.0.0:{WEBHOOK_PORT}/health")
    if not WEBHOOK_SECRET:
        logger.warning("GUESTY_WEBHOOK_SECRET is not set — requests are not verified.")
    app.run(host="0.0.0.0", port=WEBHOOK_PORT, debug=debug_mode)
