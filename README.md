# Guesty API Client

Python client for the [Guesty Open API](https://open-api-docs.guesty.com) with OAuth 2.0 authentication, token caching, and modular model structure.

---

## Project Structure

```
guesty_api/
├── .env                  # Your credentials (never commit this)
├── .env.example          # Template for credentials
├── .gitignore
├── requirements.txt
├── main.py               # Entry point / connection test
│
├── config/
│   └── settings.py       # Loads .env into variables
│
├── utils/
│   ├── auth.py           # OAuth token fetching & caching
│   └── client.py         # Base HTTP request handler
│
└── models/
    ├── listings.py       # Listing API calls
    ├── reservations.py   # Reservation API calls
    ├── guests.py         # Guest API calls
    └── tasks.py          # Task API calls
```

---

## Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Configure credentials**
```bash
copy .env.example .env
```
Then open `.env` and fill in your `GUESTY_CLIENT_ID` and `GUESTY_CLIENT_SECRET`.  
Get these from: **Guesty Dashboard → Integrations → API → Open API Keys**

**3. Run the connection test**
```bash
python main.py
```

---

## Usage Examples

```python
import models.listings as listings
import models.reservations as reservations
import models.guests as guests
import models.tasks as tasks

# Listings
all_listings = listings.get_all(limit=10)
single_listing = listings.get_by_id("abc123")
calendar = listings.get_calendar("abc123", "2026-03-01", "2026-03-31")

# Reservations
all_reservations = reservations.get_all(limit=10, status="confirmed")
single_res = reservations.get_by_id("res123")
reservations.approve("res123")

# Guests
all_guests = guests.get_all(limit=10)
new_guest = guests.create("Jane Smith", "jane@example.com", "+61400000000")

# Tasks
all_tasks = tasks.get_all(limit=10)
tasks.create({"title": "Clean room", "listingId": "abc123", "scheduledDate": "2026-03-01"})
```

---

## Token Management

- Tokens are cached in memory and reused for 24 hours
- Auto-refreshes 5 minutes before expiry
- Guesty limits renewals to **3 per 24 hours** — the cache keeps you well within this

---

## Adding a New Model

1. Create `models/your_model.py`
2. Import `make_request` from `utils.client`
3. Add it to `models/__init__.py`

```python
# models/webhooks.py
from utils.client import make_request

def get_all() -> dict:
    return make_request("GET", "/v1/webhooks")
```
