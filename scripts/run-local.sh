#!/usr/bin/env bash
# =============================================================================
# run-local.sh - Lance l'API SANS Docker (dev local, base SQLite)
# =============================================================================
# Utile quand Docker n'est pas installe. Ce mode :
#   - utilise SQLite (fichier ./portail_local.db) au lieu de PostgreSQL
#   - ne lance ni Caddy ni le conteneur web (le frontend tourne via `npm run dev`)
#   - installe les dependances Python dans ./.local-libs si absent
#
# Le mode de reference reste Docker Compose (voir QUICKSTART.md). Ici, on
# reproduit uniquement le comportement applicatif pour developper vite.
#
# Usage :
#   ./scripts/run-local.sh            # migrations + API sur http://127.0.0.1:8000
#   ./scripts/run-local.sh --migrate  # applique seulement les migrations
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_lib.sh"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_ROOT"

LIBS_DIR="${PROJECT_ROOT}/.local-libs"
SECRET_FILE="${PROJECT_ROOT}/.secret-local"
DB_FILE="${PROJECT_ROOT}/portail_local.db"

# -----------------------------------------------------------------------------
# 1. Dependances Python (dossier autonome, sans venv)
# -----------------------------------------------------------------------------
# Fournit un `python3 -m pip` utilisable, meme sans python3-pip installe :
# on telecharge le .deb (sans root) et on l'extrait dans un dossier prive.
PIP_PP=""
ensure_pip() {
    python3 -m pip --version &>/dev/null && return 0
    log WARN "pip absent du systeme : amorcage local (sans root)..."
    local boot="${PROJECT_ROOT}/.local-libs/_pipboot"
    if [[ ! -f "${boot}/usr/lib/python3/dist-packages/pip/__init__.py" ]]; then
        command -v apt-get &>/dev/null || { log ERROR "Ni pip ni apt-get : installez python3-pip ou utilisez Docker."; exit 1; }
        mkdir -p "$boot" && ( cd "$boot" && apt-get download python3-pip python3-setuptools python3-wheel python3-pkg-resources >/dev/null 2>&1 && for d in *.deb; do dpkg-deb -x "$d" .; done )
    fi
    PIP_PP="${boot}/usr/lib/python3/dist-packages"
    PYTHONPATH="$PIP_PP" python3 -m pip --version &>/dev/null || { log ERROR "Amorcage de pip echoue. Installez python3-pip (sudo apt-get install -y python3-pip)."; exit 1; }
    log OK "pip amorce localement."
}

if [[ ! -d "$LIBS_DIR" ]] || ! ls "$LIBS_DIR"/fastapi* &>/dev/null; then
    log INFO "Installation des dependances Python dans .local-libs/ ..."
    ensure_pip
    PYTHONPATH="${PIP_PP}" python3 -m pip install --quiet --target="$LIBS_DIR" -r backend/requirements.txt
    log OK "Dependances installees."
fi

# -----------------------------------------------------------------------------
# 2. Secret de dev persistant (les jetons survivent aux redemarrages)
# -----------------------------------------------------------------------------
if [[ ! -f "$SECRET_FILE" ]]; then
    (openssl rand -hex 32 2>/dev/null || head -c32 /dev/urandom | od -An -tx1 | tr -d ' \n') > "$SECRET_FILE"
    chmod 600 "$SECRET_FILE"
    log INFO "Secret de dev genere : .secret-local"
fi

# -----------------------------------------------------------------------------
# 3. Environnement applicatif
# -----------------------------------------------------------------------------
export PYTHONPATH="$LIBS_DIR"
export DATABASE_URL="sqlite:///${DB_FILE}"
export ENVIRONMENT="development"
export SECRET_KEY="$(cat "$SECRET_FILE")"
export CORS_ORIGINS="http://localhost:5173"
export BOOTSTRAP_ADMIN_EMAIL="${BOOTSTRAP_ADMIN_EMAIL:-kkram.work@gmail.com}"
export UPLOAD_DIR="${PROJECT_ROOT}/uploads"
export APP_VERSION="1.0.0-local-sqlite"
mkdir -p "$UPLOAD_DIR"

cd "$PROJECT_ROOT/backend"

# -----------------------------------------------------------------------------
# 4. Migrations
# -----------------------------------------------------------------------------
log INFO "Application des migrations Alembic (SQLite : ${DB_FILE})..."
python3 -m alembic upgrade head

if [[ "${1:-}" == "--migrate" ]]; then
    log OK "Migrations appliquees. Arret (option --migrate)."
    exit 0
fi

# -----------------------------------------------------------------------------
# 5. Serveur
# -----------------------------------------------------------------------------
log OK "API sur http://127.0.0.1:8000  (docs : /docs, sante : /health)"
log INFO "Frontend : dans un autre terminal -> make frontend-dev"
exec python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
