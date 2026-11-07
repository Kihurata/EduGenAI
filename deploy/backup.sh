#!/bin/sh
# Nightly Postgres backup to Cloud Storage, keeping the last 14 local dumps. Cron on the VM:
#   15 3 * * * cd ~/edugen && ./backup.sh >> backup.log 2>&1
# Needs BACKUP_BUCKET (gs://...) in the environment or .env, and the VM's service account allowed to write to it.
set -eu
cd "$(dirname "$0")"
[ -f .env ] && BACKUP_BUCKET="${BACKUP_BUCKET:-$(sed -n 's/^BACKUP_BUCKET=//p' .env)}"
mkdir -p backups
file="backups/edugen-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U edugen -d edugen --no-owner | gzip > "$file"
if [ -n "${BACKUP_BUCKET:-}" ]; then
  gcloud storage cp "$file" "$BACKUP_BUCKET/"
fi
ls -1t backups/edugen-*.sql.gz | tail -n +15 | xargs -r rm --
echo "backup ok: $file"
