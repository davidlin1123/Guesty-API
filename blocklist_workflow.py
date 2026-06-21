"""
blocklist_workflow.py

Workflow: find guests tagged "blocklisted" and flag their reservations.

Steps:
  1. Page through ALL guests (requesting the "tags" column).
  2. For each guest with tags containing "blocklisted", confirm via a
     full guest detail call (GET /v1/guests-crud/{id}).
  3. Fetch all reservations for that guest (GET /v1/reservations?guestId=...).
  4. PUT each reservation to mark it as blacklisted.

Run directly:
    python blocklist_workflow.py

Or import and call run() from another module.
"""

import logging
import requests

import guests
import reservations
from settings import validate

logger = logging.getLogger(__name__)

# ── Tag to scan for (case-insensitive) ────────────────────────────────────────
BLOCKLIST_TAG = "blocklisted"

# ── Payload sent to PUT /v1/reservations/{id} for each flagged reservation ────
# Adjust this dict to match your Guesty setup. Common options:
#   {"notes": "BLACKLISTED"}             — adds a note to the reservation
#   {"status": "canceled"}               — cancels the reservation outright
BLACKLIST_PAYLOAD = {
    "notes": "BLACKLISTED — guest is on the blocklist. Flagged automatically.",
}

# ── Payload sent to PUT /v1/reservations/{id}/custom-fields ──────────────────
# This is the primary flag used by both webhook triggers.
# Adjust the key to match your exact Guesty custom field name or ID.
# Common formats:
#   Object: {"blacklisted": "true"}
#   Array:  [{"fieldId": "YOUR_FIELD_ID", "value": "true"}]
BLACKLIST_CUSTOM_FIELDS_PAYLOAD = {
    "customFields": [
        {"fieldId": "64e326bf71323c004cd765ac", "value": True}
    ]
}


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — collect all blocklisted guests
# ─────────────────────────────────────────────────────────────────────────────

def find_blocklisted_guests() -> list[dict]:
    """
    Pages through every guest and returns those whose tags array
    contains BLOCKLIST_TAG (case-insensitive match).
    """
    logger.info("Scanning all guests for blocklisted tag...")
    all_guests = guests.get_all_pages(columns="fullName email tags")
    logger.info(f"Total guests fetched: {len(all_guests)}")

    flagged = [
        g for g in all_guests
        if BLOCKLIST_TAG in [t.lower() for t in (g.get("tags") or [])]
    ]

    logger.info(f"Blocklisted guests found: {len(flagged)}")
    return flagged


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — confirm tag via full guest detail
# ─────────────────────────────────────────────────────────────────────────────

def confirm_blocklisted(guest_id: str) -> bool:
    """
    GET /v1/guests-crud/{id} and verify the blocklist tag is present.
    Returns True if confirmed, False otherwise.
    """
    try:
        detail = guests.get_by_id(guest_id)
        tags = [t.lower() for t in (detail.get("tags") or [])]
        return BLOCKLIST_TAG in tags
    except requests.HTTPError as exc:
        logger.warning(f"Could not fetch guest {guest_id}: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — fetch reservations for that guest
# ─────────────────────────────────────────────────────────────────────────────

def get_reservations(guest_id: str) -> list[dict]:
    """
    Returns current and future reservations for guest_id (checkOut >= today).
    """
    return reservations.get_active_by_guest(guest_id)


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — PUT the reservation to mark it blacklisted
# ─────────────────────────────────────────────────────────────────────────────

def flag_reservation(reservation_id: str) -> dict:
    """
    PUT /v1/reservations/{id} with BLACKLIST_PAYLOAD.
    """
    logger.info(f"Flagging reservation {reservation_id} with {BLACKLIST_PAYLOAD}")
    return reservations.update(reservation_id, BLACKLIST_PAYLOAD)


def flag_reservation_custom_fields(reservation_id: str) -> dict:
    """
    PUT /v1/reservations/{id}/custom-fields with BLACKLIST_CUSTOM_FIELDS_PAYLOAD.

    Sets the Blacklisted custom field to yes on the reservation.
    This is the primary action for both webhook triggers:
      - guest.updated  (blocklisted tag newly added → all reservations)
      - reservation.new (new booking from a blocklisted guest → that reservation)
    """
    logger.info(f"Setting Blacklisted custom field on reservation {reservation_id}")
    return reservations.update_custom_fields(reservation_id, BLACKLIST_CUSTOM_FIELDS_PAYLOAD)


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────────

def run():
    """
    Main workflow entry point. Run directly: python blocklist_workflow.py
    """
    validate()

    print("\n" + "=" * 60)
    print("  Blocklist Workflow")
    print("=" * 60)

    # ── Step 1: find blocklisted guests ───────────────────────────────────────
    bl_guests = find_blocklisted_guests()

    if not bl_guests:
        print("\n  No blocklisted guests found. Nothing to do.")
        print("=" * 60 + "\n")
        return

    print(f"\n  Guests tagged '{BLOCKLIST_TAG}' ({len(bl_guests)}):")
    for g in bl_guests:
        print(f"    [{g['_id']}] {g.get('fullName', 'Unknown')}  tags={g.get('tags')}")

    total_updated = 0
    total_skipped = 0
    total_failed = 0

    for guest in bl_guests:
        guest_id = guest["_id"]
        guest_name = guest.get("fullName", "Unknown")

        print(f"\n  Processing: {guest_name} ({guest_id})")

        # ── Step 2: confirm tag via full detail call ───────────────────────────
        if not confirm_blocklisted(guest_id):
            print(f"    ⚠  Tag not confirmed on full guest record — skipping.")
            total_skipped += 1
            continue

        # ── Step 3: fetch their reservations ──────────────────────────────────
        guest_reservations = get_reservations(guest_id)

        if not guest_reservations:
            print(f"    No reservations found.")
            continue

        print(f"    Found {len(guest_reservations)} current/future reservation(s).")

        # ── Steps 4 & 5: fetch custom fields then PUT each reservation ───────────
        for res in guest_reservations:
            res_id = res["_id"]
            conf_code = res.get("confirmationCode", res_id)

            # Step 4: fetch custom fields for this reservation
            try:
                custom_fields = reservations.get_custom_fields(res_id)
                fields = custom_fields.get("results", custom_fields)
                print(f"    Custom fields for {conf_code}: {fields}")
            except requests.HTTPError as exc:
                print(f"    ⚠  Could not fetch custom fields for {conf_code}: {exc}")

            # Step 5: flag the reservation as blacklisted
            try:
                flag_reservation(res_id)
                print(f"    ✓  {conf_code} ({res_id}) — updated")
                total_updated += 1
            except requests.HTTPError as exc:
                print(f"    ✗  {conf_code} ({res_id}) — FAILED: {exc}")
                total_failed += 1

    print(f"\n  Summary:")
    print(f"    Updated : {total_updated}")
    print(f"    Skipped : {total_skipped}")
    print(f"    Failed  : {total_failed}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        run()
    except requests.HTTPError as exc:
        print(f"\n[ERROR] HTTP Error: {exc}")
    except EnvironmentError as exc:
        print(f"\n[ERROR] Config Error: {exc}")
    except Exception as exc:
        print(f"\n[ERROR] Unexpected: {exc}")
        raise
