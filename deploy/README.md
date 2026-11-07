# Deploy (production)

One Google Compute Engine VM runs everything with Docker Compose. Caddy terminates HTTPS and is the only service with open ports.

| Part | Where |
|---|---|
| Frontend (static React build) | `frontend` container, served by Caddy at `/` |
| Backend (FastAPI) | `backend` container, Caddy routes `/api/*` and `/health` to it |
| Postgres 16 | `db` container, data in the `pgdata` volume on the VM disk; nightly `pg_dump` to Cloud Storage |
| Uploaded files (matrices, sample exams, DOCX) | `storage` volume on the VM disk |
| Vector index | Qdrant Cloud (`QDRANT_URL`, `QDRANT_API_KEY`), cluster in GCP `asia-southeast1` |
| LLM and embeddings | Gemini API (`GEMINI_API_KEY`), `LLM_PROVIDER=gemini` |

Images are `ghcr.io/kihurata/edugenai/backend` and `.../frontend`. CI (`.github/workflows/ci.yml`) builds both on every
push and pull request but **does not publish them or deploy yet**; add a GHCR login and `push: true` to the `images`
job, and a deploy job, when the VM exists. Until then, build locally with `docker compose build`.

## One-time setup

1. **VM**: Compute Engine `e2-medium`, region `asia-southeast1`, Debian 12, 30 GB balanced disk.
   Firewall: allow tcp 80 and 443 from anywhere, tcp 22 only as needed. Reserve a static external IP.
2. **Docker** on the VM: install Docker Engine and the compose plugin (docs.docker.com/engine/install/debian).
   Add the deploy user to the `docker` group.
3. **Domain**: point an A record at the static IP, or use `<ip-with-dashes>.sslip.io`. Caddy gets the certificate on first start.
4. **Files**: `mkdir ~/edugen`, copy `docker-compose.prod.yml`, `Caddyfile`, `backup.sh` there, and create `.env` from `.env.example` (`chmod 600 .env`).
5. **GHCR access**: the auto-deploy job logs the VM in with its own short-lived `GITHUB_TOKEN` and logs out after the
   pull, so no token stays on the VM. For a manual pull, run `docker login ghcr.io` with a `read:packages` token
   first and `docker logout ghcr.io` afterwards.
6. **First start**: `docker compose -f docker-compose.prod.yml up -d`, then open `https://$DOMAIN/health`.
   The one-shot `seed` service creates the first school and admin from the `SEED_*` values in `.env` (see the checklist below).
7. **Backups**: create a bucket, put `BACKUP_BUCKET=gs://...` in `.env`, and add the cron line from `backup.sh`.
8. **Turn on auto-deploy** (GitHub repo settings):
   - secrets `VM_HOST`, `VM_USER`, `VM_SSH_KEY` (a key used only for deploys);
   - variables `DOMAIN` and `DEPLOY_ENABLED=true`.

## First deploy checklist

1. **Secrets in `.env`** (from `.env.example`): `DOMAIN`, `POSTGRES_PASSWORD`, `JWT_SECRET`, `GEMINI_API_KEY`,
   `QDRANT_URL`, `QDRANT_API_KEY` (Qdrant Cloud, needed by a human), and `SEED_SCHOOL_CODE`, `SEED_SCHOOL_NAME`,
   `SEED_ADMIN_EMAIL`, `SEED_ADMIN_NAME`, `SEED_ADMIN_PASSWORD`. Compose refuses to start if one is missing. The auto-deploy job keeps the VM's existing `.env`, so add `QDRANT_*` and `SEED_*` to it before the first deploy of this version.
2. **Qdrant Cloud index** must already hold the Toán 12 textbooks, embedded with `EMBEDDER=gemini` (same embedder as the
   backend). Run this from a dev machine that has `data/parsed/...` and the same Qdrant Cloud and Gemini keys
   (`data/sources.yaml` also lists grade 10-11 exams, so first make a manifest with only the SGK Toán 12 entries):
   ```
   cd edugen-backend
   python -c "import yaml; d=yaml.safe_load(open('data/sources.yaml',encoding='utf-8')); d['sources']=[s for s in d['sources'] if s['doc_type']=='sgk' and s['subject']=='toan' and s['grade']==12]; yaml.safe_dump(d,open('data/sources-toan12.yaml','w',encoding='utf-8'),allow_unicode=True)"
   QDRANT_URL=... QDRANT_API_KEY=... EMBEDDER=gemini GEMINI_API_KEY=... uv run python -m app.rag.ingest --sources data/sources-toan12.yaml
   ```
   Delete `data/sources-toan12.yaml` afterwards.
3. **Image tag**: production pulls `TAG=main` by default, so `dev` must be merged into `main` first (or set `TAG=dev`
   in `.env` deliberately).
4. `docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d`.
   The `seed` container waits for the backend (migrations done), creates the school and admin, and exits with code 0;
   `docker compose -f docker-compose.prod.yml logs seed` shows the result. Re-running `up -d` leaves existing data alone.
5. Open `https://$DOMAIN` and log in with `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`. Keep the `SEED_*` lines in
   `.env`: compose needs them on every `up`, and the seed is a no-op once the school exists.

## Everyday

- Deploy: merge into `main`. Roll back: set `TAG=sha-<older commit>` in `.env` and run `docker compose -f docker-compose.prod.yml up -d`.
- Logs: `docker compose -f docker-compose.prod.yml logs -f backend`.
- Restore a backup: `gunzip -c backups/<file>.sql.gz | docker compose -f docker-compose.prod.yml exec -T db psql -U edugen -d edugen`.

## Matrix conversion

Gemini is the only matrix reader (D-014): it turns the uploaded image/PDF into JSON, so the image needs no torch or
marker. It uses `GEMINI_API_KEY` and `MATRIX_GEMINI_MODEL`. An old `.env` that still sets `MATRIX_CONVERTER` or
`MARKER_*` keeps working; those values are ignored.

## Hardening in the compose file

- Only Caddy publishes ports. Postgres sits on an `internal` network with no internet route; only the backend joins it.
- The backend runs as an unprivileged user (uid 10001); every container has `no-new-privileges`.
- Memory limits per service (total about 2.9 GB of 4 GB) and log rotation (3 × 10 MB per container).
- Health checks: Caddy starts only after the backend (`/health`) and frontend are healthy.
- Uvicorn trusts `X-Forwarded-For` from Caddy, so the login throttle sees the real client IP.
