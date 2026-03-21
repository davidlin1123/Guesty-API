"""
auth.py
OAuth 2.0 token management — fetches, caches, and auto-refreshes tokens.

In Lambda:  token is cached in SSM Parameter Store so it survives across
            invocations (critical — Guesty limits renewals to 3 per 24h).
            A module-level in-memory cache avoids SSM reads on warm invocations.

Locally:    falls back gracefully if SSM is unavailable; behaves like the
            original disk-cache version (token is held in memory only).
"""

import json
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

EXPIRY_BUFFER_SECONDS = 300  # Refresh 5 minutes before expiry
SSM_PARAM_NAME = os.getenv("TOKEN_CACHE_SSM_PARAM", "/guesty/token_cache")

# Module-level in-memory cache.
# Survives Lambda warm invocations (same execution environment reused).
_mem_cache: dict = {"token": None, "expires_at": 0}


# ── SSM helpers ───────────────────────────────────────────────────────────────

def _ssm_load() -> dict:
    """Read token cache from SSM Parameter Store. Returns empty cache on any error."""
    try:
        import boto3
        ssm = boto3.client("ssm")
        resp = ssm.get_parameter(Name=SSM_PARAM_NAME, WithDecryption=True)
        data = json.loads(resp["Parameter"]["Value"])
        logger.debug("Token cache loaded from SSM.")
        return data
    except Exception as exc:
        logger.debug(f"SSM load skipped ({type(exc).__name__}: {exc}).")
        return {"token": None, "expires_at": 0}


def _ssm_save(token: str, expires_at: float) -> None:
    """Persist token cache to SSM Parameter Store. Logs a warning on failure."""
    try:
        import boto3
        ssm = boto3.client("ssm")
        ssm.put_parameter(
            Name=SSM_PARAM_NAME,
            Value=json.dumps({"token": token, "expires_at": expires_at}),
            Type="SecureString",
            Overwrite=True,
        )
        logger.debug("Token cache persisted to SSM.")
    except Exception as exc:
        logger.warning(
            f"Could not persist token to SSM ({type(exc).__name__}: {exc}). "
            "Token is only cached in memory — will be lost on cold start."
        )


# ── Public API ────────────────────────────────────────────────────────────────

def _load_cached_token() -> dict:
    """
    Return the best available cached token.

    Check order:
      1. In-memory cache  (fast, valid for the lifetime of this Lambda container)
      2. SSM Parameter Store  (shared across all Lambda instances/cold starts)
    """
    now = time.time()

    # 1. In-memory — cheapest path, no network call
    if _mem_cache["token"] and _mem_cache["expires_at"] > (now + EXPIRY_BUFFER_SECONDS):
        logger.debug("Using in-memory cached token.")
        return _mem_cache

    # 2. SSM — shared persistent store
    data = _ssm_load()
    if data.get("token") and data.get("expires_at", 0) > (now + EXPIRY_BUFFER_SECONDS):
        # Warm up the in-memory cache from SSM so subsequent calls skip SSM
        _mem_cache["token"] = data["token"]
        _mem_cache["expires_at"] = data["expires_at"]
        logger.debug("In-memory cache warmed from SSM.")
        return _mem_cache

    return {"token": None, "expires_at": 0}


def _save_token(token: str, expires_at: float) -> None:
    """Update in-memory cache and persist to SSM."""
    _mem_cache["token"] = token
    _mem_cache["expires_at"] = expires_at
    _ssm_save(token, expires_at)


def get_token() -> str:
    """
    Returns a valid Bearer token.

    Uses cached token (in-memory → SSM) if still valid, otherwise fetches
    a fresh one from Guesty and caches it.

    Note: Guesty limits token renewals to 3 times per 24 hours per application.
    The two-layer cache (memory + SSM) keeps us well within that limit even
    across Lambda cold starts and concurrent invocations.
    """
    from settings import CLIENT_ID, CLIENT_SECRET, TOKEN_URL

    now = time.time()
    cache = _load_cached_token()

    if cache["token"] and cache["expires_at"] > (now + EXPIRY_BUFFER_SECONDS):
        return cache["token"]

    logger.info("Fetching new OAuth token from Guesty...")

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

    logger.info(f"New token fetched and cached. Expires in {expires_in}s ({expires_in // 3600}h).")
    return token
