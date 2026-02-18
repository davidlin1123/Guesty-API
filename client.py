"""
utils/client.py
Base HTTP client — all API models use this to make authenticated requests.
"""

import logging
import requests
from typing import Optional
from config import BASE_URL
from utils.auth import get_token

logger = logging.getLogger(__name__)


def make_request(
    method: str,
    endpoint: str,
    params: Optional[dict] = None,
    body: Optional[dict] = None,
) -> dict:
    """
    Makes an authenticated request to the Guesty API.

    Args:
        method:   HTTP method — "GET", "POST", "PUT", "PATCH", "DELETE"
        endpoint: API path, e.g. "/v1/listings"
        params:   Query string parameters (optional)
        body:     JSON request body (optional)

    Returns:
        Parsed JSON response as a dict.

    Raises:
        requests.HTTPError: On non-2xx responses.
    """
    url = f"{BASE_URL}{endpoint}"

    headers = {
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    logger.info(f"{method.upper()} {url}")

    response = requests.request(
        method=method.upper(),
        url=url,
        headers=headers,
        params=params,
        json=body,
        timeout=30,
    )

    if not response.ok:
        logger.error(f"Request failed: {response.status_code} — {response.text}")
        response.raise_for_status()

    return response.json()
