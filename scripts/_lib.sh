#!/usr/bin/env bash
# =============================================================================
# _lib.sh - Fonctions partagees par les scripts d'exploitation du Portail Client
# =============================================================================
# Ce fichier est destine a etre source (`source`), jamais execute directement.
# Il fournit :
#   - la palette de couleurs ANSI
#   - la fonction de journalisation `log` (horodatage type ISO-8601)
#   - la detection de la commande Compose (`docker compose` ou `docker-compose`)
#
# Le chemin d'appel peut etre absolu (invocation via une unite systemd depuis
# /opt/portail_client) : ne jamais supposer un repertoire courant particulier.
# =============================================================================

# Couleurs ANSI
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Journalisation avec horodatage lisible.
# Usage : log INFO "message"  (niveaux : INFO, OK, WARN, ERROR)
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

# Detecte la commande Docker Compose disponible et renseigne la variable
# globale DOCKER_COMPOSE. Termine le script appelant en erreur si aucune
# variante n'est utilisable.
detect_compose() {
    if command -v docker &>/dev/null && docker compose version &>/dev/null; then
        DOCKER_COMPOSE="docker compose"
    elif command -v docker-compose &>/dev/null; then
        DOCKER_COMPOSE="docker-compose"
    else
        log ERROR "Docker ou Docker Compose n'est pas installe ou absent du PATH."
        exit 1
    fi
}
