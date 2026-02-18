"""
main.py
Entry point — run this to test the integration.
"""

import requests
from config import validate
import models.listings as listings
import models.reservations as reservations
import models.guests as guests
import models.tasks as tasks


def main():
    # Validate .env credentials are loaded before making any calls
    validate()

    print("\n" + "=" * 55)
    print("  Guesty API Client — Connection Test")
    print("=" * 55)

    # ── Listings ──────────────────────────────────────────────
    print("\n📋 Listings (first 5):")
    result = listings.get_all(limit=5)
    for l in result.get("results", []):
        print(f"  [{l.get('_id')}] {l.get('title', 'Untitled')}")

    # ── Reservations ──────────────────────────────────────────
    print("\n📅 Reservations (first 5):")
    result = reservations.get_all(limit=5)
    for r in result.get("results", []):
        print(f"  [{r.get('_id')}] {r.get('status')} — {r.get('checkIn', '')[:10]} to {r.get('checkOut', '')[:10]}")

    # ── Guests ────────────────────────────────────────────────
    print("\n👥 Guests (first 5):")
    result = guests.get_all(limit=5)
    for g in result.get("results", []):
        print(f"  [{g.get('_id')}] {g.get('fullName', 'Unknown')} — {g.get('email', '')}")

    # ── Tasks ─────────────────────────────────────────────────
    print("\n✅ Tasks (first 5):")
    result = tasks.get_all(limit=5)
    for t in result.get("results", []):
        print(f"  [{t.get('_id')}] {t.get('title', 'Untitled')} — {t.get('status', '')}")

    print("\n" + "=" * 55)
    print("  All checks passed ✓")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"\n❌ HTTP Error: {e}")
    except EnvironmentError as e:
        print(f"\n❌ Config Error: {e}")
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        raise
