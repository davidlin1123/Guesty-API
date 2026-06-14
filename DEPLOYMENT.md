# Guesty Webhook — AWS Lambda Deployment Guide

## What was built

The original Flask webhook server (`webhook_server.py`) was adapted for AWS Lambda.
These files were created or modified:

| File | Change |
|------|--------|
| `lambda_handler.py` | New — Lambda entry point, replaces Flask server |
| `auth.py` | Updated — SSM token cache for Lambda, disk cache for local dev |
| `template.yaml` | New — AWS SAM deployment template |
| `requirements.txt` | Updated — added `flask`, `boto3`, `svix` |
| `.samignore` | New — excludes secrets and cache from SAM zip |

---

## How it works

### Two webhook triggers
1. **guest.updated** — if the `blocklisted` tag is newly added to a guest, finds ALL their
   reservations (past/current/future) and sets the `Blacklisted` custom field on each one
2. **reservation.new** — if a new booking comes in from a blocklisted guest, sets the
   `Blacklisted` custom field immediately before access codes are sent

### Token cache
- **Locally** → cached to `.token_cache.json` on disk (unchanged)
- **In Lambda** → cached to AWS SSM Parameter Store at `/guesty/token_cache`
- Detected automatically via the `AWS_LAMBDA_FUNCTION_NAME` environment variable

### Signature verification
- Guesty uses **Svix** for webhook delivery
- Each request includes headers: `svix-id`, `svix-timestamp`, `svix-signature`
- Verified using the `svix` Python library
- Skipped if `GUESTY_WEBHOOK_SECRET` is not set (safe for initial setup)

---

## Remaining deployment steps

### Step 1 — Verify AWS credentials
```powershell
aws sts get-caller-identity
```
Should print your AWS account ID. If not, run `aws configure` first.

### Step 2 — Put Guesty credentials in SSM
```powershell
aws ssm put-parameter --name /guesty/client_id     --value "YOUR_GUESTY_CLIENT_ID"     --type SecureString
aws ssm put-parameter --name /guesty/client_secret --value "YOUR_GUESTY_CLIENT_SECRET"  --type SecureString
```
Skip `/guesty/webhook_secret` for now — you get that after deploy.

### Step 3 — Build
```powershell
cd "C:\Users\Yu Peng Lin\Desktop\Guesty-API"
sam build
```

### Step 4 — Deploy
```powershell
sam deploy --guided
```
Answer the prompts:
- Stack Name: `guesty-webhook`
- AWS Region: `us-east-1` (or your preferred region)
- Confirm changes before deploy: `Y`
- Allow SAM to create IAM roles: `Y`
- Save arguments to samconfig.toml: `Y`

At the end, SAM prints your webhook URL:
```
Outputs:
  WebhookUrl  https://<id>.execute-api.us-east-1.amazonaws.com/prod/webhook
```

### Step 5 — Register the webhook URL with Guesty
Get a Guesty Bearer token first (run `main.py` locally and copy the token from `.token_cache.json`),
then call:

```bash
curl -X POST https://open-api.guesty.com/v1/webhooks \
  -H "Authorization: Bearer YOUR_GUESTY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://<your-api-gateway-id>.execute-api.us-east-1.amazonaws.com/prod/webhook",
    "events": ["guest.updated", "guest.created", "guest.deleted", "reservation.new"]
  }'
```

### Step 6 — Retrieve the Svix webhook secret
```bash
curl "https://open-api.guesty.com/v1/webhooks-v2/secret?url=https://<your-url>/webhook" \
  -H "Authorization: Bearer YOUR_GUESTY_TOKEN"
```
Returns a secret like `whsec_xxxxxxxxxxxxxxxx`.

### Step 7 — Add the webhook secret to SSM
```powershell
aws ssm put-parameter --name /guesty/webhook_secret --value "whsec_xxxx" --type SecureString
```
Signature verification activates automatically — no redeployment needed.

### Step 8 — Verify everything is working
```powershell
# Hit the health check
curl https://<your-url>/prod/health
# Expected: {"status": "healthy"}

# Watch live Lambda logs
sam logs -n guesty-webhook --tail
```

---

## Environment variables (set in template.yaml, pulled from SSM at deploy time)

| Variable | SSM Parameter | Description |
|----------|--------------|-------------|
| `GUESTY_CLIENT_ID` | `/guesty/client_id` | Guesty OAuth client ID |
| `GUESTY_CLIENT_SECRET` | `/guesty/client_secret` | Guesty OAuth client secret |
| `GUESTY_WEBHOOK_SECRET` | `/guesty/webhook_secret` | Svix signing secret (add after deploy) |
| `TOKEN_SSM_PARAM` | — | SSM path for token cache (default: `/guesty/token_cache`) |
| `GUESTY_BASE_URL` | — | `https://open-api.guesty.com` |
| `GUESTY_TOKEN_URL` | — | `https://open-api.guesty.com/oauth2/token` |

---

## Subsequent deploys (after first time)
```powershell
sam build && sam deploy
```

---

## Notes
- Lambda timeout is set to 30 seconds in `template.yaml`. If a blocklisted guest has a very
  large number of reservations and the function times out, the fix is to offload processing
  to SQS. Raise this if it becomes an issue.
- `webhook_server.py` is kept intact — local dev with Flask still works as before.
- Guesty limits OAuth token renewals to 3 times per 24 hours. The SSM token cache ensures
  Lambda stays within this limit across concurrent invocations.
