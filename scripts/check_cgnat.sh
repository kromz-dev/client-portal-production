#!/usr/bin/env bash
# =============================================================================
# check_cgnat.sh - Carrier-Grade NAT (CGNAT) Detection & Ingress Advisor
# =============================================================================
# Analyzes network interfaces, default gateway routes, and external public IPs
# to determine if the host is behind Carrier-Grade NAT (RFC 6598) or has a
# dedicated public IPv4 address.
#
# Guides the operator between:
#   - Path A: DuckDNS + Router Port Forwarding (80/443)
#   - Path B: Tailscale Funnel (Zero-port-forwarding CGNAT bypass)
# =============================================================================

set -euo pipefail

# ANSI Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Helper logging functions
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
alert()   { echo -e "${RED}[ALERT]${NC} $*"; }
step()    { echo -e "\n${BOLD}${CYAN}==> $*${NC}"; }

echo -e "${BOLD}======================================================${NC}"
echo -e "${BOLD}     CGNAT Detection & Public Ingress Advisor         ${NC}"
echo -e "${BOLD}======================================================${NC}"

# Check essential tools
for cmd in curl ip awk grep; do
    if ! command -v "$cmd" &>/dev/null; then
        alert "Required tool '$cmd' is not installed."
        exit 1
    fi
done

# -----------------------------------------------------------------------------
# 1. Local Network Inspection
# -----------------------------------------------------------------------------
step "1. Inspecting local network interfaces and routing"

DEFAULT_ROUTE=$(ip route show default 2>/dev/null | head -n1 || true)
if [[ -z "$DEFAULT_ROUTE" ]]; then
    alert "No default route found. Please verify your network connection."
    exit 1
fi

LOCAL_INTERFACE=$(echo "$DEFAULT_ROUTE" | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}')
DEFAULT_GATEWAY=$(echo "$DEFAULT_ROUTE" | awk '{for(i=1;i<=NF;i++) if($i=="via") print $(i+1)}')
LOCAL_IP=$(ip -4 addr show dev "$LOCAL_INTERFACE" 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n1 || true)

echo "  - Local Interface:  ${LOCAL_INTERFACE:-unknown}"
echo "  - Local IPv4:       ${LOCAL_IP:-unknown}"
echo "  - Default Gateway:  ${DEFAULT_GATEWAY:-unknown}"

# Helper function: Check if an IP falls within RFC 6598 (100.64.0.0/10)
is_rfc6598_cgnat() {
    local ip="$1"
    local first second
    first=$(echo "$ip" | cut -d. -f1)
    second=$(echo "$ip" | cut -d. -f2)

    if [[ "$first" -eq 100 ]] && [[ "$second" -ge 64 ]] && [[ "$second" -le 127 ]]; then
        return 0 # True: is CGNAT
    fi
    return 1 # False
}

# Helper function: Check if an IP falls within RFC 1918 (Private LAN)
is_rfc1918_private() {
    local ip="$1"
    local first second
    first=$(echo "$ip" | cut -d. -f1)
    second=$(echo "$ip" | cut -d. -f2)

    # 10.0.0.0/8
    if [[ "$first" -eq 10 ]]; then return 0; fi
    # 172.16.0.0/12 (172.16 - 172.31)
    if [[ "$first" -eq 172 ]] && [[ "$second" -ge 16 ]] && [[ "$second" -le 31 ]]; then return 0; fi
    # 192.168.0.0/16
    if [[ "$first" -eq 192 ]] && [[ "$second" -eq 168 ]]; then return 0; fi

    return 1
}

# -----------------------------------------------------------------------------
# 2. Public IP Query
# -----------------------------------------------------------------------------
step "2. Querying external public IPv4 address"

PUBLIC_IP=""
IP_SERVICES=(
    "https://api.ipify.org"
    "https://ifconfig.me/ip"
    "https://icanhazip.com"
    "https://ipecho.net/plain"
)

for service in "${IP_SERVICES[@]}"; do
    info "Querying $service ..."
    if PUBLIC_IP=$(curl -s4 --max-time 4 "$service" | tr -d '[:space:]'); then
        if [[ "$PUBLIC_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            success "Public IP retrieved: $PUBLIC_IP (via $service)"
            break
        fi
    fi
done

if [[ -z "$PUBLIC_IP" || ! "$PUBLIC_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    alert "Failed to retrieve public IPv4 address from external services."
    alert "Check internet connectivity and try again."
    exit 1
fi

# Reverse DNS lookup for public IP if host / dig is available
ISP_REVERSE_DNS=""
if command -v host &>/dev/null; then
    HOST_RES=$(host "$PUBLIC_IP" 2>/dev/null || true)
    if [[ "$HOST_RES" =~ pointer\ (.*)\. ]]; then
        ISP_REVERSE_DNS="${BASH_REMATCH[1]}"
        info "Reverse DNS (ISP Hostname): $ISP_REVERSE_DNS"
    fi
fi

# -----------------------------------------------------------------------------
# 3. CGNAT Assessment & Traceroute Analysis
# -----------------------------------------------------------------------------
step "3. Analyzing routing path for Carrier-Grade NAT"

CGNAT_DETECTED=false
REASON=""

# Case A: Machine has a direct WAN interface with RFC 6598 IP
if is_rfc6598_cgnat "$LOCAL_IP"; then
    CGNAT_DETECTED=true
    REASON="Local interface address ($LOCAL_IP) is inside RFC 6598 CGNAT block (100.64.0.0/10)."
fi

# Case B: Multi-hop trace inspection
SECOND_HOP=""
if command -v traceroute &>/dev/null; then
    info "Running quick traceroute (max 3 hops)..."
    HOP_OUTPUT=$(traceroute -n -m 3 -w 2 1.1.1.1 2>/dev/null || true)
    SECOND_HOP=$(echo "$HOP_OUTPUT" | awk '$1=="2" {for(i=2;i<=NF;i++) if($i ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/) {print $i; exit}}')
elif command -v tracepath &>/dev/null; then
    info "Running quick tracepath (max 3 hops)..."
    SECOND_HOP=$(tracepath -n -m 3 1.1.1.1 2>/dev/null | awk '$1=="2:" {print $2}' || true)
fi

if [[ -n "$SECOND_HOP" ]]; then
    info "Second network hop IP: $SECOND_HOP"
    if is_rfc6598_cgnat "$SECOND_HOP"; then
        CGNAT_DETECTED=true
        REASON="Second network hop ($SECOND_HOP) is inside RFC 6598 CGNAT block (100.64.0.0/10)."
    elif is_rfc1918_private "$SECOND_HOP"; then
        # Double NAT / ISP private gateway
        warn "Second network hop ($SECOND_HOP) is an RFC 1918 private IP (Double NAT or ISP internal routing)."
    fi
fi

# -----------------------------------------------------------------------------
# 4. Diagnostic Conclusions & Action Plan
# -----------------------------------------------------------------------------
step "4. Diagnosis & Recommended Ingress Strategy"

echo -e "Summary:"
echo "  - Local IP:       $LOCAL_IP"
echo "  - Default Gateway: $DEFAULT_GATEWAY"
echo "  - Public IP:      $PUBLIC_IP"
if [[ -n "$ISP_REVERSE_DNS" ]]; then
    echo "  - ISP Hostname:   $ISP_REVERSE_DNS"
fi

if [[ "$CGNAT_DETECTED" = true ]]; then
    echo ""
    alert "RESULT: CARRIER-GRADE NAT (CGNAT) DETECTED!"
    echo -e "Reason: ${BOLD}$REASON${NC}"
    echo ""
    echo -e "${YELLOW}Impact:${NC} Traditional port forwarding (ports 80 & 443) on your home router"
    echo "will NOT work because your ISP shares your public IPv4 among multiple subscribers."
    echo ""
    echo -e "${BOLD}${CYAN}RECOMMENDED SOLUTION: PATH B - TAILSCALE FUNNEL${NC}"
    echo "Tailscale Funnel provides a public HTTPS endpoint directly to your machine"
    echo "without requiring any open router ports or public IPv4 addresses."
    echo ""
    echo -e "${BOLD}Steps to configure Tailscale Funnel:${NC}"
    echo "  1. Install Tailscale:"
    echo "     curl -fsSL https://tailscale.com/install.sh | sh"
    echo ""
    echo "  2. Authenticate and start Tailscale:"
    echo "     sudo tailscale up"
    echo ""
    echo "  3. Enable Funnel to expose port 443 to the public internet:"
    echo "     sudo tailscale funnel 443 on"
    echo "     sudo tailscale serve --bg 80"
    echo ""
    echo "  4. Retrieve your public Tailscale Funnel FQDN:"
    echo "     tailscale status"
    echo "     (Example: your-server.tailnet-xyz.ts.net)"
    echo ""
    echo "  5. Set DOMAIN_NAME in your .env:"
    echo "     DOMAIN_NAME=your-server.tailnet-xyz.ts.net"
    echo ""
    echo -e "${CYAN}Alternative for French ISP customers (Freebox, Orange, etc.):${NC}"
    echo "  - Freebox: Log in to your Free subscriber area -> Ma Freebox -> Demander une adresse IP fixe V4 dédiée."
    echo "  - If granted a full IPv4 address, you can use Path A (DuckDNS) below."

else
    echo ""
    success "RESULT: NO IMMEDIATE CGNAT DETECTED (Dedicated or standard NAT)"
    echo ""
    echo -e "${BOLD}${GREEN}RECOMMENDED SOLUTION: PATH A - DUCKDNS + ROUTER PORT FORWARDING${NC}"
    echo "Your connection appears capable of hosting directly using DuckDNS and Let's Encrypt."
    echo ""
    echo -e "${BOLD}Steps to configure DuckDNS & Port Forwarding:${NC}"
    echo "  1. Create a free account at https://www.duckdns.org and add a domain"
    echo "     (e.g., 'portail-kram.duckdns.org')."
    echo ""
    echo "  2. Point the DuckDNS domain to your public IP ($PUBLIC_IP):"
    echo "     curl \"https://www.duckdns.org/update?domains=YOUR_DOMAIN&token=YOUR_TOKEN&ip=\""
    echo ""
    echo "  3. Log into your Internet Router/Box administration panel (typically http://$DEFAULT_GATEWAY):"
    echo "     - Assign a static DHCP lease for this machine ($LOCAL_IP)."
    echo "     - Forward external port 80 (TCP)  -> $LOCAL_IP:80"
    echo "     - Forward external port 443 (TCP & UDP) -> $LOCAL_IP:443"
    echo ""
    echo "  4. Configure .env:"
    echo "     DOMAIN_NAME=your-domain.duckdns.org"
    echo "     CADDY_EMAIL=your-email@example.com"
    echo ""
    echo "  5. Launch the stack:"
    echo "     docker compose up -d"
    echo ""
    echo -e "${YELLOW}Important Notice on French ISPs:${NC}"
    echo "  - If you use a Freebox with 'IP partagée' (shared IPv4 with port chunks),"
    echo "    you cannot bind ports 80/443 until you activate 'IP fixe V4 complète'."
    echo "  - If ports 80/443 remain unreachable from outside (test via 4G phone),"
    echo "    immediately switch to Path B (Tailscale Funnel)."
fi

echo ""
echo -e "${BOLD}======================================================${NC}"
