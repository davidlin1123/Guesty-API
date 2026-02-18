"""
models/reservations.py
All Reservation-related Guesty API calls.
Docs: https://open-api-docs.guesty.com/reference/get_reservations
"""

from typing import Optional
from client import make_request


def get_all(
    limit: int = 25,
    skip: int = 0,
    status: Optional[str] = None,
    listing_id: Optional[str] = None,
) -> dict:
    """
    GET /v1/reservations
    Search and filter reservations.

    Args:
        limit:      Number of results (max 100).
        skip:       Offset for pagination.
        status:     Filter by status e.g. "confirmed", "inquiry", "canceled".
        listing_id: Filter by a specific listing.
    """
    params = {"limit": limit, "skip": skip}
    if status:
        params["status"] = status
    if listing_id:
        params["listingId"] = listing_id
    return make_request("GET", "/v1/reservations", params=params)


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
