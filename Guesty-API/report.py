"""
report.py
Fetches reservations, guests, and listings from Guesty and outputs
a human-readable booking report to booking_report.txt.
"""

import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
from datetime import datetime
from settings import validate
import reservations
import listings
import guests


REPORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "booking_report.txt")
RESPONSES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_responses.json")


def fetch_all_data():
    """Fetch listings, reservations, and guests from the API."""
    print("Fetching data from Guesty API...")
    data = {
        "listings": listings.get_all(limit=100),
        "reservations": reservations.get_all(limit=100),
        "guests": guests.get_all(limit=100, columns="fullName email phone"),
    }

    # Save raw responses
    with open(RESPONSES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Raw API responses saved to: {RESPONSES_FILE}")

    return data


def format_date(iso_str):
    """Convert ISO date string to readable format."""
    if not iso_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%a %d %b %Y")
    except (ValueError, AttributeError):
        return iso_str[:10] if iso_str else "N/A"


def calculate_nights(check_in, check_out):
    """Calculate number of nights between check-in and check-out."""
    try:
        ci = datetime.fromisoformat(check_in.replace("Z", "+00:00"))
        co = datetime.fromisoformat(check_out.replace("Z", "+00:00"))
        return (co - ci).days
    except (ValueError, AttributeError):
        return 0


def build_report(data):
    """Build a human-readable booking report."""
    lines = []
    sep = "=" * 65

    # Build lookup maps
    guest_map = {}
    for g in data["guests"].get("results", []):
        guest_map[g["_id"]] = g

    listing_map = {}
    for l in data["listings"].get("results", []):
        listing_map[l["_id"]] = l

    reservations_list = data["reservations"].get("results", [])

    # Header
    lines.append(sep)
    lines.append("  GUESTY BOOKING REPORT")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(sep)
    lines.append("")
    lines.append(f"  Total Listings:     {data['listings'].get('count', len(data['listings'].get('results', [])))}")
    lines.append(f"  Total Reservations: {data['reservations'].get('count', len(reservations_list))}")
    lines.append(f"  Total Guests:       {data['guests'].get('count', len(data['guests'].get('results', [])))}")
    lines.append("")
    lines.append(sep)
    lines.append("  BOOKING DETAILS")
    lines.append(sep)

    for i, res in enumerate(reservations_list, 1):
        guest_name = res.get("guest", {}).get("fullName", "Unknown Guest")
        listing_title = res.get("listing", {}).get("title", "Unknown Listing")
        check_in = res.get("checkIn", "")
        check_out = res.get("checkOut", "")
        nights = calculate_nights(check_in, check_out)
        conf_code = res.get("confirmationCode", "N/A")
        platform = res.get("integration", {}).get("platform", "direct") if res.get("integration") else "direct"
        guest_id = res.get("guestId", "")

        # Try to get extra guest info from guest map
        guest_detail = guest_map.get(guest_id, {})
        email = guest_detail.get("email", "")
        phone = guest_detail.get("phone", "")

        lines.append("")
        lines.append(f"  Booking #{i}")
        lines.append(f"  {'-' * 50}")
        lines.append(f"  Guest:        {guest_name}")
        if email:
            lines.append(f"  Email:        {email}")
        if phone:
            lines.append(f"  Phone:        {phone}")
        lines.append(f"  Property:     {listing_title}")
        lines.append(f"  Check-in:     {format_date(check_in)}")
        lines.append(f"  Check-out:    {format_date(check_out)}")
        lines.append(f"  Nights:       {nights}")
        lines.append(f"  Platform:     {platform}")
        lines.append(f"  Confirmation: {conf_code}")
        lines.append("")
        lines.append(f"  >> {guest_name} booked \"{listing_title}\" for {nights} night(s)")
        lines.append(f"     from {format_date(check_in)} to {format_date(check_out)} via {platform}.")

    # Summary by listing
    lines.append("")
    lines.append(sep)
    lines.append("  BOOKINGS PER PROPERTY")
    lines.append(sep)

    listing_bookings = {}
    for res in reservations_list:
        title = res.get("listing", {}).get("title", "Unknown")
        listing_bookings.setdefault(title, []).append(res)

    for title, bookings in listing_bookings.items():
        lines.append(f"\n  {title} ({len(bookings)} booking(s))")
        for res in bookings:
            guest_name = res.get("guest", {}).get("fullName", "Unknown")
            check_in = format_date(res.get("checkIn", ""))
            check_out = format_date(res.get("checkOut", ""))
            lines.append(f"    - {guest_name}: {check_in} to {check_out}")

    lines.append("")
    lines.append(sep)
    lines.append("  END OF REPORT")
    lines.append(sep)

    return "\n".join(lines)


def main():
    validate()
    data = fetch_all_data()
    report = build_report(data)

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Booking report saved to: {REPORT_FILE}")
    print("\n" + report)


if __name__ == "__main__":
    main()
