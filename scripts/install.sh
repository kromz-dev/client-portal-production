#!/usr/bin/env bash
# =============================================================================
# install.sh - Preparation de l'hote Debian (premiere execution)
# =============================================================================
# A executer une seule fois par l'operateur sur la machine de production.
# Idempotent : peut etre relance sans danger.
#
# Operations :
#   1. Verifie la presence des commandes requises (docker, compose, age...)
#   2. Cree les repertoires secrets/, backups/, uploads/, docs/mesures/
#   3. Genere la paire de cles age (X25519) si absente
#   4. Affiche la cle publique age a coller dans .env (BACKUP_AGE_RECIPIENT)
#   5. Rappelle de copier l'identite privee hors de la machine
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_ROOT"

HELP_INVOKED=false
cleanup() {
    local exit_code=$?
    [[ "${HELP_INVOKED:-false}" = true ]] && return 0
    if [[ $exit_code -ne 0 ]]; then
        log ERROR "L'installation a echoue (code ${exit_code})."
    fi
}
trap cleanup EXIT

for arg in "$@"; do
    case "$arg" in
        -h|--help)
            HELP_INVOKED=true
            echo "Usage : $0"
            echo ""
            echo "Prepare l'hote : verifie les dependances, cree les repertoires,"
            echo "genere la cle age de chiffrement des sauvegardes."
            exit 0
            ;;
    esac
done

echo -e "${BOLD}======================================================${NC}"
echo -e "${BOLD}      Portail Client - Installation de l'hote          ${NC}"
echo -e "${BOLD}======================================================${NC}"

# -----------------------------------------------------------------------------
# 1. Verification des commandes requises
# -----------------------------------------------------------------------------
log INFO "Verification des dependances systeme..."

MISSING=0

require_cmd() {
    local cmd="$1" hint="$2"
    if ! command -v "$cmd" &>/dev/null; then
        log ERROR "Commande manquante : '${cmd}'  ->  ${hint}"
        MISSING=1
    else
        log OK "Present : ${cmd}"
    fi
}

# Dependance non bloquante : absente, on avertit seulement (utile en local).
AGE_AVAILABLE=true
optional_cmd() {
    local cmd="$1" hint="$2"
    if ! command -v "$cmd" &>/dev/null; then
        log WARN "Optionnel absent : '${cmd}'  ->  ${hint}"
        return 1
    fi
    log OK "Present : ${cmd}"
    return 0
}

require_cmd docker      "installer Docker Engine : https://docs.docker.com/engine/install/debian/"
require_cmd curl        "sudo apt-get install -y curl"
require_cmd tar         "sudo apt-get install -y tar"
optional_cmd shred      "sudo apt-get install -y coreutils"
optional_cmd age        "sudo apt-get install -y age (requis pour CHIFFRER les sauvegardes)"       || AGE_AVAILABLE=false
optional_cmd age-keygen "sudo apt-get install -y age"                                              || AGE_AVAILABLE=false

# Docker Compose : plugin v2 ou binaire v1
if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    log OK "Present : docker compose (plugin v2)"
elif command -v docker-compose &>/dev/null; then
    log OK "Present : docker-compose (v1)"
else
    log ERROR "Docker Compose manquant  ->  installer le plugin : sudo apt-get install -y docker-compose-plugin"
    MISSING=1
fi

if [[ $MISSING -ne 0 ]]; then
    log ERROR "Des dependances sont manquantes. Installez-les puis relancez ce script."
    exit 1
fi
log OK "Toutes les dependances sont presentes."

# -----------------------------------------------------------------------------
# 2. Creation des repertoires
# -----------------------------------------------------------------------------
log INFO "Creation des repertoires de travail..."

mkdir -p secrets && chmod 700 secrets
mkdir -p backups && chmod 700 backups
mkdir -p uploads docs/mesures

log OK "Repertoires prets : secrets/ (700), backups/ (700), uploads/, docs/mesures/"

# -----------------------------------------------------------------------------
# 3. Generation de la cle age
# -----------------------------------------------------------------------------
AGE_KEY_FILE="${PROJECT_ROOT}/secrets/backup_age.key"

if [[ "$AGE_AVAILABLE" != true ]]; then
    log WARN "age indisponible : generation de cle ignoree."
    log WARN "Les sauvegardes seront ecrites EN CLAIR tant que ENVIRONMENT != production."
    log WARN "Pour chiffrer : sudo apt-get install -y age puis relancez ce script."
    echo ""
    echo -e "${BOLD}Prochaine commande :${NC} docker compose -f docker-compose.yml up -d --build"
    exit 0
fi

if [[ -f "$AGE_KEY_FILE" ]]; then
    log INFO "Une identite age existe deja : ${AGE_KEY_FILE} (non modifiee)."
else
    log INFO "Generation d'une nouvelle identite age (X25519)..."
    age-keygen -o "$AGE_KEY_FILE" 2>/dev/null
    chmod 600 "$AGE_KEY_FILE"
    log OK "Identite privee creee : ${AGE_KEY_FILE} (chmod 600)"
fi

AGE_PUBLIC_KEY="$(age-keygen -y "$AGE_KEY_FILE")"

# -----------------------------------------------------------------------------
# 4. Etat de .env et cle publique
# -----------------------------------------------------------------------------
ENV_FILE="${PROJECT_ROOT}/.env"
ENV_RECIPIENT=""
if [[ -f "$ENV_FILE" ]]; then
    ENV_RECIPIENT="$(grep -E '^BACKUP_AGE_RECIPIENT=' "$ENV_FILE" | tail -n1 | cut -d= -f2- || true)"
fi

echo ""
echo -e "${BOLD}======================================================${NC}"
echo -e "${BOLD}      CLE PUBLIQUE age (chiffrement des sauvegardes)   ${NC}"
echo -e "${BOLD}======================================================${NC}"
echo -e "  ${GREEN}${AGE_PUBLIC_KEY}${NC}"
echo -e "${BOLD}======================================================${NC}"

if [[ -n "$ENV_RECIPIENT" ]]; then
    log OK "BACKUP_AGE_RECIPIENT est deja renseigne dans .env : ${ENV_RECIPIENT}"
    if [[ "$ENV_RECIPIENT" != "$AGE_PUBLIC_KEY" ]]; then
        log WARN "La valeur de .env differe de la cle publique ci-dessus. Verifiez que c'est voulu"
        log WARN "(sinon les sauvegardes seront chiffrees pour une cle dont vous n'avez pas l'identite)."
    fi
else
    echo ""
    echo -e "${YELLOW}Action (a) :${NC} collez cette ligne dans ${ENV_FILE} :"
    echo -e "    ${BOLD}BACKUP_AGE_RECIPIENT=${AGE_PUBLIC_KEY}${NC}"
fi

echo ""
echo -e "${YELLOW}Action (b) :${NC} copiez ${BOLD}secrets/backup_age.key${NC} hors de cette machine"
echo -e "  (gestionnaire de mots de passe, cle USB chiffree...). SANS cette identite"
echo -e "  privee, AUCUNE sauvegarde ne pourra jamais etre restauree."

# -----------------------------------------------------------------------------
# 5. Verification de .env
# -----------------------------------------------------------------------------
echo ""
if [[ ! -f "$ENV_FILE" ]]; then
    log WARN "Fichier .env absent."
    log WARN "  cp .env.example .env"
    log WARN "  puis renseignez : POSTGRES_PASSWORD, SECRET_KEY (openssl rand -hex 32),"
    log WARN "  DOMAIN_NAME, CADDY_EMAIL, CORS_ORIGINS"
else
    log OK "Fichier .env present."
fi

# -----------------------------------------------------------------------------
# 6. Etape suivante
# -----------------------------------------------------------------------------
echo ""
echo -e "${BOLD}Prochaine commande a executer :${NC}"
echo -e "    ${BOLD}docker compose up -d --build${NC}"
echo ""
log OK "Installation de l'hote terminee."
