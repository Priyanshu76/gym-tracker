# Deploying to production (OCI)

This covers the one-time server setup. None of this can be done from here —
it needs your actual OCI instance and GitHub repo access.

## 1. Server setup (new OCI instance, per your plan — different IP than the n8n box)

```bash
# On the new OCI instance:
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER   # log out/in after this
git clone -b prod https://github.com/Priyanshu76/gym-tracker.git
cd gym-tracker
cp .env.example .env   # fill in real production values — see below
```

## 2. Production `.env` values that differ from local dev

- `POSTGRES_PASSWORD` — generate fresh with `openssl rand -hex 32`, don't reuse the local dev one
- `JWT_SECRET_KEY` / `ADMIN_CREATE_USER_KEY` — generate fresh, separate from local dev's
- `ENVIRONMENT=production` — this hides `/api/docs` and switches the login cookie to `Secure` (HTTPS-only)
- `SITE_BASE_URL` — your real domain once it's pointed at this server
- `SMTP_*` — your real Gmail App Password credentials

## 3. First deploy (manual, one time)

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Confirm it's up: `curl http://localhost:8000/api/health`

## 4. Reverse proxy (Caddy, matching your existing n8n box's pattern)

Point Caddy at `localhost:8000` the same way it's already set up for n8n —
this repo doesn't manage Caddy config since that's host-level, not app-level.

## 5. Set these GitHub repo secrets (Settings → Secrets and variables → Actions)

For the CD workflow (`.github/workflows/cd-deploy.yml`) to actually be able to deploy:

| Secret | Value |
|---|---|
| `OCI_HOST` | the new instance's IP or hostname |
| `OCI_SSH_USER` | the SSH user to deploy as |
| `OCI_SSH_KEY` | a private key whose public half is in that user's `~/.ssh/authorized_keys` |
| `OCI_DEPLOY_PATH` | absolute path to the repo checkout, e.g. `/home/ubuntu/gym-tracker` |

Once these are set, merging `dev` → `prod` will automatically SSH in, pull the
latest `prod`, and rebuild — no manual redeploy step needed going forward.

## What I could not do from here

I have no access to your OCI instance, so steps 1, 3, 4, and the actual
GitHub secrets in step 5 all need you to do them directly. Everything else
(the workflow file, the production compose file, this doc) is ready to use
the moment those exist.
