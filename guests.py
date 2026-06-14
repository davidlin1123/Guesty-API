"""
models/guests.py
All Guest-related Guesty API calls.
Docs: https://open-api-docs.guesty.com/reference/guestsopenapicontroller_getguestslist
"""

from typing import Optional
from client import make_request


def get_all(limit: int = 25, skip: int = 0, columns: str = "fullName email") -> dict:
    """
    GET /v1/guests-crud
    Retrieve a paginated list of guests.
    """
    return make_request("GET", "/v1/guests-crud", params={"limit": limit, "skip": skip, "columns": columns})


def get_all_pages(columns: str = "fullName email tags") -> list:
    """
    Paginate through ALL guests and return a flat list of guest dicts.

    Args:
        columns: Comma-separated list of fields to include in each result.
                 Always include "tags" to support blocklist filtering.
    """
    LIMIT = 100
    skip = 0
    all_guests = []
    while True:
        page = get_all(limit=LIMIT, skip=skip, columns=columns)
        results = page.get("results", [])
        if not results:
            break
        all_guests.extend(results)
        skip += len(results)
        if len(results) < LIMIT:
            break
    return all_guests


def get_by_id(guest_id: str) -> dict:
    """
    GET /v1/guests-crud/{id}
    Retrieve a single guest by ID.
    """
    return make_request("GET", f"/v1/guests-crud/{guest_id}")


def create(full_name: str, email: str, phone: Optional[str] = None, extra: Optional[dict] = None) -> dict:
    """
    POST /v1/guests-crud
    Create a new guest.

    Args:
        full_name: Guest's full name.
        email:     Guest's email address.
        phone:     Guest's phone number (optional).
        extra:     Any additional fields to include (optional).
    """
    body = {"fullName": full_name, "email": email}
    if phone:
        body["phone"] = phone
    if extra:
        body.update(extra)
    return make_request("POST", "/v1/guests-crud", body=body)


def update(guest_id: str, payload: dict) -> dict:
    """
    PUT /v1/guests-crud/{id}
    Update an existing guest.
    """
    return make_request("PUT", f"/v1/guests-crud/{guest_id}", body=payload)


def get_payment_methods(guest_id: str) -> dict:
    """
    GET /v1/guests/{id}/payment-methods
    List all payment methods for a guest.
    """
    return make_request("GET", f"/v1/guests/{guest_id}/payment-methods")


def add_payment_method(guest_id: str, payload: dict) -> dict:
    """
    POST /v1/guests/{id}/payment-methods
    Add a payment method to a guest profile.
    """
    return make_request("POST", f"/v1/guests/{guest_id}/payment-methods", body=payload)
