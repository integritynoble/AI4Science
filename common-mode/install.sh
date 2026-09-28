#!/bin/sh
set -eu
VERSION=$(cat "$(dirname "$0")/VERSION")
PREFIX=${AI4SCIENCE_PREFIX:-"$HOME/.local/ai4science"}
ARCH=$(uname -m)
case "$(uname -s):$ARCH" in
  Linux:x86_64) PKG=opencode-linux-x64; FILE=opencode ;;
  Linux:aarch64|Linux:arm64) PKG=opencode-linux-arm64; FILE=opencode ;;
  Darwin:x86_64) PKG=opencode-darwin-x64; FILE=opencode ;;
  Darwin:arm64) PKG=opencode-darwin-arm64; FILE=opencode ;;
  *) echo "Unsupported platform: $(uname -s) $ARCH" >&2; exit 1 ;;
esac
case "$PKG" in
  opencode-linux-x64) INTEGRITY='sha512-q/t/3p2CTxOT9y2kvjesb/LZab2+1eqlhhWA02Be6mjTtmYtNBcBsrI5yDo4Fw7ZSPBW2oyMIGMNRqiKQjiAWw==' ;;
  opencode-linux-arm64) INTEGRITY='sha512-8aKOjIz6Cw3POGpvLvaByyMmfV2OCWgDdOBB9h7nqYV6rCGOzOsdQkT0OhjbAa5/JKGp28RSBEhDeMhINajs1g==' ;;
  opencode-darwin-x64) INTEGRITY='sha512-2y+0nvT9SEJu4MFJbymDR0YPoJNILEZrvguG4/dvkJm1EAKE9dzwfXk9iBsiq7BI2V3dnXqcg95e5Si/MNflxw==' ;;
  opencode-darwin-arm64) INTEGRITY='sha512-rZm4Phz7eu/kVz2lynergU/LzKS/L0ofErB2fRXfaoAH528b3EnVcISZ/13dwk78FPxVhop7hWXshowT88C8Yw==' ;;
esac
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
if [ -n "${AI4SCIENCE_PACKAGE_ARCHIVE:-}" ]; then
  cp "$AI4SCIENCE_PACKAGE_ARCHIVE" "$TMP/opencode.tgz"
else
  URL="https://registry.npmjs.org/$PKG/-/$PKG-$VERSION.tgz"
  curl -fL --retry 3 "$URL" -o "$TMP/opencode.tgz"
fi
ACTUAL="sha512-$(openssl dgst -sha512 -binary "$TMP/opencode.tgz" | base64 | tr -d '\n')"
if [ "$ACTUAL" != "$INTEGRITY" ]; then
  echo "OpenCode package integrity check failed for $PKG@$VERSION" >&2
  exit 1
fi
mkdir -p "$TMP/unpack" "$PREFIX/bin" "$PREFIX/config"
tar -xzf "$TMP/opencode.tgz" -C "$TMP/unpack"
install -m 755 "$TMP/unpack/package/bin/$FILE" "$PREFIX/bin/opencode"
install -m 755 "$(dirname "$0")/ai4science" "$PREFIX/bin/ai4science"
if [ ! -f "$PREFIX/config/opencode.json" ]; then
  cp "$(dirname "$0")/opencode.json" "$PREFIX/config/opencode.json"
fi
# OpenCode installs its selected provider adapter on first model use. Prime it
# now against an intentionally closed loopback port so the first real session
# does not need a package-registry connection. The expected request failure is
# suppressed; package download failures remain visible in OpenCode's log.
if [ ! -f "$PREFIX/.provider-primed" ]; then
  AI4SCIENCE_PREFIX="$PREFIX" AI4SCIENCE_OPENAI_BASE_URL=http://127.0.0.1:1/v1 \
    OPENAI_API_KEY=ai4science-install-placeholder \
    "$PREFIX/bin/ai4science" run --format json "bootstrap local provider" >/dev/null 2>&1 || true
  if [ ! -f "$PREFIX/xdg/config/opencode/node_modules/@opencode-ai/sdk/package.json" ]; then
    echo "OpenCode provider setup did not complete; check network access to npm and retry." >&2
    exit 1
  fi
  : > "$PREFIX/.provider-primed"
fi
printf 'Installed AI4Science common mode (OpenCode %s) in %s\n' "$VERSION" "$PREFIX"
printf 'Run: AI4SCIENCE_PREFIX=%s %s/bin/ai4science --version\n' "$PREFIX" "$PREFIX"
