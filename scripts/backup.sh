#!/usr/bin/env bash
# =============================================================================
# backup.sh - Production Database & Uploads Backup with 7-Day Retention
# =============================================================================
# Performs:
#   1. pg_dump in custom compressed format (-Fc) directly from PostgreSQL container
#   2. Compressed archive (.tar.gz) of the uploads directory
#   3. Automatic verification of backup file sizes and integrity
#   4. 7-day retention rotation policy (deletes archives older than retention threshold)
#   5. Timestamped, audit-ready logging with duration metrics
# =============================================================================

set -euo pipefail

# ANSI Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# Determine Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKUP_DIR="${PROJECT_ROOT}/backups"
TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
START_TIME="$(date +%s)"

# Logging function with ISO-8601-like timestamp
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
        log OK "Backup completed successfully in ${duration}s."
    else
        log ERROR "Backup failed with exit code ${exit_code} after ${duration}s!"
    fi
}
trap cleanup EXIT

# Parse help flag
for arg in "$@"; do
    case "$arg" in
        -h|--help)
            HELP_INVOKED=true
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Automated PostgreSQL custom dump (-Fc) and uploads archive with 7-day retention rotation."
            echo ""
            echo "Options:"
            echo "  -h, --help    Show this help message"
            exit 0
            ;;
    esac
done

# -----------------------------------------------------------------------------
# 1. Environment & Preflight Checks
# -----------------------------------------------------------------------------
log INFO "Starting backup procedure from ${PROJECT_ROOT}"

# Load environment variables if .env exists
ENV_FILE="${PROJECT_ROOT}/.env"
if [[ -f "$ENV_FILE" ]]; then
    log INFO "Loading configuration from .env"
    # Export only non-comment, valid variable assignments safely
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
else
    log WARN ".env file not found at ${ENV_FILE}. Falling back to default values."
fi

# Set defaults
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-portail_client}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-portail_db}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

# Check Docker Compose command
if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    log ERROR "Docker or Docker Compose is not installed or not in PATH."
    exit 1
fi

# Ensure backup directory exists with restricted permissions (0700)
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# -----------------------------------------------------------------------------
# 2. Database Health Verification
# -----------------------------------------------------------------------------
log INFO "Verifying PostgreSQL container status (${POSTGRES_CONTAINER})..."

if ! $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" ps --services --filter "status=running" | grep -q "^db$"; then
    log ERROR "Database service 'db' (${POSTGRES_CONTAINER}) is not running."
    exit 1
fi

if ! $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" &>/dev/null; then
    log ERROR "PostgreSQL is running but not accepting connections for user '$POSTGRES_USER' and db '$POSTGRES_DB'."
    exit 1
fi
log OK "PostgreSQL database is healthy and ready for dump."

# -----------------------------------------------------------------------------
# 3. PostgreSQL Database Backup (pg_dump -Fc)
# -----------------------------------------------------------------------------
DB_BACKUP_FILE="${BACKUP_DIR}/db_${POSTGRES_DB}_${TIMESTAMP}.dump"
log INFO "Dumping database '${POSTGRES_DB}' into ${DB_BACKUP_FILE}..."

# Use custom format (-Fc) for compression, BLOB support, and granular restore options
$DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T db \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges \
    > "$DB_BACKUP_FILE"

# Validate DB dump file
if [[ ! -s "$DB_BACKUP_FILE" ]]; then
    log ERROR "Database backup file is empty or was not created: ${DB_BACKUP_FILE}"
    rm -f "$DB_BACKUP_FILE"
    exit 1
fi

# Verify header begins with PGDMP magic bytes (0x50 0x47 0x44 0x4D 0x50)
HEADER=$(head -c 5 "$DB_BACKUP_FILE" || true)
if [[ "$HEADER" != "PGDMP" ]]; then
    log ERROR "Backup file header does not match PostgreSQL custom dump format (got '$HEADER')."
    rm -f "$DB_BACKUP_FILE"
    exit 1
fi

DB_SIZE=$(du -h "$DB_BACKUP_FILE" | cut -f1)
log OK "Database backup verified: ${DB_BACKUP_FILE} (${DB_SIZE})"

# -----------------------------------------------------------------------------
# 4. Uploads Volume Backup
# -----------------------------------------------------------------------------
UPLOADS_DIR="${PROJECT_ROOT}/uploads"
UPLOADS_BACKUP_FILE="${BACKUP_DIR}/uploads_${TIMESTAMP}.tar.gz"

if [[ -d "$UPLOADS_DIR" ]]; then
    log INFO "Archiving uploads from ${UPLOADS_DIR}..."
    tar -czf "$UPLOADS_BACKUP_FILE" -C "$PROJECT_ROOT" uploads

    if [[ -s "$UPLOADS_BACKUP_FILE" ]]; then
        UPLOADS_SIZE=$(du -h "$UPLOADS_BACKUP_FILE" | cut -f1)
        log OK "Uploads archive verified: ${UPLOADS_BACKUP_FILE} (${UPLOADS_SIZE})"
    else
        log WARN "Uploads archive was created but is empty."
    fi
else
    log WARN "No uploads directory found at ${UPLOADS_DIR}. Skipping upload archive."
fi

# -----------------------------------------------------------------------------
# 5. Retention Policy (7-Day Rotation)
# -----------------------------------------------------------------------------
log INFO "Applying ${RETENTION_DAYS}-day backup retention rotation..."

# Find and remove expired DB dumps
EXPIRED_DB=$(find "$BACKUP_DIR" -type f -name "db_*.dump" -mtime +"$RETENTION_DAYS" || true)
if [[ -n "$EXPIRED_DB" ]]; then
    while IFS= read -r file; do
        log INFO "Purging expired database dump: $(basename "$file")"
        rm -f "$file"
    done <<< "$EXPIRED_DB"
fi

# Find and remove expired uploads archives
EXPIRED_UPLOADS=$(find "$BACKUP_DIR" -type f -name "uploads_*.tar.gz" -mtime +"$RETENTION_DAYS" || true)
if [[ -n "$EXPIRED_UPLOADS" ]]; then
    while IFS= read -r file; do
        log INFO "Purging expired uploads archive: $(basename "$file")"
        rm -f "$file"
    done <<< "$EXPIRED_UPLOADS"
fi

# -----------------------------------------------------------------------------
# 6. Summary Report
# -----------------------------------------------------------------------------
TOTAL_BACKUPS_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
BACKUP_COUNT=$(find "$BACKUP_DIR" -type f \( -name "*.dump" -o -name "*.tar.gz" \) | wc -l)

echo -e "\n${BOLD}======================================================${NC}"
echo -e "${BOLD}               Backup Summary Report                  ${NC}"
echo -e "${BOLD}======================================================${NC}"
echo "  - Database Dump:    ${DB_BACKUP_FILE} (${DB_SIZE})"
if [[ -f "$UPLOADS_BACKUP_FILE" ]]; then
echo "  - Uploads Archive:  ${UPLOADS_BACKUP_FILE} (${UPLOADS_SIZE})"
fi
echo "  - Total Archives:   ${BACKUP_COUNT} files in ${BACKUP_DIR}"
echo "  - Total Disk Usage: ${TOTAL_BACKUPS_SIZE}"
echo "  - Retention Window: ${RETENTION_DAYS} days"
echo -e "${BOLD}======================================================${NC}\n"
