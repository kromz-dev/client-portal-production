#!/usr/bin/env bash
# =============================================================================
# install-timers.sh - Installation des unites systemd du Portail Client
# =============================================================================
# Copie deploy/systemd/*.service et *.timer dans /etc/systemd/system/, recharge
# systemd, active le timer de sauvegarde et l'unite de demarrage de la pile.
#
# A executer en root (sudo) sur l'hote de production.
# Les unites codent en dur le chemin /opt/portail_client.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
UNIT_SRC_DIR="${PROJECT_ROOT}/deploy/systemd"
SYSTEMD_DIR="/etc/systemd/system"
EXPECTED_ROOT="/opt/portail_client"

HELP_INVOKED=false
cleanup() {
    local exit_code=$?
    [[ "${HELP_INVOKED:-false}" = true ]] && return 0
    [[ $exit_code -ne 0 ]] && log ERROR "L'installation des unites a echoue (code ${exit_code})."
}
trap cleanup EXIT

for arg in "$@"; do
    case "$arg" in
        -h|--help)
            HELP_INVOKED=true
            echo "Usage : sudo $0"
            echo ""
            echo "Installe et active les unites systemd (portail-client.service,"
            echo "portail-backup.service, portail-backup.timer)."
            exit 0
            ;;
    esac
done

# -----------------------------------------------------------------------------
# 1. Privileges et emplacement du projet
# -----------------------------------------------------------------------------
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    log ERROR "Ce script doit etre execute en root. Relancez : sudo $0"
    exit 1
fi

if [[ ! -d "$UNIT_SRC_DIR" ]]; then
    log ERROR "Repertoire des unites introuvable : ${UNIT_SRC_DIR}"
    exit 1
fi

if [[ "$PROJECT_ROOT" != "$EXPECTED_ROOT" ]]; then
    log WARN "======================================================"
    log WARN "Le projet est situe a : ${PROJECT_ROOT}"
    log WARN "Or les unites systemd codent en dur : ${EXPECTED_ROOT}"
    log WARN "Elles ne fonctionneront PAS tant que le projet n'est pas"
    log WARN "deploye a ${EXPECTED_ROOT} (ou que vous n'avez pas edite"
    log WARN "les fichiers deploy/systemd/*.service en consequence)."
    log WARN "======================================================"
fi

# -----------------------------------------------------------------------------
# 2. Copie des unites
# -----------------------------------------------------------------------------
log INFO "Copie des unites vers ${SYSTEMD_DIR}/ ..."
shopt -s nullglob
UNIT_FILES=("${UNIT_SRC_DIR}"/*.service "${UNIT_SRC_DIR}"/*.timer)
shopt -u nullglob

if [[ ${#UNIT_FILES[@]} -eq 0 ]]; then
    log ERROR "Aucun fichier .service / .timer dans ${UNIT_SRC_DIR}."
    exit 1
fi

for unit in "${UNIT_FILES[@]}"; do
    install -m 0644 "$unit" "${SYSTEMD_DIR}/$(basename "$unit")"
    log OK "Installe : $(basename "$unit")"
done

# -----------------------------------------------------------------------------
# 3. Rechargement et activation
# -----------------------------------------------------------------------------
log INFO "systemctl daemon-reload"
systemctl daemon-reload

log INFO "Activation du timer de sauvegarde (enable --now)..."
systemctl enable --now portail-backup.timer

log INFO "Activation de l'unite de demarrage de la pile (enable)..."
systemctl enable portail-client.service

# -----------------------------------------------------------------------------
# 4. Etat final
# -----------------------------------------------------------------------------
echo ""
echo -e "${BOLD}======================================================${NC}"
echo -e "${BOLD}  Etat du timer de sauvegarde                          ${NC}"
echo -e "${BOLD}======================================================${NC}"
systemctl list-timers portail-backup --all --no-pager || true

echo ""
echo -e "${BOLD}======================================================${NC}"
echo -e "${BOLD}  Derniers journaux de portail-backup                  ${NC}"
echo -e "${BOLD}======================================================${NC}"
journalctl -u portail-backup -n 20 --no-pager || true

echo ""
log OK "Unites systemd installees et activees."
