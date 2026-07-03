#!/bin/bash
# Generates a self-signed TLS certificate for the kiosk's HTTPS listener.
#
# Why this is needed at all: browsers only allow camera/microphone access
# (getUserMedia) on a "secure context" - https://, or http://localhost.
# A plain http://192.168.x.x URL from another machine on the LAN does NOT
# count, even though it's a private/trusted network. This cert lets you
# serve the kiosk over https:// to other LAN machines so their cameras work.
#
# Usage:
#   ./generate_cert.sh 192.168.1.10
#   (pass the Pi's LAN IP address as the only argument)
#
# Output: certs/kiosk.key and certs/kiosk.crt, valid for 10 years.
# This is a self-signed cert - browsers on OTHER machines will show a
# one-time security warning the first time they connect. That's expected
# and safe to accept on a trusted LAN (see README). It won't affect the
# kiosk's own on-Pi browser, which keeps using plain http://localhost and
# never touches this cert at all.

set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <pi-lan-ip>"
  echo "Example: $0 192.168.1.10"
  exit 1
fi

LAN_IP="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="$SCRIPT_DIR/../certs"
mkdir -p "$CERT_DIR"

CONFIG_FILE=$(mktemp)
cat > "$CONFIG_FILE" <<EOF
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = ${LAN_IP}

[v3_req]
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
IP.2 = ${LAN_IP}
EOF

openssl req -x509 -nodes -days 3650 \
  -newkey rsa:2048 \
  -keyout "$CERT_DIR/kiosk.key" \
  -out "$CERT_DIR/kiosk.crt" \
  -config "$CONFIG_FILE"

rm -f "$CONFIG_FILE"
chmod 600 "$CERT_DIR/kiosk.key"

echo
echo "Certificate written to:"
echo "  $CERT_DIR/kiosk.crt"
echo "  $CERT_DIR/kiosk.key"
echo
echo "Valid for: localhost, 127.0.0.1, ${LAN_IP}"
echo "Expires in 10 years."
