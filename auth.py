"""
utils/auth.py
OAuth 2.0 token management — fetches, caches, and auto-refreshes tokens.
"""

import time
import logging
import requests
from config import CLIENT_ID, CLIENT_SECRET, TOKEN_URL

logger = logging.getLogger(__name__)

EXPIRY_BUFFER_SECONDS = 300  # Refresh 5 minutes before expiry

_token_cache: dict = {
    "token": None,
    "expires_at": 0,
}


def get_token() -> str:
    """
    Returns a valid Bearer token.
    Uses the cached token if still valid, otherwise fetches a new one.

    Note: Guesty limits token renewals to 3 times per 24 hours per application.
    This cache ensures we stay well within that limit.
    """
    now = time.time()

    if _token_cache["token"] and _token_cache["expires_at"] > (now + EXPIRY_BUFFER_SECONDS):
        logger.debug("Using cached token.")
        return _token_cache["token"]

    logger.info("Fetching new OAuth token...")

    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "scope": "open-api",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        timeout=10,
    )

    response.raise_for_status()
    data = response.json()

    expires_in = data.get("expires_in", 86400)
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + expires_in

    logger.info(f"Token cached. Expires in {expires_in}s ({expires_in // 3600}h).")
    return _token_cache["token"]
