#!/bin/bash
# Pre-load WireGuard "remote help" on the BirdNET display. Run once on Chris's bench.
# The parents never run this. After it finishes, the tunnel comes up by itself wherever the Pi has internet.
set -euo pipefail

usage() {
    echo "Usage: $0 --endpoint HOST:PORT --server-pubkey KEY --address IP/32 --vpn-subnet CIDR [--lan-subnet CIDR] [--dry-run DIR]" >&2
    exit 2
}

ENDPOINT="" SERVER_PUBKEY="" ADDRESS="" VPN_SUBNET="" LAN_SUBNET="" DRY_RUN_DIR=""
while [ $# -gt 0 ]; do
    case "$1" in
        --endpoint) ENDPOINT="${2:-}"; shift 2 ;;
        --server-pubkey) SERVER_PUBKEY="${2:-}"; shift 2 ;;
        --address) ADDRESS="${2:-}"; shift 2 ;;
        --vpn-subnet) VPN_SUBNET="${2:-}"; shift 2 ;;
        --lan-subnet) LAN_SUBNET="${2:-}"; shift 2 ;;
        --dry-run) DRY_RUN_DIR="${2:-}"; shift 2 ;;
        *) usage ;;
    esac
done

# shellcheck disable=SC2229  # read deliberately assigns to the variable *named* by $var
ask() { local var="$1" prompt="$2"; if [ -z "${!var}" ]; then read -rp "$prompt" "$var" || true; fi; }
ask ENDPOINT "WireGuard server endpoint (your DDNS name:port): "
ask SERVER_PUBKEY "WireGuard server public key: "
ask ADDRESS "This display's VPN address (e.g. 10.66.66.50/32): "
ask VPN_SUBNET "Your VPN subnet (e.g. 10.66.66.0/24): "

fail() { echo "ERROR: $1" >&2; exit 2; }
[[ "$ENDPOINT" =~ ^[A-Za-z0-9.-]+:[0-9]{1,5}$ ]] || fail "endpoint must look like host:port"
[[ "$SERVER_PUBKEY" =~ ^[A-Za-z0-9+/]{43}=$ ]] || fail "server public key must be a 44-character WireGuard key"
python3 -c 'import ipaddress,sys; ipaddress.ip_interface(sys.argv[1]); ipaddress.ip_network(sys.argv[2], strict=False)' \
    "$ADDRESS" "$VPN_SUBNET" 2>/dev/null || fail "address/subnet must be CIDR, e.g. 10.66.66.50/32 and 10.66.66.0/24"

if [ -z "$LAN_SUBNET" ]; then
    LAN_SUBNET="$(ip -o -f inet addr show wlan0 2>/dev/null | awk '{print $4}' | head -1 || true)"
fi
if [ -n "$LAN_SUBNET" ] && python3 -c 'import ipaddress,sys; sys.exit(0 if ipaddress.ip_interface(sys.argv[1]).network.overlaps(ipaddress.ip_network(sys.argv[2], strict=False)) else 1)' "$LAN_SUBNET" "$VPN_SUBNET"; then
    echo "WARNING: this network ($LAN_SUBNET) overlaps your VPN subnet ($VPN_SUBNET). Routing will be confused — pick a different VPN subnet." >&2
fi

if [ -n "$DRY_RUN_DIR" ]; then
    mkdir -p "$DRY_RUN_DIR"
    out() { echo "$DRY_RUN_DIR/$(basename "$1")"; }
    write() { cat > "$(out "$1")"; }
    SUDO=""
else
    out() { echo "$1"; }
    write() { sudo tee "$1" > /dev/null; }
    SUDO="sudo"
    sudo apt-get install -y wireguard-tools openssh-server
    sudo mkdir -p /etc/wireguard && sudo chmod 700 /etc/wireguard
fi

KEY_FILE="$(out /etc/wireguard/remote-help.key)"
if ! $SUDO test -s "$KEY_FILE"; then
    if command -v wg >/dev/null 2>&1; then
        (umask 077; wg genkey | $SUDO tee "$KEY_FILE" > /dev/null)
    elif [ -n "$DRY_RUN_DIR" ]; then
        (umask 077; echo "dry-run-private-key-$RANDOM" > "$KEY_FILE")
    else
        fail "wg not found after installing wireguard-tools"
    fi
fi
$SUDO chmod 600 "$KEY_FILE"
PRIVATE_KEY="$($SUDO cat "$KEY_FILE")"
if command -v wg >/dev/null 2>&1 && { [ -z "$DRY_RUN_DIR" ] || [ "${PRIVATE_KEY#dry-run}" = "$PRIVATE_KEY" ]; }; then
    PUBLIC_KEY="$(echo "$PRIVATE_KEY" | wg pubkey)"
else
    PUBLIC_KEY="dry-run-public-key"
fi

(umask 077; write /etc/wireguard/wg0.conf <<EOF
# Remote help tunnel to Chris's home (split tunnel: only the VPN subnet goes through it)
[Interface]
PrivateKey = $PRIVATE_KEY
Address = $ADDRESS

[Peer]
PublicKey = $SERVER_PUBKEY
Endpoint = $ENDPOINT
AllowedIPs = $VPN_SUBNET
PersistentKeepalive = 25
EOF
)
$SUDO chmod 600 "$(out /etc/wireguard/wg0.conf)"

write /usr/local/sbin/wg-reresolve <<EOF
#!/bin/sh
# Re-resolve the DDNS endpoint so the tunnel follows Chris's home IP when it changes.
exec wg set wg0 peer "$SERVER_PUBKEY" endpoint "$ENDPOINT"
EOF
$SUDO chmod 755 "$(out /usr/local/sbin/wg-reresolve)"

write /etc/systemd/system/wg-reresolve.service <<'EOF'
[Unit]
Description=Re-resolve WireGuard remote-help endpoint
After=wg-quick@wg0.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/wg-reresolve
EOF

write /etc/systemd/system/wg-reresolve.timer <<'EOF'
[Unit]
Description=Re-resolve WireGuard remote-help endpoint every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF

write /etc/ssh/sshd_config.d/50-remote-help.conf <<'EOF'
# Remote help: key-only SSH
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF

if [ -z "$DRY_RUN_DIR" ]; then
    if [ ! -s "$HOME/.ssh/authorized_keys" ]; then
        sudo rm -f /etc/ssh/sshd_config.d/50-remote-help.conf
        echo "WARNING: no ~/.ssh/authorized_keys yet — left password SSH on. Add your key (ssh-copy-id) and re-run." >&2
    fi
    sudo systemctl daemon-reload
    sudo systemctl enable --now ssh wg-quick@wg0 wg-reresolve.timer
    sudo systemctl reload ssh || true
fi

ADDR_ONLY="${ADDRESS%/*}"
cat <<EOF

Add this to your WireGuard SERVER config, then reload it:

[Peer]
# BirdNET display (parents)
PublicKey = $PUBLIC_KEY
AllowedIPs = $ADDR_ONLY/32

Then from anywhere on your VPN:  ssh $(whoami)@$ADDR_ONLY
Mic web page:                    ssh -L 8081:<mic-ip>:80 $(whoami)@$ADDR_ONLY  →  http://localhost:8081
EOF
