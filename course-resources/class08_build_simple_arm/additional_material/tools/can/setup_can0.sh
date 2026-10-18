#!/usr/bin/env bash
# One-time setup: install a systemd unit that configures can0 (1 Mbit/s, restart-ms 100) and brings it up
# automatically whenever the PCAN-USB adapter appears (boot, re-plug). Needs sudo once; afterwards the
# scripts for the physical arm never need `sudo ip link ...`.
#
#     sudo tools/can/setup_can0.sh          # install + start now
#     sudo tools/can/setup_can0.sh remove   # uninstall
set -euo pipefail
UNIT=/etc/systemd/system/can0.service
SRC="$(cd "$(dirname "$0")" && pwd)/can0.service"
if [[ $EUID -ne 0 ]]; then echo "Run with sudo: sudo $0 ${1:-}"; exit 1; fi
if [[ "${1:-}" == "remove" ]]; then
    systemctl disable --now can0.service 2>/dev/null || true
    rm -f "$UNIT"; systemctl daemon-reload
    echo "can0.service removed"; exit 0
fi
install -m 644 "$SRC" "$UNIT"
systemctl daemon-reload
systemctl enable can0.service
if [[ -e /sys/class/net/can0 ]]; then
    systemctl restart can0.service
    ip -br link show can0
else
    echo "No can0 now (USB-CAN adapter not connected). It is configured automatically when you connect it."
fi
echo "Done. After each boot and each re-plug of the USB-CAN adapter, can0 is set to 1 Mbit/s and UP automatically."
