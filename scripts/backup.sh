#!/usr/bin/env bash
# =============================================================================
# backup.sh - Sauvegarde chiffree de la base de donnees et des uploads
# =============================================================================
# Operations realisees :
#   1. pg_dump au format compresse personnalise (-Fc) depuis le conteneur
#      PostgreSQL
#   2. Archive compressee (.tar.gz) du repertoire uploads/
#   3. Verification de la taille et de l'entete des fichiers produits
#   4. Chiffrement de chaque artefact avec `age` (cle publique X25519) :
#      aucune sauvegarde en clair n'est conservee sur le disque
#   5. Rotation de retention (suppression des archives plus vieilles que le
#      seuil), y compris les anciens fichiers en clair d'avant le chiffrement
#   6. Rapport horodate et pret pour l'audit, avec metriques de duree
#
# Ce script s'execute sans surveillance (timer systemd) : il utilise donc une
# cle publique age et jamais une phrase de passe interactive.
# =============================================================================

set -euo pipefail

# ANSI / journalisation / detection Compose (fonctions partagees)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

# Determination des chemins
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKUP_DIR="${PROJECT_ROOT}/backups"
TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
START_TIME="$(date +%s)"

HELP_INVOKED=false

# Artefacts en clair a supprimer imperativement si le script meurt en cours de
# chiffrement : une sauvegarde non chiffree ne doit jamais survivre a un echec.
DB_PLAINTEXT=""
UPLOADS_PLAINTEXT=""

# Artefacts finaux effectivement conserves (chiffres .age OU en clair selon le
# mode) : renseignes pour le rapport de synthese.
DB_FINAL_FILE=""
UPLOADS_FINAL_FILE=""

# Piege de sortie / nettoyage
cleanup() {
    local exit_code=$?
    if [[ "${HELP_INVOKED:-false}" = true ]]; then
        return 0
    fi

    # Suppression des intermediaires en clair eventuellement laisses en place
    for leftover in "$DB_PLAINTEXT" "$UPLOADS_PLAINTEXT"; do
        if [[ -n "$leftover" && -f "$leftover" ]]; then
            log WARN "Suppression de l'intermediaire en clair : $(basename "$leftover")"
            rm -f "$leftover"
        fi
    done

    local end_time; end_time="$(date +%s)"
    local duration=$((end_time - START_TIME))

    if [[ $exit_code -eq 0 ]]; then
        log OK "Sauvegarde terminee avec succes en ${duration}s."
    else
        log ERROR "Echec de la sauvegarde (code ${exit_code}) apres ${duration}s !"
    fi
}
trap cleanup EXIT

# Analyse de l'option d'aide
for arg in "$@"; do
    case "$arg" in
        -h|--help)
            HELP_INVOKED=true
            echo "Usage : $0 [OPTIONS]"
            echo ""
            echo "Sauvegarde PostgreSQL (pg_dump -Fc) et archive des uploads, chiffrees"
            echo "avec age, suivies d'une rotation de retention."
            echo ""
            echo "Options :"
            echo "  -h, --help    Affiche cette aide"
            exit 0
            ;;
    esac
done

# -----------------------------------------------------------------------------
# 1. Environnement et verifications prealables
# -----------------------------------------------------------------------------
log INFO "Demarrage de la procedure de sauvegarde depuis ${PROJECT_ROOT}"

# Chargement des variables d'environnement si .env existe
ENV_FILE="${PROJECT_ROOT}/.env"
if [[ -f "$ENV_FILE" ]]; then
    log INFO "Chargement de la configuration depuis .env"
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
else
    log WARN "Fichier .env introuvable a ${ENV_FILE}. Utilisation des valeurs par defaut."
fi

# Valeurs par defaut
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-portail_client}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-portail_db}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

# Chiffrement : obligatoire en production, optionnel ailleurs.
#   - BACKUP_AGE_RECIPIENT renseigne  -> chiffrement age (binaire 'age' requis)
#   - vide + ENVIRONMENT=production    -> erreur (aucune sauvegarde en clair en prod)
#   - vide + hors production           -> sauvegarde NON chiffree (toleree en local)
ENCRYPT=true
if [[ -z "${BACKUP_AGE_RECIPIENT:-}" ]]; then
    if [[ "${ENVIRONMENT:-production}" == "production" ]]; then
        log ERROR "BACKUP_AGE_RECIPIENT n'est pas defini dans .env (obligatoire en production)."
        log ERROR "Executez d'abord : ./scripts/install.sh (genere la cle et affiche la cle publique age1...)."
        exit 1
    fi
    ENCRYPT=false
    log WARN "BACKUP_AGE_RECIPIENT vide et ENVIRONMENT != production :"
    log WARN "les sauvegardes seront ecrites EN CLAIR (mode local uniquement)."
fi

# Binaire age requis uniquement si l'on chiffre
if [[ "$ENCRYPT" == true ]] && ! command -v age &>/dev/null; then
    log ERROR "Le binaire 'age' est introuvable. Installez-le : sudo apt-get install -y age"
    exit 1
fi

# Detection de la commande Docker Compose
detect_compose

# Repertoire de sauvegarde avec permissions restreintes (0700)
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# -----------------------------------------------------------------------------
# 2. Verification de l'etat de la base de donnees
# -----------------------------------------------------------------------------
log INFO "Verification de l'etat du conteneur PostgreSQL (${POSTGRES_CONTAINER})..."

if ! $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" ps --services --filter "status=running" | grep -q "^db$"; then
    log ERROR "Le service de base de donnees 'db' (${POSTGRES_CONTAINER}) n'est pas en cours d'execution."
    exit 1
fi

if ! $DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" &>/dev/null; then
    log ERROR "PostgreSQL fonctionne mais n'accepte pas les connexions pour l'utilisateur '$POSTGRES_USER' et la base '$POSTGRES_DB'."
    exit 1
fi
log OK "La base de donnees PostgreSQL est saine et prete pour le dump."

# -----------------------------------------------------------------------------
# 3. Sauvegarde de la base de donnees (pg_dump -Fc) puis chiffrement
# -----------------------------------------------------------------------------
DB_DUMP_FILE="${BACKUP_DIR}/db_${POSTGRES_DB}_${TIMESTAMP}.dump"
DB_ENC_FILE="${DB_DUMP_FILE}.age"
log INFO "Dump de la base '${POSTGRES_DB}' vers ${DB_DUMP_FILE}..."

# On marque l'artefact en clair AVANT sa creation pour que le piege puisse le
# nettoyer meme si le dump echoue a mi-parcours.
DB_PLAINTEXT="$DB_DUMP_FILE"

# Format personnalise (-Fc) : compression, gestion des BLOB, restauration fine
$DOCKER_COMPOSE -f "${PROJECT_ROOT}/docker-compose.yml" exec -T db \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges \
    > "$DB_DUMP_FILE"

# Validation du dump en clair (l'entete PGDMP est encore lisible a ce stade)
if [[ ! -s "$DB_DUMP_FILE" ]]; then
    log ERROR "Le fichier de sauvegarde de la base est vide ou n'a pas ete cree : ${DB_DUMP_FILE}"
    exit 1
fi

HEADER=$(head -c 5 "$DB_DUMP_FILE" || true)
if [[ "$HEADER" != "PGDMP" ]]; then
    log ERROR "L'entete du fichier ne correspond pas au format dump personnalise PostgreSQL (obtenu '$HEADER')."
    exit 1
fi
log OK "Dump de la base valide (entete PGDMP)."

if [[ "$ENCRYPT" == true ]]; then
    # Chiffrement avec la cle publique age
    log INFO "Chiffrement du dump avec age -> $(basename "$DB_ENC_FILE")"
    rm -f "$DB_ENC_FILE"
    age -r "$BACKUP_AGE_RECIPIENT" -o "$DB_ENC_FILE" "$DB_DUMP_FILE"
    rm -f "$DB_DUMP_FILE"
    DB_PLAINTEXT=""

    # Verification de l'artefact chiffre
    if [[ ! -s "$DB_ENC_FILE" ]]; then
        log ERROR "Le fichier chiffre est vide : ${DB_ENC_FILE}"
        rm -f "$DB_ENC_FILE"
        exit 1
    fi
    ENC_HEADER=$(head -c 21 "$DB_ENC_FILE" || true)
    if [[ "$ENC_HEADER" != "age-encryption.org/v1" ]]; then
        log ERROR "L'entete du fichier chiffre n'est pas 'age-encryption.org/v1' (obtenu '$ENC_HEADER')."
        rm -f "$DB_ENC_FILE"
        exit 1
    fi

    DB_FINAL_FILE="$DB_ENC_FILE"
    DB_SIZE=$(du -h "$DB_ENC_FILE" | cut -f1)
    log OK "Sauvegarde de la base chiffree et verifiee : ${DB_ENC_FILE} (${DB_SIZE})"
else
    # Pas de chiffrement : on conserve le dump en clair tel quel.
    DB_PLAINTEXT=""   # ne pas laisser le piege EXIT supprimer un artefact valide
    DB_FINAL_FILE="$DB_DUMP_FILE"
    DB_SIZE=$(du -h "$DB_DUMP_FILE" | cut -f1)
    log OK "Sauvegarde de la base (NON chiffree) : ${DB_DUMP_FILE} (${DB_SIZE})"
fi

# -----------------------------------------------------------------------------
# 4. Sauvegarde du volume uploads puis chiffrement
# -----------------------------------------------------------------------------
UPLOADS_DIR="${PROJECT_ROOT}/uploads"
UPLOADS_TAR_FILE="${BACKUP_DIR}/uploads_${TIMESTAMP}.tar.gz"
UPLOADS_ENC_FILE="${UPLOADS_TAR_FILE}.age"

if [[ -d "$UPLOADS_DIR" ]]; then
    log INFO "Archivage des uploads depuis ${UPLOADS_DIR}..."
    UPLOADS_PLAINTEXT="$UPLOADS_TAR_FILE"
    tar -czf "$UPLOADS_TAR_FILE" -C "$PROJECT_ROOT" uploads

    if [[ -s "$UPLOADS_TAR_FILE" ]]; then
        if [[ "$ENCRYPT" == true ]]; then
            log INFO "Chiffrement de l'archive uploads avec age -> $(basename "$UPLOADS_ENC_FILE")"
            rm -f "$UPLOADS_ENC_FILE"
            age -r "$BACKUP_AGE_RECIPIENT" -o "$UPLOADS_ENC_FILE" "$UPLOADS_TAR_FILE"
            rm -f "$UPLOADS_TAR_FILE"
            UPLOADS_PLAINTEXT=""

            if [[ ! -s "$UPLOADS_ENC_FILE" ]]; then
                log ERROR "L'archive uploads chiffree est vide : ${UPLOADS_ENC_FILE}"
                rm -f "$UPLOADS_ENC_FILE"
                exit 1
            fi
            UP_ENC_HEADER=$(head -c 21 "$UPLOADS_ENC_FILE" || true)
            if [[ "$UP_ENC_HEADER" != "age-encryption.org/v1" ]]; then
                log ERROR "L'entete de l'archive uploads chiffree n'est pas 'age-encryption.org/v1' (obtenu '$UP_ENC_HEADER')."
                rm -f "$UPLOADS_ENC_FILE"
                exit 1
            fi

            UPLOADS_FINAL_FILE="$UPLOADS_ENC_FILE"
            UPLOADS_SIZE=$(du -h "$UPLOADS_ENC_FILE" | cut -f1)
            log OK "Archive uploads chiffree et verifiee : ${UPLOADS_ENC_FILE} (${UPLOADS_SIZE})"
        else
            UPLOADS_PLAINTEXT=""   # artefact valide : le piege EXIT ne doit pas y toucher
            UPLOADS_FINAL_FILE="$UPLOADS_TAR_FILE"
            UPLOADS_SIZE=$(du -h "$UPLOADS_TAR_FILE" | cut -f1)
            log OK "Archive uploads (NON chiffree) : ${UPLOADS_TAR_FILE} (${UPLOADS_SIZE})"
        fi
    else
        log WARN "L'archive uploads a ete creee mais elle est vide. Suppression."
        rm -f "$UPLOADS_TAR_FILE"
        UPLOADS_PLAINTEXT=""
    fi
else
    log WARN "Aucun repertoire uploads trouve a ${UPLOADS_DIR}. Archive des uploads ignoree."
fi

# -----------------------------------------------------------------------------
# 5. Politique de retention (rotation)
# -----------------------------------------------------------------------------
log INFO "Application de la rotation de retention sur ${RETENTION_DAYS} jours..."

purge_expired() {
    local pattern="$1" label="$2" expired
    expired=$(find "$BACKUP_DIR" -maxdepth 1 -type f -name "$pattern" -mtime +"$RETENTION_DAYS" || true)
    if [[ -n "$expired" ]]; then
        while IFS= read -r file; do
            [[ -z "$file" ]] && continue
            log INFO "Purge ${label} expire : $(basename "$file")"
            rm -f "$file"
        done <<< "$expired"
    fi
}

# Artefacts chiffres courants
purge_expired "db_*.dump.age"       "du dump de base"
purge_expired "uploads_*.tar.gz.age" "de l'archive uploads"
# Anciens artefacts en clair d'avant le chiffrement : une installation mise a
# jour se nettoie ainsi d'elle-meme.
purge_expired "db_*.dump"           "du dump de base (ancien format en clair)"
purge_expired "uploads_*.tar.gz"    "de l'archive uploads (ancien format en clair)"

# -----------------------------------------------------------------------------
# 6. Rapport de synthese
# -----------------------------------------------------------------------------
TOTAL_BACKUPS_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
BACKUP_COUNT=$(find "$BACKUP_DIR" -maxdepth 1 -type f \( -name "*.age" -o -name "*.dump" -o -name "*.tar.gz" \) | wc -l)

echo -e "\n${BOLD}======================================================${NC}"
echo -e "${BOLD}            Rapport de synthese - Sauvegarde           ${NC}"
echo -e "${BOLD}======================================================${NC}"
if [[ "$ENCRYPT" == true ]]; then
echo "  - Dump base (chiffre) : ${DB_FINAL_FILE} (${DB_SIZE})"
else
echo "  - Dump base (EN CLAIR) : ${DB_FINAL_FILE} (${DB_SIZE})"
fi
if [[ -n "$UPLOADS_FINAL_FILE" && -f "$UPLOADS_FINAL_FILE" ]]; then
echo "  - Archive uploads : ${UPLOADS_FINAL_FILE} (${UPLOADS_SIZE:-?})"
fi
echo "  - Total archives : ${BACKUP_COUNT} fichiers dans ${BACKUP_DIR}"
echo "  - Espace disque total : ${TOTAL_BACKUPS_SIZE}"
echo "  - Fenetre de retention : ${RETENTION_DAYS} jours"
if [[ "$ENCRYPT" == true ]]; then
echo "  - Chiffrement : age (X25519), destinataire ${BACKUP_AGE_RECIPIENT}"
echo -e "  ${YELLOW}Rappel : la restauration exige l'identite privee age"
echo -e "  (secrets/backup_age.key). Sans elle, AUCUNE sauvegarde n'est recuperable.${NC}"
else
echo -e "  ${YELLOW}Chiffrement : DESACTIVE (mode local). Ne pas utiliser tel quel en production.${NC}"
fi
echo -e "${BOLD}======================================================${NC}\n"
