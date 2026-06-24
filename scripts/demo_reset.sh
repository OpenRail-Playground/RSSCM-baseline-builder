#!/usr/bin/env bash
# Reset the demo backend to a clean state: empty database + fresh admin user.
# Run this before a live demo if you want to show objects being created from
# scratch. (Flushing removes ALL rows including users, so we recreate the admin.)
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
RSSCM="${RSSCM_DIR:-$HERE/../RSSCM}"
VENV="$HERE/.demo-venv"

cd "$RSSCM/rsscm"
"$VENV/bin/python" manage.py flush --noinput
DJANGO_SUPERUSER_PASSWORD="${ADMIN_PASSWORD:-hack4rail2026}" \
  "$VENV/bin/python" manage.py createsuperuser --noinput \
  --username "${ADMIN_USER:-admin}" --email admin@hack4rail.org 2>/dev/null || true

echo "Reset done: empty DB + admin user (admin / hack4rail2026)."
