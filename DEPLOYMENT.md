# Guesty Webhook — AWS Lambda Deployment Guide

## What was built

A Lambda function that receives Guesty webhook events via API Gateway, verifies Svix signatures,
and runs blocklist logic to flag reservations when a guest is tagged `blocklisted`.

| File | Purpose |
|------|---------|
| `lambda_handler.py` | Lambda entry point — routes events, verifies signatures |
| `auth.py` | OAuth token management — SSM cache in Lambda, disk cache locally |
| `blocklist_workflow.py` | Core business logic — confirms tag, fetches reservations, sets custom fields |
| `template.yaml` | AWS SAM template — Lambda + API Gateway + SSM parameter |
| `requirements.txt` | Python dependencies |

---

## How it works

### Webhook events handled
| Event | Action |
|-------|--------|
| `guest.updated` | If `blocklisted` tag newly added → flag all current/future reservations |
| `guest.created` | If new guest already tagged `blocklisted` → flag all reservations |
| `guest.deleted` | Logs deletion, no action |
| `reservation.new` | If guest is blocklisted → flag the new reservation immediately |

### Token cache
- **In Lambda** → cached to SSM Parameter Store at `/guesty/token_cache`
- **Locally** → cached to `.token_cache.json` on disk
- Detected automatically via `AWS_LAMBDA_FUNCTION_NAME` environment variable

### Signature verification
- Guesty uses **Svix** for webhook delivery
- Each request includes: `svix-id`, `svix-timestamp`, `svix-signature` headers
- Verified using the `svix` Python library
- Skipped silently if `GUESTY_WEBHOOK_SECRET` is not set (safe for initial setup)

---

## Prerequisites

- AWS CLI installed and configured (`aws configure`)
- AWS SAM CLI installed (`sam --version`)
- IAM user must have sufficient permissions — **AdministratorAccess** is the simplest option.
  If using least-privilege, the user needs: `s3:*`, `cloudformation:*`, `lambda:*`,
  `apigateway:*`, `ssm:*`, `iam:CreateRole`, `iam:AttachRolePolicy`, `iam:PassRole`

Verify your credentials:
```powershell
aws sts get-caller-identity
```

---

## Step 1 — Create SSM parameters

> **IMPORTANT:** Parameters MUST be type `String`, not `SecureString`.
> CloudFormation cannot resolve `SecureString` parameters at deploy time
> (`AWS::SSM::Parameter::Value<String>` only supports plain `String`).

```powershell
aws ssm put-parameter --name /guesty/client_id     --value "YOUR_GUESTY_CLIENT_ID"     --type String
aws ssm put-parameter --name /guesty/client_secret --value "YOUR_GUESTY_CLIENT_SECRET"  --type String
aws ssm put-parameter --name /guesty/webhook_secret --value "placeholder"               --type String
```

Get your `client_id` and `client_secret` from **Guesty Dashboard → Integrations → OAuth Applications**.

The webhook secret stays as `placeholder` until after deploy (see Step 5).

---

## Step 2 — Build

```powershell
sam build
```

Expected output:
```
Build Succeeded
Built Artifacts  : .aws-sam\build
Built Template   : .aws-sam\build\template.yaml
```

---

## Step 3 — Deploy (first time)

```powershell
sam deploy --guided
```

Answer the prompts exactly as follows:

| Prompt | Answer |
|--------|--------|
| Stack Name | `guesty-webhook` |
| AWS Region | `us-east-1` (or your region) |
| Parameter GuestyClientId | press Enter (uses `/guesty/client_id`) |
| Parameter GuestyClientSecret | press Enter (uses `/guesty/client_secret`) |
| Parameter GuestyWebhookSecret | press Enter (uses `/guesty/webhook_secret`) |
| Parameter LogLevel | press Enter (uses `INFO`) |
| Confirm changes before deploy | `y` |
| Allow SAM CLI IAM role creation | `y` |
| Disable rollback | `n` |
| GuestyWebhookFunction has no authentication. Is this okay? | **type `y`** (default is No — must type it) |
| GuestyWebhookFunction has no authentication. Is this okay? | **type `y`** (appears twice) |
| Save arguments to configuration file | press Enter (`Y`) |
| SAM configuration file | press Enter (`samconfig.toml`) — **do not type `y` here** |
| SAM configuration environment | press Enter (`default`) |

Then review the changeset and type `y` to deploy:
```
Deploy this changeset? [y/N]: y
```

### Troubleshooting deploy failures

**If you see:** `Stack aws-sam-cli-managed-default is missing Tags and/or Outputs... ROLLBACK_COMPLETE`

A previous failed attempt left a broken stack. Delete it and retry:
```powershell
aws cloudformation delete-stack --stack-name aws-sam-cli-managed-default
# Wait ~30 seconds, then:
sam deploy --guided
```

**If you see:** `Parameters [...] have types not supported by CloudFormation`

Your SSM parameters were created as `SecureString`. Recreate them as `String`:
```powershell
aws ssm put-parameter --name /guesty/client_id      --value "YOUR_ID"     --type String --overwrite
aws ssm put-parameter --name /guesty/client_secret  --value "YOUR_SECRET" --type String --overwrite
aws ssm put-parameter --name /guesty/webhook_secret --value "placeholder"  --type String --overwrite
```

---

## Step 4 — Get your deployed URLs

```powershell
aws cloudformation describe-stacks --stack-name guesty-webhook --query "Stacks[0].Outputs" --output table
```

Note the `WebhookUrl` — you need it for the next steps.

---

## Step 5 — Register the webhook with Guesty and get the signing secret

Guesty has no UI for webhook management — this must be done via API.

**Get an OAuth token:**
```powershell
$clientId = aws ssm get-parameter --name /guesty/client_id --query Parameter.Value --output text
$clientSecret = aws ssm get-parameter --name /guesty/client_secret --query Parameter.Value --output text
$tokenResponse = Invoke-RestMethod -Method Post -Uri "https://open-api.guesty.com/oauth2/token" -ContentType "application/x-www-form-urlencoded" -Body "grant_type=client_credentials&client_id=$clientId&client_secret=$clientSecret"
$token = $tokenResponse.access_token
```

**Register the webhook URL** (subscribe to events):
```powershell
$body = @{
    url = "YOUR_WEBHOOK_URL"
    events = @("guest.updated", "guest.created", "guest.deleted", "reservation.new")
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "https://open-api.guesty.com/v1/webhooks" -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json" -Body $body
```

A successful response returns a JSON object with `_id`, `accountId`, `url`, and `events`.

**Get the Svix signing secret:**
```powershell
Invoke-RestMethod -Method Get -Uri "https://open-api.guesty.com/v1/webhooks-v2/secret?url=YOUR_WEBHOOK_URL" -Headers @{ Authorization = "Bearer $token" }
```

Returns a secret beginning with `whsec_`.

**Store the secret in SSM:**
```powershell
aws ssm put-parameter --name /guesty/webhook_secret --value "whsec_YOUR_SECRET_HERE" --type String --overwrite
```

Signature verification activates automatically on the next webhook delivery — no redeployment needed.

---

## Step 6 — Verify everything is working

**Health check** — open in browser or run:
```powershell
Invoke-RestMethod -Uri "YOUR_HEALTH_URL"
```
Expected: `{"status":"healthy"}`

**CloudWatch logs** — the log group `/aws/lambda/guesty-webhook` is created on first invocation.
If you don't see it yet, hit the health URL first to trigger an invocation, then wait 30 seconds.

Navigate to: **AWS Console → CloudWatch → Log Groups → `/aws/lambda/guesty-webhook`**

Or tail logs from the terminal:
```powershell
sam logs -n guesty-webhook --tail
```

---

## Subsequent deploys

`samconfig.toml` saves all your settings. Future deploys are just:

```powershell
sam build; sam deploy
```

---

## Redeploying after stack deletion

If you delete and recreate the stack, API Gateway generates a new ID and your webhook URL changes. You must re-register with Guesty:

**Step 1 — Get new URLs:**
```powershell
aws cloudformation describe-stacks --stack-name guesty-webhook --query "Stacks[0].Outputs" --output table
```

**Step 2 — Get a token from SSM cache** (avoids hitting the token rate limit of 3/day):
```powershell
$cached = aws ssm get-parameter --name /guesty/token_cache --query Parameter.Value --output text --with-decryption | ConvertFrom-Json
$token = $cached.token
```

> Note: the token cache SSM parameter is written as `SecureString` by `auth.py` — always use `--with-decryption` when reading it.

**Step 3 — Delete the old webhook registration:**
```powershell
Invoke-RestMethod -Method Delete -Uri "https://open-api.guesty.com/v1/webhooks/OLD_WEBHOOK_ID" -Headers @{ Authorization = "Bearer $token" }
```

**Step 4 — Register the new URL:**
```powershell
$body = @{
    url = "YOUR_NEW_WEBHOOK_URL"
    events = @("guest.updated", "guest.created", "guest.deleted", "reservation.new")
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "https://open-api.guesty.com/v1/webhooks" -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json" -Body $body
```

**Step 5 — Get the new Svix secret** (returns an object — extract `.key`):
```powershell
$secret = Invoke-RestMethod -Method Get -Uri "https://open-api.guesty.com/v1/webhooks-v2/secret?url=YOUR_NEW_WEBHOOK_URL" -Headers @{ Authorization = "Bearer $token" }
aws ssm put-parameter --name /guesty/webhook_secret --value "$($secret.key)" --type String --overwrite
```

> The `.key` property is critical — storing the whole object causes `Incorrect padding` errors in Svix signature verification.

**Step 6 — Redeploy to inject the new secret into Lambda env vars:**
```powershell
sam deploy
```

> The webhook secret is baked into Lambda environment variables at deploy time via `AWS::SSM::Parameter::Value<String>`. Updating SSM alone is not enough — a redeploy is required.

---

## Monitoring with CloudWatch

Log group: `/aws/lambda/guesty-webhook`

> The log group is only created on the **first Lambda invocation**. Hit the health URL in a browser to trigger it if it doesn't appear.

**AWS Console → CloudWatch → Log Insights** — useful queries:

All recent activity:
```
fields @timestamp, @message
| sort @timestamp desc
| limit 50
```

Blocklist events only:
```
fields @timestamp, @message
| filter @message like /blocklist/ or @message like /\[OK\]/ or @message like /\[FAIL\]/ or @message like /Blacklisted/
| sort @timestamp desc
| limit 50
```

Invocation statistics:
```
filter @type = "REPORT"
| stats count() as totalInvocations,
        sum(@billedDuration) as totalBilledMs,
        avg(@duration) as avgDurationMs,
        max(@duration) as maxDurationMs,
        avg(@maxMemoryUsed) / 1024 / 1024 as avgMemoryUsedMB
```

Tail live logs from terminal:
```powershell
sam logs -n guesty-webhook --tail
```

Set log retention to avoid unnecessary storage costs:
```powershell
aws logs put-retention-policy --log-group-name /aws/lambda/guesty-webhook --retention-in-days 30
```

---

## Environment variables

Set in `template.yaml`, resolved from SSM at deploy time:

| Variable | SSM Parameter | Description |
|----------|--------------|-------------|
| `GUESTY_CLIENT_ID` | `/guesty/client_id` | Guesty OAuth client ID |
| `GUESTY_CLIENT_SECRET` | `/guesty/client_secret` | Guesty OAuth client secret |
| `GUESTY_WEBHOOK_SECRET` | `/guesty/webhook_secret` | Svix signing secret |
| `TOKEN_SSM_PARAM` | — | SSM path for token cache (`/guesty/token_cache`) |
| `GUESTY_BASE_URL` | — | `https://open-api.guesty.com` |
| `GUESTY_TOKEN_URL` | — | `https://open-api.guesty.com/oauth2/token` |

---

## Notes

- Lambda timeout is 30 seconds. If a blocklisted guest has a very large number of reservations
  and the function times out, consider offloading to SQS.
- Guesty limits OAuth token renewals to 3 times per 24 hours. The SSM token cache ensures
  Lambda stays within this limit across concurrent invocations.
- `webhook_server.py` (Flask) is kept intact for local development.
- SSM parameters are plain `String` type by design — CloudFormation cannot resolve `SecureString`.
  Consider restricting IAM access to these parameters to compensate.
