"""
utils/auth.py
OAuth 2.0 token management — fetches, caches, and auto-refreshes tokens.
Token is persisted to disk so it survives between script runs.
"""

import json
import os
import time
import logging
import requests
from settings import CLIENT_ID, CLIENT_SECRET, TOKEN_URL

logger = logging.getLogger(__name__)

EXPIRY_BUFFER_SECONDS = 300  # Refresh 5 minutes before expiry
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".token_cache.json")


def _load_cached_token() -> dict:
    """Load token from disk if the cache file exists."""
    try:
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"token": None, "expires_at": 0}


def _save_token(token: str, expires_at: float):
    """Persist token to disk."""
    with open(TOKEN_FILE, "w") as f:
        json.dump({"token": token, "expires_at": expires_at}, f)


def get_token() -> str:
    """
    Returns a valid Bearer token.
    Uses the cached token (from disk) if still valid, otherwise fetches a new one.

    Note: Guesty limits token renewals to 3 times per 24 hours per application.
    This file-based cache ensures we stay well within that limit.
    """
    now = time.time()
    cache = _load_cached_token()

    if cache["token"] and cache["expires_at"] > (now + EXPIRY_BUFFER_SECONDS):
        logger.debug("Using cached token from disk.")
        return cache["token"]

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
    token = data["access_token"]
    expires_at = now + expires_in

    _save_token(token, expires_at)

    logger.info(f"Token cached to disk. Expires in {expires_in}s ({expires_in // 3600}h).")
    return token
