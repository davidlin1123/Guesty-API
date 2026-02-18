"""
main.py
Entry point — run this to test the integration.
"""

import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from settings import validate
import listings
import reservations
import guests
import tasks


def main():
    # Validate .env credentials are loaded before making any calls
    validate()

    print("\n" + "=" * 55)
    print("  Guesty API Client — Connection Test")
    print("=" * 55)

    # ── Listings ──────────────────────────────────────────────
    print("\nListings (first 5):")
    result = listings.get_all(limit=5)
    for l in result.get("results", []):
        print(f"  [{l.get('_id')}] {l.get('title', 'Untitled')}")

    # ── Reservations ──────────────────────────────────────────
    print("Reservations (first 5):")
    result = reservations.get_all(limit=5)
    for r in result.get("results", []):
        print(f"  [{r.get('_id')}] {r.get('status')} — {r.get('checkIn', '')[:10]} to {r.get('checkOut', '')[:10]}")

    # ── Guests ────────────────────────────────────────────────
    print("Guests (first 5):")
    result = guests.get_all(limit=5)
    for g in result.get("results", []):
        print(f"  [{g.get('_id')}] {g.get('fullName', 'Unknown')} — {g.get('email', '')}")

    # ── Tasks ─────────────────────────────────────────────────
    print(" Tasks (first 5):")
    result = tasks.get_all(limit=5)
    for t in result.get("results", []):
        print(f"  [{t.get('_id')}] {t.get('title', 'Untitled')} — {t.get('status', '')}")

    print("\n" + "=" * 55)
    print("  All checks passed")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"\n[ERROR] HTTP Error: {e}")
    except EnvironmentError as e:
        print(f"\n[ERROR] Config Error: {e}")
    except Exception as e:
        print(f"\n[ERROR] Unexpected Error: {e}")
        raise
