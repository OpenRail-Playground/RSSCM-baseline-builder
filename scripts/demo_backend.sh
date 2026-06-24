#!/usr/bin/env bash
# Start the RSSCM Django backend for the demo, with an admin user.
#
# Uses a local venv with only the runtime deps, so it avoids the project's
# `pygraphviz` dependency (which needs system graphviz headers and is only used
# for ER-diagram generation, not the API or admin).
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
RSSCM="${RSSCM_DIR:-$HERE/../RSSCM}"
VENV="$HERE/.demo-venv"

if [ ! -d "$RSSCM/rsscm" ]; then
  echo "Could not find the RSSCM backend at: $RSSCM"
  echo "Set RSSCM_DIR=/path/to/RSSCM and retry."
  exit 1
fi

if [ ! -d "$VENV" ]; then
  echo "Creating demo venv at $VENV ..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q "django>=5.2" django-ninja django-extensions
fi

# The /graph view imports pygraphviz at startup, so it must be installed.
# pygraphviz needs the system graphviz library (brew install graphviz).
if ! "$VENV/bin/python" -c "import pygraphviz" 2>/dev/null; then
  if command -v brew >/dev/null 2>&1 && brew --prefix graphviz >/dev/null 2>&1; then
    GVIZ="$(brew --prefix graphviz)"
    echo "Installing pygraphviz against $GVIZ ..."
    CFLAGS="-I$GVIZ/include" LDFLAGS="-L$GVIZ/lib" "$VENV/bin/pip" install -q "pygraphviz>=1.14"
  else
    echo "ERROR: system graphviz not found. Install it first:  brew install graphviz"
    echo "       then re-run this script."
    exit 1
  fi
fi

cd "$RSSCM/rsscm"
"$VENV/bin/python" manage.py migrate

# Create the demo admin if it does not exist yet (idempotent).
DJANGO_SUPERUSER_PASSWORD="${ADMIN_PASSWORD:-hack4rail2026}" \
  "$VENV/bin/python" manage.py createsuperuser --noinput \
  --username "${ADMIN_USER:-admin}" --email admin@hack4rail.org 2>/dev/null \
  && echo "Created admin user." || echo "Admin user already exists."

echo "Backend starting on http://127.0.0.1:8000  (admin at /admin/)"
exec "$VENV/bin/python" manage.py runserver 127.0.0.1:8000
