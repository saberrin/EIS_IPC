#!/bin/bash
# Configure the dedicated EIS Ethernet interface with a persistent static IP.

set -u

STATIC_CIDR="${EIS_STATIC_CIDR:-192.168.98.3/24}"
SERVER_IP="${EIS_SERVER_IP:-192.168.98.2}"
REQUESTED_INTERFACE="${EIS_NETWORK_INTERFACE:-${1:-}}"
PROFILE_PREFIX="eis-static"

log() {
    echo "[EIS network] $*"
}

fail() {
    echo "[EIS network] Error: $*" >&2
    exit 1
}

if [ "$EUID" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        exec sudo \
            EIS_STATIC_CIDR="$STATIC_CIDR" \
            EIS_SERVER_IP="$SERVER_IP" \
            EIS_NETWORK_INTERFACE="$REQUESTED_INTERFACE" \
            bash "$0"
    fi
    fail "Run this script as root or install sudo."
fi

command -v ip >/dev/null 2>&1 || fail "The ip command is required."

list_wired_interfaces() {
    local path iface type
    for path in /sys/class/net/*; do
        [ -e "$path" ] || continue
        iface="$(basename "$path")"
        case "$iface" in
            lo|docker*|veth*|virbr*|br-*|tun*|tap*|wg*) continue ;;
        esac
        [ -d "$path/wireless" ] && continue
        type="$(cat "$path/type" 2>/dev/null || true)"
        [ "$type" = "1" ] && echo "$iface"
    done
}

select_interface() {
    local default_iface candidates candidate_count iface

    if [ -n "$REQUESTED_INTERFACE" ]; then
        [ -d "/sys/class/net/$REQUESTED_INTERFACE" ] || \
            fail "Interface '$REQUESTED_INTERFACE' does not exist."
        echo "$REQUESTED_INTERFACE"
        return
    fi

    default_iface="$(ip route show default 2>/dev/null | awk 'NR == 1 {print $5}')"
    mapfile -t candidates < <(list_wired_interfaces)
    [ "${#candidates[@]}" -gt 0 ] || fail "No wired Ethernet interface was found."

    if [ "${#candidates[@]}" -gt 1 ] && [ -n "$default_iface" ]; then
        mapfile -t candidates < <(printf '%s\n' "${candidates[@]}" | grep -vx "$default_iface" || true)
    fi

    candidate_count="${#candidates[@]}"
    if [ "$candidate_count" -eq 1 ]; then
        echo "${candidates[0]}"
        return
    fi

    log "Available dedicated Ethernet interfaces:" >&2
    for iface in "${candidates[@]}"; do
        echo "  - $iface" >&2
    done
    read -r -p "Enter the interface connected to the EIS server: " iface
    [ -d "/sys/class/net/$iface" ] || fail "Interface '$iface' does not exist."
    echo "$iface"
}

configure_with_network_manager() {
    local iface="$1"
    local profile="${PROFILE_PREFIX}-${iface}"

    if nmcli -g NAME connection show "$profile" >/dev/null 2>&1; then
        log "Updating NetworkManager profile '$profile'."
    else
        log "Creating NetworkManager profile '$profile'."
        nmcli connection add type ethernet ifname "$iface" con-name "$profile" >/dev/null || return 1
    fi

    nmcli connection modify "$profile" \
        connection.interface-name "$iface" \
        connection.autoconnect yes \
        connection.autoconnect-priority 100 \
        ipv4.method manual \
        ipv4.addresses "$STATIC_CIDR" \
        ipv4.gateway "" \
        ipv4.dns "" \
        ipv4.never-default yes \
        ipv6.method disabled || return 1

    if ! nmcli connection up "$profile" ifname "$iface" >/dev/null; then
        log "Profile saved. It will activate automatically when the cable is connected."
    fi
}

configure_with_netplan() {
    local iface="$1"
    local netplan_file="/etc/netplan/99-eis-static-network.yaml"

    command -v netplan >/dev/null 2>&1 || \
        fail "Neither NetworkManager nor Netplan is available."

    log "Writing persistent Netplan configuration to $netplan_file."
    cat > "$netplan_file" <<EOF
network:
  version: 2
  ethernets:
    ${iface}:
      dhcp4: false
      dhcp6: false
      addresses:
        - ${STATIC_CIDR}
      optional: true
EOF
    chmod 600 "$netplan_file"
    netplan generate || return 1
    netplan apply || return 1
}

INTERFACE="$(select_interface)"
log "Selected interface: $INTERFACE"
log "Static address: $STATIC_CIDR"
log "EIS server: $SERVER_IP"

if command -v nmcli >/dev/null 2>&1 && systemctl is-active --quiet NetworkManager 2>/dev/null; then
    configure_with_network_manager "$INTERFACE" || fail "NetworkManager configuration failed."
else
    configure_with_netplan "$INTERFACE" || fail "Netplan configuration failed."
fi

log "Current interface state:"
ip -br address show dev "$INTERFACE"
log "The configuration persists across reboots and does not install a default route."

if ping -c 1 -W 1 "$SERVER_IP" >/dev/null 2>&1; then
    log "Server $SERVER_IP is reachable."
else
    log "Server $SERVER_IP is not reachable yet. Check its cable, IP address, and firewall."
fi
