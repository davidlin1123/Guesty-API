"""
models/listings.py
All Listing-related Guesty API calls.
Docs: https://open-api-docs.guesty.com/reference/get_listings
"""

from typing import Optional
from utils.client import make_request


def get_all(limit: int = 25, skip: int = 0, fields: Optional[str] = None) -> dict:
    """
    GET /v1/listings
    Retrieve a paginated list of listings.

    Args:
        limit:  Number of results to return (max 100).
        skip:   Number of results to skip (for pagination).
        fields: Comma-separated list of fields to include in response.
    """
    params = {"limit": limit, "skip": skip}
    if fields:
        params["fields"] = fields
    return make_request("GET", "/v1/listings", params=params)


def get_by_id(listing_id: str) -> dict:
    """
    GET /v1/listings/{id}
    Retrieve a single listing by ID.
    """
    return make_request("GET", f"/v1/listings/{listing_id}")


def create(payload: dict) -> dict:
    """
    POST /v1/listings
    Create a new listing.

    Args:
        payload: Dict of listing fields. See Guesty docs for required fields.
    """
    return make_request("POST", "/v1/listings", body=payload)


def update(listing_id: str, payload: dict) -> dict:
    """
    PUT /v1/listings/{id}
    Update an existing listing.
    """
    return make_request("PUT", f"/v1/listings/{listing_id}", body=payload)


def delete(listing_id: str) -> dict:
    """
    DELETE /v1/listings/{id}
    Delete a listing.
    """
    return make_request("DELETE", f"/v1/listings/{listing_id}")


def get_calendar(listing_id: str, start_date: str, end_date: str) -> dict:
    """
    GET /availability-pricing/api/v3/calendar/listings/{id}
    Retrieve the availability calendar for a listing.

    Args:
        listing_id: The listing ID.
        start_date: Start date in YYYY-MM-DD format.
        end_date:   End date in YYYY-MM-DD format.
    """
    return make_request(
        "GET",
        f"/availability-pricing/api/v3/calendar/listings/{listing_id}",
        params={"startDate": start_date, "endDate": end_date},
    )


def update_availability_settings(listing_id: str, payload: dict) -> dict:
    """
    PUT /v1/listings/{id}/availability-settings
    Update availability settings for a listing.
    """
    return make_request("PUT", f"/v1/listings/{listing_id}/availability-settings", body=payload)
