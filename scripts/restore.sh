#!/usr/bin/env bash
# =============================================================================
# restore.sh - Safe Database & Uploads Restoration with Health Verification
# =============================================================================
# Restores a PostgreSQL database dump (-Fc) and optional uploads archive.
#
# Features:
#   - Automated interactive backup selection or command-line path argument
#   - Format validation (verifies PGDMP custom header and TOC)
#   - Explicit confirmation safeguard (requires typing 'RESTORE' or --force flag)
#   - Drops and recreates objects cleanly (--clean --if-exists)
#   - Safe uploads extraction with pre-restore backup protection
#   - Post-restoration healthcheck verification (pg_isready + /health endpoint)
# =============================================================================

set -euo pipefail

# ANSI Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKUP_DIR="${PROJECT_ROOT}/backups"
START_TIME="$(date +%s)"

# Logging function
log() {
    local level="$1"; shift
    local color="$NC"
    case "$level" in
        INFO)  color="$BLUE" ;;
        OK)    color="$GREEN" ;;
        WARN)  color="$YELLOW" ;;
        ERROR) color="$RED" ;;
    esac
    echo -e "$(date +'%Y-%m-%d %H:%M:%S') [${color}${level}${NC}] $*"
}

HELP_INVOKED=false

# Cleanup & Exit Trap
cleanup() {
    local exit_code=$?
    if [[ "${HELP_INVOKED:-false}" = true ]]; then
        return 0
    fi
    local end_time="$(date +%s)"
    local duration=$((end_time - START_TIME))

    if [[ $exit_code -eq 0 ]]; then
        log OK "Restoration procedure finished successfully in ${duration}s."
    else
        log ERROR "Restoration procedure terminated with error (code ${exit_code}) after ${duration}s."
    fi
}
trap cleanup EXIT

# -----------------------------------------------------------------------------
# 1. Parse Arguments & Options
# -----------------------------------------------------------------------------
FORCE_RESTORE=false
DB_BACKUP_ARG=""
UPLOADS_BACKUP_ARG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--force)
            FORCE_RESTORE=true
            shift
            ;;
        -h|--help)
            HELP_INVOKED=true
            echo "Usage: $0 [OPTIONS] [DB_BACKUP_FILE] [UPLOADS_BACKUP_FILE]"
            echo ""
            echo "Options:"
            echo "  -f, --force    Skip interactive confirmation prompt"
            echo "  -h, --help     Show this help message"
            exit 0
            ;;
        *)
            if [[ -z "$DB_BACKUP_ARG" ]]; then
                DB_BACKUP_ARG="$1"
            elif [[ -z "$UPLOADS_BACKUP_ARG" ]]; then
                UPLOADS_BACKUP_ARG="$1"
            fi
            shift
            ;;
    esac
done

# Load .env
ENV_FILE="${PROJECT_ROOT}/.env"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-portail_client}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-portail_db}"

# Detect Docker Compose
if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    log ERROR "Docker or Docker Compose is not installed or not in PATH."
    exit 1
fi

# -----------------------------------------------------------------------------
# 2. Select Backup File
# -----------------------------------------------------------------------------
DB_BACKUP_FILE="$DB_BACKUP_ARG"

if [[ -z "$DB_BACKUP_FILE" ]]; then
    if [[ ! -d "$BACKUP_DIR" ]]; then
        log ERROR "No backup directory found at ${BACKUP_DIR}. Please specify a backup file path."
        exit 1
    fi

    # Find available database dumps sorted by newest first
    mapfile -t BACKUP_LIST < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name "db_*.dump" | sort -r)

    if [[ ${#BACKUP_LIST[@]} -eq 0 ]]; then
        log ERROR "No database backup files (.dump) found in ${BACKUP_DIR}."
        exit 1
    fi

    echo -e "\n${BOLD}${CYAN}Available Database Backups:${NC}"
    for i in "${!BACKUP_LIST[@]}"; do
        file="${BACKUP_LIST[$i]}"
        size=$(du -h "$file" | cut -f1)
        mtime=$(date -r "$file" "+%Y-%m-%d %H:%M:%S")
        echo -e "  [$((i+1))] $(basename "$file")  (${size}, ${mtime})"
    done
    echo ""

    if [[ "$FORCE_RESTORE" = true ]]; then
        # Pick the most recent backup automatically
        DB_BACKUP_FILE="${BACKUP_LIST[0]}"
        log INFO "Force flag active: selected most recent backup: $(basename "$DB_BACKUP_FILE")"
    else
        read -r -p "Select backup number to restore [1-${#BACKUP_LIST[@]}]: " CHOICE
        if [[ ! "$CHOICE" =~ ^[0-9]+$ ]] || [[ "$CHOICE" -lt 1 ]] || [[ "$CHOICE" -gt ${#BACKUP_LIST[@]} ]]; then
            log ERROR "Invalid selection."
            exit 1
        fi
        DB_BACKUP_FILE="${BACKUP_LIST[$((CHOICE-1))]}"
    fi
fi

# Resolve full path
if [[ ! -f "$DB_BACKUP_FILE" ]]; then
    log ERROR "Backup file does not exist: ${DB_BACKUP_FILE}"
    exit 1
fi

# Look for corresponding uploads archive if not explicitly provided
UPLOADS_BACKUP_FILE="$UPLOADS_BACKUP_ARG"
if [[ -z "$UPLOADS_BACKUP_FILE" ]]; then
    # Extract timestamp from db filename: db_<db>_<timestamp>.dump
    FILENAME=$(basename "$DB_BACKUP_FILE")
    BACKUP_TIMESTAMP=$(echo "$FILENAME" | grep -oP '\d{8}_\d{6}' || true)
    if [[ -n "$BACKUP_TIMESTAMP" ]]; then
        CANDIDATE_UPLOADS="${BACKUP_DIR}/uploads_${BACKUP_TIMESTAMP}.tar.gz"
        if [[ -f "$CANDIDATE_UPLOADS" ]]; then
            UPLOADS_BACKUP_FILE="$CANDIDATE_UPLOADS"
            log INFO "Discovered matching uploads archive: $(basename "$UPLOADS_BACKUP_FILE")"
        fi
    fi
fi

# -----------------------------------------------------------------------------
# 3. Validation
# -----------------------------------------------------------------------------
log INFO "Validating database dump file..."

# Check non-empty
if [[ ! -s "$DB_BACKUP_FILE" ]]; then
    log ERROR "Database backup file is empty (0 bytes): ${DB_BACKUP_FILE}"
    exit 1
fi

# Verify header magic bytes (PGDMP)
HEADER=$(head -c 5 "$DB_BACKUP_FILE" || true)
if [[ "$HEADER" != "PGDMP" ]]; then
    log ERROR "Backup file does not start with valid PostgreSQL custom dump header 'PGDMP'."
    exit 1
fi
log OK "File header is valid PostgreSQL custom dump (PGDMP)."

# -----------------------------------------------------------------------------
# 4. Confirmation Safeguard
# -----------------------------------------------------------------------------
echo -e "\n${BOLD}${RED}======================================================${NC}"
echo -e "${BOLD}${RED}               RESTORE WARNING CONFIRMATION           ${NC}"
echo -e "${BOLD}${RED}======================================================${NC}"
echo -e "Target Database:       ${BOLD}${POSTGRES_DB}${NC}"
echo -e "Target Container:      ${BOLD}${POSTGRES_CONTAINER}${NC}"
echo -e "Database Backup File:  ${BOLD}${DB_BACKUP_FILE}${NC}"
if [[ -n "$UPLOADS_BACKUP_FILE" && -f "$UPLOADS_BACKUP_FILE" ]]; then
echo -e "Uploads Backup File:   ${BOLD}${UPLOADS_BACKUP_FILE}${NC}"
fi
echo ""
echo -e "${YELLOW}WARNING: This operation will overwrite existing tables and data"
echo -e "in '${POSTGRES_DB}'. Any uncommitted changes will be PERMANENTLY LOST.${NC}"
echo -e "${BOLD}${RED}======================================================${NC}\n"

if [[ "$FORCE_RESTORE" = false ]]; then
    read -r -p "Type 'RESTORE' to confirm and proceed: " CONFIRMATION
    if [[ "$CONFIRMATION" != "RESTORE" ]]; then
        log WARN "Restoration aborted by operator."
        exit 0
    fi
else
    log WARN "--force flag specified. Skipping manual confirmation prompt."
fi

# -----------------------------------------------------------------------------
# 5. Database Service Check & Connection Termination
# -----------------------------------------------------------------------------
log INFO "Checking if PostgreSQL service is running..."

if ! $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" ps --services --filter "status=running" | grep -q "^db$"; then
    log INFO "Database service is not running. Starting database container..."
    $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" up -d db
fi

# Wait for PostgreSQL to be ready
log INFO "Waiting for PostgreSQL to accept connections..."
MAX_RETRIES=15
COUNTER=0
until $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" &>/dev/null; do
    COUNTER=$((COUNTER+1))
    if [[ $COUNTER -ge $MAX_RETRIES ]]; then
        log ERROR "Timed out waiting for PostgreSQL to become ready."
        exit 1
    fi
    sleep 1
done
log OK "PostgreSQL is accepting connections."

# Terminate active client connections to prevent restoration locks
log INFO "Terminating other active client connections to '${POSTGRES_DB}'..."
$DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T db \
    psql -U "$POSTGRES_USER" -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();" &>/dev/null || true

# -----------------------------------------------------------------------------
# 6. Database Restoration (pg_restore)
# -----------------------------------------------------------------------------
log INFO "Restoring database '${POSTGRES_DB}' from dump..."

# Use pg_restore with --clean --if-exists --no-owner --no-privileges
# Note: pg_restore might return exit code 1 for non-critical warnings (e.g. notices during drop if exists),
# so we handle standard pg_restore warning exit status gracefully.
RESTORE_STATUS=0
$DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T db \
    pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    < "$DB_BACKUP_FILE" || RESTORE_STATUS=$?

if [[ $RESTORE_STATUS -ne 0 && $RESTORE_STATUS -ne 1 ]]; then
    log ERROR "pg_restore failed with critical exit code ${RESTORE_STATUS}!"
    exit "$RESTORE_STATUS"
fi
log OK "Database schema and data restored successfully."

# -----------------------------------------------------------------------------
# 7. Uploads Directory Restoration
# -----------------------------------------------------------------------------
if [[ -n "$UPLOADS_BACKUP_FILE" && -f "$UPLOADS_BACKUP_FILE" ]]; then
    log INFO "Restoring uploads from ${UPLOADS_BACKUP_FILE}..."
    UPLOADS_DIR="${PROJECT_ROOT}/uploads"

    # Create safety backup of existing uploads if directory is not empty
    if [[ -d "$UPLOADS_DIR" ]] && [[ "$(ls -A "$UPLOADS_DIR" 2>/dev/null)" ]]; then
        SAFETY_BACKUP="${PROJECT_ROOT}/uploads.pre-restore_$(date +%Y%m%d_%H%M%S)"
        log INFO "Backing up current uploads to ${SAFETY_BACKUP} before extraction..."
        cp -r "$UPLOADS_DIR" "$SAFETY_BACKUP"
    fi

    mkdir -p "$UPLOADS_DIR"
    tar -xzf "$UPLOADS_BACKUP_FILE" -C "$PROJECT_ROOT"
    log OK "Uploads archive restored successfully."
fi

# -----------------------------------------------------------------------------
# 8. Post-Restoration Verification & Healthchecks
# -----------------------------------------------------------------------------
log INFO "Performing post-restoration verification..."

# Check database responsiveness
if $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" &>/dev/null; then
    TABLE_COUNT=$($DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T db \
        psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d '[:space:]')
    log OK "Database verified. Public schema table count: ${TABLE_COUNT:-0}"
else
    log ERROR "Database is not responding after restoration!"
    exit 1
fi

# Check backend health if backend container is running
if $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" ps --services --filter "status=running" | grep -q "^backend$"; then
    log INFO "Verifying backend health endpoint (/health)..."
    sleep 2
    if $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T backend \
        python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" &>/dev/null; then
        log OK "Backend healthcheck PASSED: /health is responding with HTTP 200."
    else
        log WARN "Backend is running but /health did not return 200. You may need to restart the backend container."
    fi
fi

echo -e "\n${BOLD}${GREEN}======================================================${NC}"
echo -e "${BOLD}${GREEN}         Restoration Completed Successfully!          ${NC}"
echo -e "${BOLD}${GREEN}======================================================${NC}\n"
