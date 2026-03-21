# Lambda Deployment Guide

## Prerequisites
- AWS account with permissions to create Lambda, API Gateway, SSM, and IAM roles
- AWS CLI installed and configured (`aws configure`)

---

## Step 1 — Store secrets in SSM Parameter Store

Run these once in your terminal (replace the placeholder values):

```bash
aws ssm put-parameter --name /guesty/client_id      --value "YOUR_CLIENT_ID"      --type SecureString
aws ssm put-parameter --name /guesty/client_secret  --value "YOUR_CLIENT_SECRET"  --type SecureString
aws ssm put-parameter --name /guesty/webhook_secret --value "YOUR_WEBHOOK_SECRET" --type SecureString
```

> The token cache parameter (`/guesty/token_cache`) is created automatically by
> the Lambda on its first run — you don't need to create it manually.

---

## Step 2 — Build the deployment ZIP

Run this from the project root. It installs dependencies into a `package/`
folder and zips everything together.

```bash
# Install dependencies into a staging folder
pip install -r requirements.txt --target package/ --upgrade

# Copy all project .py files into the staging folder
copy *.py package\

# Zip the staging folder contents (not the folder itself)
cd package
zip -r ../guesty_lambda.zip .
cd ..
```

On Windows PowerShell:
```powershell
pip install -r requirements.txt --target package/ --upgrade
Copy-Item *.py package\
Compress-Archive -Path package\* -DestinationPath guesty_lambda.zip -Force
```

---

## Step 3a — Deploy via AWS Console (manual ZIP upload)

1. Go to **AWS Console → Lambda → Create function**
2. Choose **Author from scratch**
   - Function name: `guesty-webhook`
   - Runtime: `Python 3.12`
   - Architecture: `x86_64`
3. Click **Create function**
4. Under **Code source**, click **Upload from → .zip file** and upload `guesty_lambda.zip`
5. Set the **Handler** to: `lambda_handler.handler`
6. Under **Configuration → Environment variables**, add:

   | Key | Value |
   |-----|-------|
   | `GUESTY_CLIENT_ID` | Your Guesty client ID |
   | `GUESTY_CLIENT_SECRET` | Your Guesty client secret |
   | `GUESTY_WEBHOOK_SECRET` | Your webhook signing secret |
   | `TOKEN_CACHE_SSM_PARAM` | `/guesty/token_cache` |
   | `LOG_LEVEL` | `INFO` |

7. Under **Configuration → General configuration**:
   - Timeout: `30 seconds`
   - Memory: `128 MB`
8. Under **Configuration → Permissions**, attach an IAM policy that allows:
   - `ssm:GetParameter` on `arn:aws:ssm:*:*:parameter/guesty/*`
   - `ssm:PutParameter` on `arn:aws:ssm:*:*:parameter/guesty/token_cache`

---

## Step 3b — Deploy via AWS SAM (recommended for repeatable deploys)

```bash
# Install SAM CLI: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html

sam build
sam deploy --guided   # first run — follow the prompts to set region, stack name, S3 bucket
                      # subsequent runs: sam deploy
```

SAM outputs the public URL at the end:
```
WebhookUrl: https://<id>.execute-api.<region>.amazonaws.com/webhook
```

---

## Step 4 — Add an API Gateway trigger

### Via Console (if you used the manual ZIP method):
1. In your Lambda function, click **Add trigger**
2. Select **API Gateway**
3. Choose **Create a new API → HTTP API**
4. Security: **Open** (signature verification is handled in code)
5. Click **Add**
6. Copy the endpoint URL — it ends in `/default`; change it to `/webhook`

---

## Step 5 — Register the endpoint in Guesty

Go to **Guesty Dashboard → Integrations → Webhooks** and add:

```
https://<your-api-gateway-id>.execute-api.<region>.amazonaws.com/webhook
```

Subscribe to these four events:

| Event | Purpose |
|-------|---------|
| `guest.updated` | Detects when the `blocklisted` tag is added |
| `guest.created` | Catches guests imported with the tag already present |
| `guest.deleted` | Audit log |
| `reservation.new` | Flags new bookings from blocklisted guests immediately |

---

## Step 6 — Verify it's working

```bash
# Health check
curl https://<your-url>/health
# → {"status": "healthy"}

# Check Lambda logs
aws logs tail /aws/lambda/guesty-webhook --follow
```

---

## How the token cache works

```
Cold start (new Lambda container):
  auth.py → checks in-memory cache (empty) → reads SSM → if expired → fetches from Guesty → writes SSM

Warm invocation (same container reused):
  auth.py → checks in-memory cache (hit!) → returns immediately (no SSM call, no Guesty call)

New cold start (different container):
  auth.py → checks in-memory cache (empty) → reads SSM (token still valid!) → warms memory → returns
```

This means Guesty's 3-per-24h token limit is never hit in normal operation.
