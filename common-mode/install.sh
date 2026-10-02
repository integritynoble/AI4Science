#!/bin/sh
set -eu
umask 077
ai4science_source=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
ai4science_prefix=${AI4SCIENCE_PREFIX:-"$HOME/.local/ai4science-common"}
if [ "$#" -gt 0 ]; then
  [ "$#" = 2 ] && [ "$1" = --prefix ] || { echo 'Usage: install.sh [--prefix DIRECTORY]' >&2; exit 2; }
  ai4science_prefix=$2
fi
case "$ai4science_prefix" in /*) ;; *) ai4science_prefix="$PWD/$ai4science_prefix" ;; esac
# Do not replace an existing installation, user settings, or another ai4science.
[ ! -e "$ai4science_prefix" ] || { echo 'Prefix already exists; choose an empty installation prefix.' >&2; exit 1; }
case "$(uname -s)" in Linux) ai4science_os=linux ;; Darwin) ai4science_os=darwin ;; *) echo 'Supported systems: Linux and macOS.' >&2; exit 1 ;; esac
case "$(uname -m)" in x86_64|amd64) ai4science_arch=x64 ;; aarch64|arm64) ai4science_arch=arm64 ;; *) echo 'Supported CPUs: x64 and arm64.' >&2; exit 1 ;; esac
ai4science_package="opencode-$ai4science_os-$ai4science_arch"
[ "$ai4science_arch" != x64 ] || ai4science_package="$ai4science_package-baseline"
if [ "$ai4science_os" = linux ]; then
  if [ -e /etc/alpine-release ] || (ldd --version 2>&1 | grep -qi musl); then
    [ "$ai4science_arch" != arm64 ] || { echo 'arm64 musl is unsupported: upstream has no matching ripgrep executable.' >&2; exit 1; }
    ai4science_package="$ai4science_package-musl"
  fi
fi
ai4science_record=$(awk -v p="$ai4science_package" '$1 == p { print; exit }' "$ai4science_source/artifacts.lock")
[ -n "$ai4science_record" ] || { echo 'No pinned artifact for this platform.' >&2; exit 1; }
ai4science_hash=$(printf '%s\n' "$ai4science_record" | awk '{print $2}')
ai4science_url=$(printf '%s\n' "$ai4science_record" | awk '{print $3}')
ai4science_stage=$(mktemp -d)
ai4science_cleanup() {
  find "$ai4science_stage" -type f -delete
  find "$ai4science_stage" -depth -type d -empty -delete
}
trap ai4science_cleanup EXIT
trap 'exit 1' HUP INT TERM
if [ -n "${AI4SCIENCE_ARTIFACT:-}" ]; then
  cp "$AI4SCIENCE_ARTIFACT" "$ai4science_stage/engine.tgz"
elif command -v curl >/dev/null 2>&1; then
  curl --fail --location --proto '=https' --tlsv1.2 --connect-timeout 15 --max-time 600 "$ai4science_url" -o "$ai4science_stage/engine.tgz"
elif command -v wget >/dev/null 2>&1; then
  wget --https-only --timeout=60 "$ai4science_url" -O "$ai4science_stage/engine.tgz"
else
  echo 'Install needs curl or wget to download the pinned executable.' >&2; exit 1
fi
if command -v sha512sum >/dev/null 2>&1; then
  ai4science_actual=$(sha512sum "$ai4science_stage/engine.tgz" | awk '{print $1}')
else
  ai4science_actual=$(shasum -a 512 "$ai4science_stage/engine.tgz" | awk '{print $1}')
fi
[ "$ai4science_actual" = "$ai4science_hash" ] || { echo 'Pinned artifact checksum mismatch; nothing installed.' >&2; exit 1; }
tar -xzf "$ai4science_stage/engine.tgz" -C "$ai4science_stage"
# OpenCode otherwise downloads ripgrep on the first session. Fetch and verify
# it during installation so even a cold session only calls the user's model.
ai4science_record=$(awk -v p="$ai4science_os-$ai4science_arch" '$1 == p { print; exit }' "$ai4science_source/ripgrep.lock")
[ -n "$ai4science_record" ] || { echo 'No pinned ripgrep for this platform.' >&2; exit 1; }
ai4science_hash=$(printf '%s\n' "$ai4science_record" | awk '{print $2}')
ai4science_url=$(printf '%s\n' "$ai4science_record" | awk '{print $3}')
if [ -n "${AI4SCIENCE_RIPGREP_ARTIFACT:-}" ]; then
  cp "$AI4SCIENCE_RIPGREP_ARTIFACT" "$ai4science_stage/ripgrep.tgz"
elif command -v curl >/dev/null 2>&1; then
  curl --fail --location --proto '=https' --tlsv1.2 --connect-timeout 15 --max-time 600 "$ai4science_url" -o "$ai4science_stage/ripgrep.tgz"
else
  wget --https-only --timeout=60 "$ai4science_url" -O "$ai4science_stage/ripgrep.tgz"
fi
if command -v sha256sum >/dev/null 2>&1; then
  ai4science_actual=$(sha256sum "$ai4science_stage/ripgrep.tgz" | awk '{print $1}')
else
  ai4science_actual=$(shasum -a 256 "$ai4science_stage/ripgrep.tgz" | awk '{print $1}')
fi
[ "$ai4science_actual" = "$ai4science_hash" ] || { echo 'Pinned ripgrep checksum mismatch; nothing installed.' >&2; exit 1; }
tar -xzf "$ai4science_stage/ripgrep.tgz" -C "$ai4science_stage"
ai4science_rg_dir=$(basename "$ai4science_url" .tar.gz)
mkdir -p "$ai4science_prefix/bin" "$ai4science_prefix/var/config/opencode" "$ai4science_prefix/share"
mkdir -p "$ai4science_prefix/var/cache/opencode/bin" "$ai4science_prefix/share/ripgrep"
cp "$ai4science_stage/$ai4science_rg_dir/rg" "$ai4science_prefix/var/cache/opencode/bin/rg"
chmod 755 "$ai4science_prefix/var/cache/opencode/bin/rg"
cp "$ai4science_stage/$ai4science_rg_dir/COPYING" "$ai4science_stage/$ai4science_rg_dir/LICENSE-MIT" "$ai4science_stage/$ai4science_rg_dir/UNLICENSE" "$ai4science_prefix/share/ripgrep/"
cp "$ai4science_stage/package/bin/opencode" "$ai4science_prefix/bin/opencode"
cp "$ai4science_source/ai4science" "$ai4science_prefix/bin/ai4science"
chmod 755 "$ai4science_prefix/bin/opencode" "$ai4science_prefix/bin/ai4science"
sed 's/"plugin": \[\]/"plugin": [".\/install-prime.mjs"]/' "$ai4science_source/defaults.json" > "$ai4science_prefix/var/config/opencode/opencode.json"
printf 'export default async () => ({})\n' > "$ai4science_prefix/var/config/opencode/install-prime.mjs"
cp "$ai4science_source/THIRD_PARTY_NOTICES.md" "$ai4science_source/README.md" "$ai4science_source/opencode.version" "$ai4science_source/artifacts.lock" "$ai4science_source/ripgrep.lock" "$ai4science_prefix/share/"
: > "$ai4science_prefix/empty-user.npmrc"
: > "$ai4science_prefix/empty-global.npmrc"
# The native runtime includes its package manager. Prime its config dependency
# during install (network allowed here), then require offline npm at runtime.
ai4science_version=$("$ai4science_prefix/bin/opencode" --version)
[ "$ai4science_version" = "$(cat "$ai4science_source/opencode.version")" ] || { echo 'Unexpected engine version.' >&2; exit 1; }
if ! AI4SCIENCE_INSTALL_DEPENDENCIES=1 "$ai4science_prefix/bin/ai4science" models own-llm > "$ai4science_prefix/var/install-models.txt" 2> "$ai4science_prefix/var/install.log"; then
  cp "$ai4science_source/defaults.json" "$ai4science_prefix/var/config/opencode/opencode.json"
  find "$ai4science_prefix/var/config/opencode/install-prime.mjs" -type f -delete
  echo 'Dependency setup failed. Private diagnostic log is in PREFIX/var/install.log.' >&2; exit 1
fi
cp "$ai4science_source/defaults.json" "$ai4science_prefix/var/config/opencode/opencode.json"
find "$ai4science_prefix/var/config/opencode/install-prime.mjs" -type f -delete
[ -d "$ai4science_prefix/var/config/opencode/node_modules/@opencode-ai/plugin" ] || { echo 'Config dependency setup did not finish; see PREFIX/var/install.log.' >&2; exit 1; }
"$ai4science_prefix/bin/ai4science" --version
printf 'Installed. Add this directory to PATH: %s/bin\n' "$ai4science_prefix"
