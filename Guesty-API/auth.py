"""
utils/auth.py
OAuth 2.0 token management — fetches, caches, and auto-refreshes tokens.

Cache backend is selected automatically:
  - Lambda / no filesystem  → AWS SSM Parameter Store (set TOKEN_SSM_PARAM env var)
  - Local dev               → disk (.token_cache.json, same behaviour as before)
"""

import json
import os
import time
import logging
import requests
from settings import CLIENT_ID, CLIENT_SECRET, TOKEN_URL

logger = logging.getLogger(__name__)

EXPIRY_BUFFER_SECONDS = 300
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".token_cache.json")
SSM_PARAM = os.getenv("TOKEN_SSM_PARAM", "/guesty/token_cache")

# True when running inside AWS Lambda
_IS_LAMBDA = bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))


# ── SSM backend ────────────────────────────────────────────────────────────────

def _ssm_client():
    import boto3
    return boto3.client("ssm", region_name=os.getenv("AWS_REGION", "us-east-1"))


def _load_cached_token_ssm() -> dict:
    try:
        resp = _ssm_client().get_parameter(Name=SSM_PARAM, WithDecryption=True)
        return json.loads(resp["Parameter"]["Value"])
    except Exception:
        return {"token": None, "expires_at": 0}


def _save_token_ssm(token: str, expires_at: float):
    _ssm_client().put_parameter(
        Name=SSM_PARAM,
        Value=json.dumps({"token": token, "expires_at": expires_at}),
        Type="SecureString",
        Overwrite=True,
    )


# ── Disk backend (local dev) ───────────────────────────────────────────────────

def _load_cached_token_disk() -> dict:
    try:
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"token": None, "expires_at": 0}


def _save_token_disk(token: str, expires_at: float):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"token": token, "expires_at": expires_at}, f)


# ── Public interface ───────────────────────────────────────────────────────────

def get_token() -> str:
    """
    Returns a valid Bearer token.
    Uses SSM Parameter Store when running in Lambda, disk cache locally.

    Note: Guesty limits token renewals to 3 times per 24 hours per application.
    The cache keeps us well within that limit in both environments.
    """
    now = time.time()

    if _IS_LAMBDA:
        cache = _load_cached_token_ssm()
    else:
        cache = _load_cached_token_disk()

    if cache["token"] and cache["expires_at"] > (now + EXPIRY_BUFFER_SECONDS):
        logger.debug("Using cached token.")
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

    if _IS_LAMBDA:
        _save_token_ssm(token, expires_at)
        logger.info(f"Token cached to SSM ({SSM_PARAM}). Expires in {expires_in}s.")
    else:
        _save_token_disk(token, expires_at)
        logger.info(f"Token cached to disk. Expires in {expires_in}s ({expires_in // 3600}h).")

    return token
