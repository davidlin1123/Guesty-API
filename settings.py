"""
config/settings.py
Loads all configuration from the .env file.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

# ─── Credentials ──────────────────────────────────────────────────────────────
CLIENT_ID = os.getenv("GUESTY_CLIENT_ID")
CLIENT_SECRET = os.getenv("GUESTY_CLIENT_SECRET")

# ─── API URLs ─────────────────────────────────────────────────────────────────
BASE_URL = os.getenv("GUESTY_BASE_URL", "https://open-api.guesty.com")
TOKEN_URL = os.getenv("GUESTY_TOKEN_URL", "https://open-api.guesty.com/oauth2/token")

# ─── Webhook Server ───────────────────────────────────────────────────────────
WEBHOOK_SECRET = os.getenv("GUESTY_WEBHOOK_SECRET", "")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", 5000))

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)


def validate():
    """Call on startup to catch missing credentials early."""
    missing = [k for k, v in {"GUESTY_CLIENT_ID": CLIENT_ID, "GUESTY_CLIENT_SECRET": CLIENT_SECRET}.items() if not v]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")
