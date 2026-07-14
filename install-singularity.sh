#!/bin/sh
# Personal Singularity — one-command installer (codex-style, prebuilt binary).
#
#   curl -fsSL https://raw.githubusercontent.com/integritynoble/AI4Science/main/install-singularity.sh | sh
#
# Downloads a standalone `singularity` binary for your platform (no Python/pipx
# needed), then checks host prerequisites and brings up the governed control
# plane + first agent. This repo (AI4Science) is only the public distribution
# front door; the `singularity` and `pwm-control-plane` source repos stay private.
#
# Podman is a host requirement (rootless Podman *is* the sandbox — the safety
# model). `singularity doctor` surfaces it; this script never proceeds silently
# without it.
set -eu

BRAND="singularity"
# Public release channel: a dedicated tag on AI4Science, so ai4science's own
# "latest" release is untouched.
DIST_BASE="${SINGULARITY_DIST_URL:-https://github.com/integritynoble/AI4Science/releases/download/singularity-v0.1.0}"
BIN_DIR="${SINGULARITY_BIN_DIR:-$HOME/.local/bin}"

say() { printf '[%s] %s\n' "$BRAND" "$*"; }
die() { say "$*"; exit 1; }

# 1. detect platform -> asset name (singularity-<os>-<arch>)
os="$(uname -s | tr '[:upper:]' '[:lower:]')"
arch="$(uname -m)"
case "$os" in
    linux|darwin) ;;
    *) die "unsupported OS: $os (linux and macOS only)" ;;
esac
case "$arch" in
    x86_64|amd64) arch="x86_64" ;;
    arm64|aarch64) arch="arm64" ;;
    *) die "unsupported architecture: $arch" ;;
esac
asset="singularity-${os}-${arch}"
url="${DIST_BASE}/${asset}"

# 2. download the prebuilt binary
say "downloading ${asset}"
mkdir -p "$BIN_DIR"
tmp="$(mktemp)"
if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$tmp" || die "download failed: $url (no binary for this platform yet?)"
elif command -v wget >/dev/null 2>&1; then
    wget -qO "$tmp" "$url" || die "download failed: $url (no binary for this platform yet?)"
else
    die "need curl or wget to download the binary"
fi
chmod +x "$tmp"
mv "$tmp" "$BIN_DIR/singularity"
say "installed ${asset} -> $BIN_DIR/singularity"

# 3. PATH hint
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) say "note: add $BIN_DIR to PATH:  export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

# 4. prerequisites, then bring it up
SING="$BIN_DIR/singularity"
say "checking host prerequisites"
if ! "$SING" doctor; then
    say "prerequisites are missing (see above). Fix them, then run: singularity up"
    exit 2
fi
say "starting the governed control plane + first agent"
exec "$SING" up
