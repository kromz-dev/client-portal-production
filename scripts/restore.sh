#!/usr/bin/env bash
# =============================================================================
# restore.sh - Restauration securisee de la base et des uploads
# =============================================================================
# Restaure un dump PostgreSQL (-Fc) et, si disponible, l'archive des uploads.
#
# Fonctionnalites :
#   - Selection interactive (plus recent d'abord) ou chemin en argument
#   - Dechiffrement transparent des artefacts .age (via l'identite privee age)
#   - Validation du format (entete PGDMP sur le dump dechiffre)
#   - Garde-fou de confirmation (saisie de 'RESTORE' ou option --force)
#   - Suppression/recreation propre des objets (--clean --if-exists)
#   - Copie de securite des uploads avant extraction
#   - Verification post-restauration (pg_isready + comptage + /health)
#
# L'interface operateur ne change pas : `./scripts/restore.sh` suffit.
# =============================================================================

set -euo pipefail

# ANSI / journalisation / detection Compose (fonctions partagees)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

# Chemins
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKUP_DIR="${PROJECT_ROOT}/backups"
START_TIME="$(date +%s)"

HELP_INVOKED=false

# Fichiers temporaires de dechiffrement a effacer sur TOUS les chemins de sortie
DECRYPTED_DB_TMP=""
DECRYPTED_UPLOADS_TMP=""

# Efface un fichier temporaire de maniere sure : `shred -u` si disponible,
# sinon `rm -f`.
secure_erase() {
    local target="$1"
    [[ -z "$target" || ! -e "$target" ]] && return 0
    if command -v shred &>/dev/null; then
        shred -u "$target" 2>/dev/null || rm -f "$target"
    else
        rm -f "$target"
    fi
}

# Piege de sortie / nettoyage
cleanup() {
    local exit_code=$?
    if [[ "${HELP_INVOKED:-false}" = true ]]; then
        return 0
    fi

    secure_erase "$DECRYPTED_DB_TMP"
    secure_erase "$DECRYPTED_UPLOADS_TMP"

    local end_time; end_time="$(date +%s)"
    local duration=$((end_time - START_TIME))

    if [[ $exit_code -eq 0 ]]; then
        log OK "Procedure de restauration terminee avec succes en ${duration}s."
    else
        log ERROR "Procedure de restauration interrompue (code ${exit_code}) apres ${duration}s."
    fi
}
trap cleanup EXIT

# -----------------------------------------------------------------------------
# 1. Analyse des arguments et options
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
            echo "Usage : $0 [OPTIONS] [FICHIER_DUMP] [FICHIER_UPLOADS]"
            echo ""
            echo "Options :"
            echo "  -f, --force    Ignore la confirmation interactive (choisit le plus recent)"
            echo "  -h, --help     Affiche cette aide"
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

# Chargement de .env
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

# Identite privee age (defaut : secrets/backup_age.key sous la racine du projet)
BACKUP_AGE_IDENTITY="${BACKUP_AGE_IDENTITY:-${PROJECT_ROOT}/secrets/backup_age.key}"

# Detection de la commande Docker Compose
detect_compose

# -----------------------------------------------------------------------------
# 2. Selection du fichier de sauvegarde
# -----------------------------------------------------------------------------
DB_BACKUP_FILE="$DB_BACKUP_ARG"

if [[ -z "$DB_BACKUP_FILE" ]]; then
    if [[ ! -d "$BACKUP_DIR" ]]; then
        log ERROR "Aucun repertoire de sauvegarde a ${BACKUP_DIR}. Precisez un chemin de fichier."
        exit 1
    fi

    # Dumps disponibles (chiffres .age ET anciens .dump en clair), plus recent d'abord
    mapfile -t BACKUP_LIST < <(find "$BACKUP_DIR" -maxdepth 1 -type f \( -name "db_*.dump.age" -o -name "db_*.dump" \) | sort -r)

    if [[ ${#BACKUP_LIST[@]} -eq 0 ]]; then
        log ERROR "Aucun fichier de sauvegarde de base (db_*.dump.age ou db_*.dump) dans ${BACKUP_DIR}."
        exit 1
    fi

    echo -e "\n${BOLD}${CYAN}Sauvegardes de base disponibles :${NC}"
    for i in "${!BACKUP_LIST[@]}"; do
        file="${BACKUP_LIST[$i]}"
        size=$(du -h "$file" | cut -f1)
        mtime=$(date -r "$file" "+%Y-%m-%d %H:%M:%S")
        echo -e "  [$((i+1))] $(basename "$file")  (${size}, ${mtime})"
    done
    echo ""

    if [[ "$FORCE_RESTORE" = true ]]; then
        DB_BACKUP_FILE="${BACKUP_LIST[0]}"
        log INFO "Option --force active : sauvegarde la plus recente selectionnee : $(basename "$DB_BACKUP_FILE")"
    else
        read -r -p "Numero de la sauvegarde a restaurer [1-${#BACKUP_LIST[@]}] : " CHOICE
        if [[ ! "$CHOICE" =~ ^[0-9]+$ ]] || [[ "$CHOICE" -lt 1 ]] || [[ "$CHOICE" -gt ${#BACKUP_LIST[@]} ]]; then
            log ERROR "Selection invalide."
            exit 1
        fi
        DB_BACKUP_FILE="${BACKUP_LIST[$((CHOICE-1))]}"
    fi
fi

# Verification de l'existence du fichier choisi
if [[ ! -f "$DB_BACKUP_FILE" ]]; then
    log ERROR "Le fichier de sauvegarde n'existe pas : ${DB_BACKUP_FILE}"
    exit 1
fi

# Recherche de l'archive uploads correspondante si non fournie explicitement
UPLOADS_BACKUP_FILE="$UPLOADS_BACKUP_ARG"
if [[ -z "$UPLOADS_BACKUP_FILE" ]]; then
    FILENAME=$(basename "$DB_BACKUP_FILE")
    BACKUP_TIMESTAMP=$(echo "$FILENAME" | grep -oP '\d{8}_\d{6}' || true)
    if [[ -n "$BACKUP_TIMESTAMP" ]]; then
        for candidate in \
            "${BACKUP_DIR}/uploads_${BACKUP_TIMESTAMP}.tar.gz.age" \
            "${BACKUP_DIR}/uploads_${BACKUP_TIMESTAMP}.tar.gz"; do
            if [[ -f "$candidate" ]]; then
                UPLOADS_BACKUP_FILE="$candidate"
                log INFO "Archive uploads correspondante trouvee : $(basename "$UPLOADS_BACKUP_FILE")"
                break
            fi
        done
    fi
fi

# -----------------------------------------------------------------------------
# 3. Dechiffrement (si necessaire) et validation
# -----------------------------------------------------------------------------

# Prepare le dump a restaurer : dechiffre l'artefact .age vers un fichier
# temporaire dans le projet (meme systeme de fichiers), ou renvoie le .dump tel
# quel. Renseigne la variable globale DB_RESTORE_SOURCE.
DB_RESTORE_SOURCE=""
if [[ "$DB_BACKUP_FILE" == *.age ]]; then
    if ! command -v age &>/dev/null; then
        log ERROR "Le binaire 'age' est requis pour dechiffrer ${DB_BACKUP_FILE}. Installez-le : sudo apt-get install -y age"
        exit 1
    fi
    if [[ ! -f "$BACKUP_AGE_IDENTITY" || ! -r "$BACKUP_AGE_IDENTITY" ]]; then
        log ERROR "Identite privee age introuvable ou illisible : ${BACKUP_AGE_IDENTITY}"
        log ERROR "Definissez BACKUP_AGE_IDENTITY dans .env ou placez la cle a cet emplacement."
        exit 1
    fi
    log INFO "Dechiffrement du dump avec l'identite ${BACKUP_AGE_IDENTITY}..."
    DECRYPTED_DB_TMP=$(mktemp --suffix=.tmp "${PROJECT_ROOT}/.restore_db.XXXXXX")
    # Redirection vers stdout (et non `-o`) : le fichier temporaire existe deja
    # (mktemp) et age refuse d'ecraser un fichier existant.
    age -d -i "$BACKUP_AGE_IDENTITY" "$DB_BACKUP_FILE" > "$DECRYPTED_DB_TMP"
    DB_RESTORE_SOURCE="$DECRYPTED_DB_TMP"
else
    DB_RESTORE_SOURCE="$DB_BACKUP_FILE"
fi

log INFO "Validation du fichier de dump..."

if [[ ! -s "$DB_RESTORE_SOURCE" ]]; then
    log ERROR "Le dump a restaurer est vide (0 octet)."
    exit 1
fi

HEADER=$(head -c 5 "$DB_RESTORE_SOURCE" || true)
if [[ "$HEADER" != "PGDMP" ]]; then
    log ERROR "Le dump ne commence pas par l'entete personnalise PostgreSQL 'PGDMP'."
    exit 1
fi
log OK "Entete de dump PostgreSQL valide (PGDMP)."

# -----------------------------------------------------------------------------
# 4. Garde-fou de confirmation
# -----------------------------------------------------------------------------
echo -e "\n${BOLD}${RED}======================================================${NC}"
echo -e "${BOLD}${RED}          CONFIRMATION - AVERTISSEMENT RESTAURATION    ${NC}"
echo -e "${BOLD}${RED}======================================================${NC}"
echo -e "Base cible :            ${BOLD}${POSTGRES_DB}${NC}"
echo -e "Conteneur cible :       ${BOLD}${POSTGRES_CONTAINER}${NC}"
echo -e "Fichier de dump :       ${BOLD}${DB_BACKUP_FILE}${NC}"
if [[ -n "$UPLOADS_BACKUP_FILE" && -f "$UPLOADS_BACKUP_FILE" ]]; then
echo -e "Archive uploads :       ${BOLD}${UPLOADS_BACKUP_FILE}${NC}"
fi
echo ""
echo -e "${YELLOW}ATTENTION : cette operation ecrase les tables et les donnees existantes"
echo -e "de '${POSTGRES_DB}'. Toute modification non sauvegardee sera DEFINITIVEMENT PERDUE.${NC}"
echo -e "${BOLD}${RED}======================================================${NC}\n"

if [[ "$FORCE_RESTORE" = false ]]; then
    read -r -p "Tapez 'RESTORE' pour confirmer et poursuivre : " CONFIRMATION
    if [[ "$CONFIRMATION" != "RESTORE" ]]; then
        log WARN "Restauration annulee par l'operateur."
        exit 0
    fi
else
    log WARN "Option --force specifiee. Confirmation manuelle ignoree."
fi

# -----------------------------------------------------------------------------
# 5. Verification du service et terminaison des connexions
# -----------------------------------------------------------------------------
log INFO "Verification de l'execution du service PostgreSQL..."

if ! $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" ps --services --filter "status=running" | grep -q "^db$"; then
    log INFO "Le service de base de donnees n'est pas actif. Demarrage du conteneur db..."
    $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" up -d db
fi

log INFO "Attente de l'acceptation des connexions par PostgreSQL..."
MAX_RETRIES=15
COUNTER=0
until $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" &>/dev/null; do
    COUNTER=$((COUNTER+1))
    if [[ $COUNTER -ge $MAX_RETRIES ]]; then
        log ERROR "Delai depasse en attendant que PostgreSQL soit pret."
        exit 1
    fi
    sleep 1
done
log OK "PostgreSQL accepte les connexions."

log INFO "Terminaison des autres connexions clientes actives sur '${POSTGRES_DB}'..."
$DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T db \
    psql -U "$POSTGRES_USER" -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();" &>/dev/null || true

# -----------------------------------------------------------------------------
# 6. Restauration de la base (pg_restore)
# -----------------------------------------------------------------------------
log INFO "Restauration de la base '${POSTGRES_DB}' depuis le dump..."

# pg_restore peut renvoyer le code 1 pour des avertissements non critiques
# (notices lors des DROP ... IF EXISTS) : on tolere donc 0 et 1, on echoue au-dela.
RESTORE_STATUS=0
$DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T db \
    pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    < "$DB_RESTORE_SOURCE" || RESTORE_STATUS=$?

if [[ $RESTORE_STATUS -ne 0 && $RESTORE_STATUS -ne 1 ]]; then
    log ERROR "pg_restore a echoue avec le code critique ${RESTORE_STATUS} !"
    exit "$RESTORE_STATUS"
fi
log OK "Schema et donnees de la base restaures."

# Effacement immediat du dump dechiffre (le piege le refera au besoin)
if [[ -n "$DECRYPTED_DB_TMP" ]]; then
    secure_erase "$DECRYPTED_DB_TMP"
    DECRYPTED_DB_TMP=""
fi

# -----------------------------------------------------------------------------
# 7. Restauration du repertoire uploads
# -----------------------------------------------------------------------------
if [[ -n "$UPLOADS_BACKUP_FILE" && -f "$UPLOADS_BACKUP_FILE" ]]; then
    log INFO "Restauration des uploads depuis ${UPLOADS_BACKUP_FILE}..."
    UPLOADS_DIR="${PROJECT_ROOT}/uploads"

    # Source d'extraction : dechiffree si .age, sinon l'archive telle quelle
    UPLOADS_EXTRACT_SOURCE=""
    if [[ "$UPLOADS_BACKUP_FILE" == *.age ]]; then
        if ! command -v age &>/dev/null; then
            log ERROR "Le binaire 'age' est requis pour dechiffrer ${UPLOADS_BACKUP_FILE}. Installez-le : sudo apt-get install -y age"
            exit 1
        fi
        if [[ ! -f "$BACKUP_AGE_IDENTITY" || ! -r "$BACKUP_AGE_IDENTITY" ]]; then
            log ERROR "Identite privee age introuvable ou illisible : ${BACKUP_AGE_IDENTITY}"
            exit 1
        fi
        log INFO "Dechiffrement de l'archive uploads..."
        DECRYPTED_UPLOADS_TMP=$(mktemp --suffix=.tmp "${PROJECT_ROOT}/.restore_uploads.XXXXXX")
        age -d -i "$BACKUP_AGE_IDENTITY" "$UPLOADS_BACKUP_FILE" > "$DECRYPTED_UPLOADS_TMP"
        UPLOADS_EXTRACT_SOURCE="$DECRYPTED_UPLOADS_TMP"
    else
        UPLOADS_EXTRACT_SOURCE="$UPLOADS_BACKUP_FILE"
    fi

    # Copie de securite des uploads actuels si le repertoire n'est pas vide
    if [[ -d "$UPLOADS_DIR" ]] && [[ "$(ls -A "$UPLOADS_DIR" 2>/dev/null)" ]]; then
        SAFETY_BACKUP="${PROJECT_ROOT}/uploads.pre-restore_$(date +%Y%m%d_%H%M%S)"
        log INFO "Copie des uploads actuels vers ${SAFETY_BACKUP} avant extraction..."
        cp -r "$UPLOADS_DIR" "$SAFETY_BACKUP"
    fi

    mkdir -p "$UPLOADS_DIR"
    tar -xzf "$UPLOADS_EXTRACT_SOURCE" -C "$PROJECT_ROOT"
    log OK "Archive des uploads restauree."

    if [[ -n "$DECRYPTED_UPLOADS_TMP" ]]; then
        secure_erase "$DECRYPTED_UPLOADS_TMP"
        DECRYPTED_UPLOADS_TMP=""
    fi
fi

# -----------------------------------------------------------------------------
# 8. Verification post-restauration
# -----------------------------------------------------------------------------
log INFO "Verification post-restauration..."

if $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" &>/dev/null; then
    TABLE_COUNT=$($DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T db \
        psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d '[:space:]')
    log OK "Base verifiee. Nombre de tables du schema public : ${TABLE_COUNT:-0}"
else
    log ERROR "La base ne repond pas apres la restauration !"
    exit 1
fi

if $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" ps --services --filter "status=running" | grep -q "^backend$"; then
    log INFO "Verification du point de sante du backend (/health)..."
    sleep 2
    if $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T backend \
        python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" &>/dev/null; then
        log OK "Point de sante du backend OK : /health repond avec HTTP 200."
    else
        log WARN "Le backend tourne mais /health n'a pas renvoye 200. Un redemarrage du conteneur backend peut etre necessaire."
    fi
fi

echo -e "\n${BOLD}${GREEN}======================================================${NC}"
echo -e "${BOLD}${GREEN}          Restauration terminee avec succes !          ${NC}"
echo -e "${BOLD}${GREEN}======================================================${NC}\n"
