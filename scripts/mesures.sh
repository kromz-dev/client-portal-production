#!/usr/bin/env bash
# =============================================================================
# mesures.sh - Releve reel des indicateurs de service (SLA)
# =============================================================================
# Mesure sur la machine courante, chronometre a l'appui :
#   - Demarrage a froid  (down + up -d --build jusqu'a tous les services sains)
#   - Demarrage a chaud   (down + up -d, images conservees)
#   - Reprise apres arret (stop + start) - proxy du RTO d'un reboot
#   - Duree de restauration (backup.sh puis restore.sh -f)
#   - Latence HTTP (/api/health, 20 requetes : min / mediane / p95)
#
# Le rapport horodate est ecrit dans docs/mesures/resultats_<ts>.txt et
# affiche sur la sortie standard.
#
# ATTENTION - OPERATION SEMI-DESTRUCTIVE :
#   ce script ARRETE et REDEMARRE la pile plusieurs fois et RESTAURE une
#   sauvegarde (la base est ecrasee par le dump le plus recent).
#   Ne l'executez PAS sur un environnement de production en service.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_lib.sh
source "${SCRIPT_DIR}/_lib.sh"

PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_ROOT"

COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"
MESURES_DIR="${PROJECT_ROOT}/docs/mesures"
TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
REPORT_FILE="${MESURES_DIR}/resultats_${TIMESTAMP}.txt"

# Les quatre services de la pile et leurs conteneurs
CONTAINERS=(portail_db portail_backend portail_web portail_caddy)

# Delai maximal (secondes) d'attente d'une pile saine
HEALTH_TIMEOUT=300

HELP_INVOKED=false
FORCE=false

cleanup() {
    local exit_code=$?
    [[ "${HELP_INVOKED:-false}" = true ]] && return 0
    if [[ $exit_code -eq 0 ]]; then
        log OK "Releve de mesures termine. Rapport : ${REPORT_FILE}"
    else
        log ERROR "Le releve de mesures s'est interrompu (code ${exit_code})."
        log ERROR "Verifiez l'etat de la pile : ${DOCKER_COMPOSE:-docker compose} ps"
    fi
}
trap cleanup EXIT

# -----------------------------------------------------------------------------
# Analyse des options
# -----------------------------------------------------------------------------
for arg in "$@"; do
    case "$arg" in
        -f|--force) FORCE=true ;;
        -h|--help)
            HELP_INVOKED=true
            echo "Usage : $0 [-f|--force]"
            echo ""
            echo "  -f, --force   Ne pas demander la confirmation interactive"
            echo "  -h, --help    Affiche cette aide"
            exit 0
            ;;
    esac
done

detect_compose

# -----------------------------------------------------------------------------
# Avertissement et confirmation
# -----------------------------------------------------------------------------
echo -e "\n${BOLD}${RED}======================================================${NC}"
echo -e "${BOLD}${RED}     MESURES - OPERATION SEMI-DESTRUCTIVE              ${NC}"
echo -e "${BOLD}${RED}======================================================${NC}"
echo -e "Ce script va, sur cette machine :"
echo -e "  - executer plusieurs cycles ${BOLD}docker compose down / up / stop / start${NC}"
echo -e "  - reconstruire les images (${BOLD}--build${NC})"
echo -e "  - lancer ${BOLD}./scripts/backup.sh${NC} puis ${BOLD}./scripts/restore.sh -f${NC}"
echo -e "    (la base sera ${BOLD}ECRASEE${NC} par le dump le plus recent)"
echo -e "  - envoyer 20 requetes HTTPS a https://localhost/api/health"
echo -e "${YELLOW}A ne PAS lancer sur un environnement de production en service.${NC}"
echo -e "${BOLD}${RED}======================================================${NC}\n"

if [[ "$FORCE" = false ]]; then
    read -r -p "Tapez 'MESURER' pour confirmer : " CONFIRM
    if [[ "$CONFIRM" != "MESURER" ]]; then
        log WARN "Mesures annulees par l'operateur."
        HELP_INVOKED=true   # evite le message d'erreur du piege
        exit 0
    fi
else
    log WARN "Option --force : confirmation ignoree."
fi

mkdir -p "$MESURES_DIR"

# -----------------------------------------------------------------------------
# Fonctions utilitaires
# -----------------------------------------------------------------------------

# Ecrit une ligne a la fois dans le rapport et sur la sortie standard.
report() {
    echo -e "$*" | tee -a "$REPORT_FILE"
}

# Etat consolide d'un conteneur : "healthy"/"starting"/... si healthcheck,
# sinon l'etat brut ("running", "exited"...). "absent" si le conteneur n'existe pas.
container_state() {
    docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1" 2>/dev/null || echo "absent"
}

# Attend que les QUATRE conteneurs soient sains.
#   - conteneur avec healthcheck : doit etre "healthy"
#   - conteneur sans healthcheck (ex. portail_caddy) : "running" accepte
# Renvoie 0 si tous sains avant le delai, 1 en cas de depassement.
wait_all_healthy() {
    local timeout="$1"
    local start now st all_ok
    start=$(date +%s)
    while true; do
        all_ok=true
        for c in "${CONTAINERS[@]}"; do
            st=$(container_state "$c")
            case "$st" in
                healthy|running) ;;
                *) all_ok=false ;;
            esac
        done
        if [[ "$all_ok" = true ]]; then
            return 0
        fi
        now=$(date +%s)
        if (( now - start >= timeout )); then
            return 1
        fi
        sleep 2
    done
}

# Affiche l'etat courant de chaque conteneur (diagnostic en cas d'echec).
dump_states() {
    local c st
    for c in "${CONTAINERS[@]}"; do
        st=$(container_state "$c")
        report "      ${c} : ${st}"
    done
}

# Mesure : execute les arguments comme une commande de demarrage, puis
# chronometre l'attente d'une pile saine.
#   $1 = libelle, $2 = delai max, reste = commande de mise en route
measure_startup() {
    local label="$1" timeout="$2"; shift 2
    local t0 t1 elapsed
    report "\n--- ${label} ---"
    report "  Commande : $*"
    t0=$(date +%s)
    if ! "$@" >/dev/null 2>&1; then
        report "  ${label} : ECHEC de la commande de demarrage."
        dump_states
        return 1
    fi
    if wait_all_healthy "$timeout"; then
        t1=$(date +%s)
        elapsed=$((t1 - t0))
        report "  ${label} : ${elapsed} s (4/4 services sains)"
    else
        t1=$(date +%s)
        elapsed=$((t1 - t0))
        report "  ${label} : ECHEC - pile non saine apres ${elapsed} s (delai ${timeout} s)."
        dump_states
        return 1
    fi
}

# -----------------------------------------------------------------------------
# En-tete du rapport
# -----------------------------------------------------------------------------
: > "$REPORT_FILE"
report "======================================================"
report " Portail Client - Releve de mesures SLA"
report "======================================================"
report " Date        : $(date '+%Y-%m-%d %H:%M:%S %z')"
report " Hote        : $(hostname)"
report " Docker      : $(docker --version 2>/dev/null || echo 'inconnu')"
report " Compose     : $($DOCKER_COMPOSE version 2>/dev/null | head -n1 || echo 'inconnu')"
report " Racine      : ${PROJECT_ROOT}"
report "------------------------------------------------------"
report " NOTE : ces chiffres sont propres a CETTE machine (CPU, disque,"
report " reseau, cache d'images). Ils DOIVENT etre re-mesures sur la"
report " machine de production pour etre inscrits dans le RUNBOOK ou"
report " l'ETUDE DE CAS."
report "======================================================"

# -----------------------------------------------------------------------------
# 1. Demarrage a froid
# -----------------------------------------------------------------------------
log INFO "Mesure 1/5 : demarrage a froid"
$DOCKER_COMPOSE -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true
measure_startup "Demarrage a froid (down + up -d --build)" "$HEALTH_TIMEOUT" \
    $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d --build || true

# -----------------------------------------------------------------------------
# 2. Demarrage a chaud
# -----------------------------------------------------------------------------
log INFO "Mesure 2/5 : demarrage a chaud"
$DOCKER_COMPOSE -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true
measure_startup "Demarrage a chaud (down + up -d, images conservees)" "$HEALTH_TIMEOUT" \
    $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d || true

# -----------------------------------------------------------------------------
# 3. Reprise apres arret (proxy du RTO reboot)
# -----------------------------------------------------------------------------
log INFO "Mesure 3/5 : reprise apres arret"
$DOCKER_COMPOSE -f "$COMPOSE_FILE" stop >/dev/null 2>&1 || true
measure_startup "Reprise apres arret (stop + start)" "$HEALTH_TIMEOUT" \
    $DOCKER_COMPOSE -f "$COMPOSE_FILE" start || true
report "  NOTE : ceci n'est qu'un PROXY. Le RTO reel d'un redemarrage de l'hote"
report "  (POST BIOS + boot noyau + demarrage de dockerd + conteneurs) doit etre"
report "  chronometre separement, au chronometre, lors d'un vrai reboot."

# -----------------------------------------------------------------------------
# 4. Duree de restauration
# -----------------------------------------------------------------------------
log INFO "Mesure 4/5 : duree de restauration"
report "\n--- Duree de restauration (backup.sh + restore.sh -f) ---"

if wait_all_healthy 120; then
    :
else
    report "  AVERTISSEMENT : la pile n'est pas totalement saine avant la mesure."
fi

R0=$(date +%s)
if ./scripts/backup.sh >/dev/null 2>&1; then
    R_BACKUP=$(date +%s)
    report "  Sauvegarde (backup.sh)   : $((R_BACKUP - R0)) s"
else
    report "  Sauvegarde (backup.sh)   : ECHEC (voir la configuration BACKUP_AGE_RECIPIENT / age)"
    R_BACKUP=$(date +%s)
fi

RESTORE_RC=0
./scripts/restore.sh -f >/dev/null 2>&1 || RESTORE_RC=$?
R_RESTORE=$(date +%s)
if [[ $RESTORE_RC -eq 0 ]]; then
    report "  Restauration (restore.sh): $((R_RESTORE - R_BACKUP)) s"
    report "  Total backup + restore   : $((R_RESTORE - R0)) s"
else
    report "  Restauration (restore.sh): ECHEC (code ${RESTORE_RC}) apres $((R_RESTORE - R_BACKUP)) s"
fi

# -----------------------------------------------------------------------------
# 5. Latence HTTP
# -----------------------------------------------------------------------------
log INFO "Mesure 5/5 : latence HTTP (/api/health x20)"
report "\n--- Latence HTTP (20 x GET https://localhost/api/health) ---"

wait_all_healthy 120 || report "  AVERTISSEMENT : pile non totalement saine, latences a interpreter avec prudence."

LAT_TMP="$(mktemp)"
for _ in $(seq 1 20); do
    t=$(curl -k -s -o /dev/null -w '%{time_total}' "https://localhost/api/health" 2>/dev/null || echo "")
    [[ -n "$t" ]] && echo "$t" >> "$LAT_TMP"
done

if [[ -s "$LAT_TMP" ]]; then
    SUMMARY=$(sort -n "$LAT_TMP" | awk '
        { a[NR]=$1 }
        END {
            n=NR
            min=a[1]*1000
            if (n%2==1) med=a[(n+1)/2]*1000
            else med=((a[n/2]+a[n/2+1])/2)*1000
            idx=int(0.95*n); if (idx < 1) idx=1; if (0.95*n > idx) idx=idx+1; if (idx>n) idx=n
            p95=a[idx]*1000
            printf "min=%.1f ms   mediane=%.1f ms   p95=%.1f ms   (n=%d)", min, med, p95, n
        }')
    report "  ${SUMMARY}"
else
    report "  ECHEC : aucune reponse HTTP obtenue (la pile ecoute-t-elle sur 443 ?)."
fi
rm -f "$LAT_TMP"

# -----------------------------------------------------------------------------
# Fin
# -----------------------------------------------------------------------------
report "\n======================================================"
report " Fin du releve : $(date '+%Y-%m-%d %H:%M:%S %z')"
report " Rapport enregistre : ${REPORT_FILE}"
report "======================================================"
