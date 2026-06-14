"""
models/reservations.py
All Reservation-related Guesty API calls.
Docs: https://open-api-docs.guesty.com/reference/get_reservations
"""

import json
from datetime import date
from typing import Optional
from client import make_request


def get_all(
    limit: int = 25,
    skip: int = 0,
    status: Optional[str] = None,
    listing_id: Optional[str] = None,
    guest_id: Optional[str] = None,
    filters: Optional[dict] = None,
) -> dict:
    """
    GET /v1/reservations
    Search and filter reservations.

    Args:
        limit:      Number of results (max 100).
        skip:       Offset for pagination.
        status:     Filter by status e.g. "confirmed", "inquiry", "canceled".
        listing_id: Filter by a specific listing.
        guest_id:   Filter by a specific guest ID.
        filters:    Guesty filters object, e.g. {"checkOut": {"$gte": "2025-01-01"}}.
                    Serialized to JSON and passed as the `filters` query parameter.
    """
    params = {"limit": limit, "skip": skip}
    if status:
        params["status"] = status
    if listing_id:
        params["listingId"] = listing_id
    if guest_id:
        params["guestId"] = guest_id
    if filters:
        params["filters"] = json.dumps(filters)
    return make_request("GET", "/v1/reservations", params=params)


def get_active_by_guest(guest_id: str) -> list:
    """
    Paginate through current and future reservations for a given guest ID.
    Excludes past reservations by filtering checkOut >= today.
    Returns a flat list of reservation dicts.
    """
    today = date.today().isoformat()
    LIMIT = 100
    skip = 0
    all_results = []
    while True:
        page = get_all(limit=LIMIT, skip=skip, guest_id=guest_id, filters={"checkOut": {"$gte": today}})
        results = page.get("results", [])
        if not results:
            break
        all_results.extend(results)
        skip += len(results)
        if len(results) < LIMIT:
            break
    return all_results


def get_by_id(reservation_id: str) -> dict:
    """
    GET /v1/reservations/{id}
    Retrieve a single reservation.
    """
    return make_request("GET", f"/v1/reservations/{reservation_id}")


def create(payload: dict) -> dict:
    """
    POST /v1/reservations
    Create a new reservation.
    """
    return make_request("POST", "/v1/reservations", body=payload)


def update(reservation_id: str, payload: dict) -> dict:
    """
    PUT /v1/reservations/{id}
    Update an existing reservation.
    """
    return make_request("PUT", f"/v1/reservations/{reservation_id}", body=payload)


def approve(reservation_id: str) -> dict:
    """
    POST /v1/reservations/{id}/approve
    Approve a pending booking request.
    """
    return make_request("POST", f"/v1/reservations/{reservation_id}/approve")


def decline(reservation_id: str) -> dict:
    """
    POST /v1/reservations/{id}/decline
    Decline a pending booking request.
    """
    return make_request("POST", f"/v1/reservations/{reservation_id}/decline")


def add_payment(reservation_id: str, payload: dict) -> dict:
    """
    POST /v1/reservations/{id}/payments
    Add a payment to a reservation.
    """
    return make_request("POST", f"/v1/reservations/{reservation_id}/payments", body=payload)


def get_custom_fields(reservation_id: str) -> dict:
    """
    GET /v1/reservations/{id}/custom-fields
    Retrieve all custom fields for a reservation.
    """
    return make_request("GET", f"/v1/reservations/{reservation_id}/custom-fields")


def update_custom_fields(reservation_id: str, payload: dict) -> dict:
    """
    PUT /v1/reservations/{id}/custom-fields
    Update custom fields on a reservation.
    """
    return make_request("PUT", f"/v1/reservations/{reservation_id}/custom-fields", body=payload)
