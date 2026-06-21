#!/usr/bin/env bash
# AI4Science installer — one-line install, no root / pipx / system packages.
#
#   curl -fsSL https://raw.githubusercontent.com/integritynoble/AI4Science/main/install.sh | bash
#
# Creates an isolated venv under ~/.ai4science and links the `ai4science`
# command into ~/.local/bin. Works on locked-down HPC login nodes.
#
# Env overrides:
#   AI4SCIENCE_HOME=<dir>     install location (default ~/.ai4science)
#   AI4SCIENCE_BIN=<dir>      where to link the command (default ~/.local/bin)
#   AI4SCIENCE_WITH_CLAUDE=0  skip the [claude] chat-agent extra (lean install).
#                             Default is 1 — the chat agent is installed so
#                             `ai4science` is a Claude-Code-like session.
#   AI4SCIENCE_REF=<spec>     override the install source (pip requirement)
set -euo pipefail

PKG="pwm-ai4science"
GH="https://github.com/integritynoble/AI4Science/archive/refs/heads"
INSTALL_DIR="${AI4SCIENCE_HOME:-$HOME/.ai4science}"
VENV="$INSTALL_DIR/venv"
BIN_DIR="${AI4SCIENCE_BIN:-$HOME/.local/bin}"
WITH_CLAUDE="${AI4SCIENCE_WITH_CLAUDE:-1}"

# Release channel (Part A): stable (default) | rc | dev. Select with --rc/--dev/
# --stable or AI4SCIENCE_CHANNEL; each maps to a GitHub branch ZIP (no git needed,
# pip downloads over HTTP). PyPI is phase 2. AI4SCIENCE_REF still overrides all.
CHANNEL="${AI4SCIENCE_CHANNEL:-stable}"
for _a in "$@"; do
  case "$_a" in
    --dev) CHANNEL=dev ;; --rc) CHANNEL=rc ;; --stable) CHANNEL=stable ;;
  esac
done
case "$CHANNEL" in
  stable) BRANCH=stable ;; rc) BRANCH=rc ;; dev) BRANCH=main ;;
  *) printf '\033[31m✗ unknown channel %s (use stable|rc|dev)\033[0m\n' "$CHANNEL" >&2; exit 1 ;;
esac
ZIP_URL="$GH/${BRANCH}.zip"

say()  { printf '\033[36m▸\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

say "Installing AI4Science (command: ai4science)…"

# 1. Find a Python >= 3.10.
find_python() {
  for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
    command -v "$c" >/dev/null 2>&1 || continue
    "$c" - <<'PYEOF' >/dev/null 2>&1 || continue
import sys
raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 1)
PYEOF
    echo "$c"; return 0
  done
  return 1
}
# 1b. If no suitable Python exists, download a self-contained one (no system
# Python, compiler, or admin rights needed) from Astral's python-build-standalone
# into $INSTALL_DIR/python. This is what makes the installer work on a bare macOS
# or Windows box. Pinned to a minor series for wheel compatibility.
PBS_API="https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"
PBS_PYVER="${AI4SCIENCE_PYVER:-3.12}"

pbs_url() {  # $1 = target triple → echoes the install_only.tar.gz download URL
  curl -fsSL "$PBS_API" 2>/dev/null \
    | grep -o '"browser_download_url": *"[^"]*cpython-'"${PBS_PYVER}"'\.[0-9]*%2B[0-9]*-'"$1"'-install_only\.tar\.gz"' \
    | head -n1 | sed 's/.*"browser_download_url": *"//; s/"$//'
}

bootstrap_python() {  # echoes the path to a freshly downloaded standalone python3
  local os arch triple url tgz
  os="$(uname -s)"; arch="$(uname -m)"
  case "$os" in
    Darwin) case "$arch" in arm64|aarch64) triple=aarch64-apple-darwin ;; *) triple=x86_64-apple-darwin ;; esac ;;
    Linux)  case "$arch" in aarch64|arm64) triple=aarch64-unknown-linux-gnu ;; *) triple=x86_64-unknown-linux-gnu ;; esac ;;
    *) return 1 ;;
  esac
  url="$(pbs_url "$triple")"; [ -n "$url" ] || return 1
  say "No suitable Python found — downloading a standalone Python ${PBS_PYVER} ($triple)…" >&2
  mkdir -p "$INSTALL_DIR"
  tgz="$INSTALL_DIR/.python-dl.tar.gz"
  curl -fsSL "$url" -o "$tgz" || return 1
  rm -rf "$INSTALL_DIR/python"
  tar -xzf "$tgz" -C "$INSTALL_DIR" >/dev/null 2>&1 || return 1   # extracts a 'python/' dir
  rm -f "$tgz"
  [ -x "$INSTALL_DIR/python/bin/python3" ] || return 1
  echo "$INSTALL_DIR/python/bin/python3"
}

if ! PY="$(find_python)"; then
  if ! PY="$(bootstrap_python)"; then
    case "$(uname -s)" in
      Darwin)
        _hint="Auto-download failed (no network?). Install Python yourself:
   brew install python@3.12   (or https://www.python.org/downloads/macos/)
   Note: the Command Line Tools python3 is often 3.9 and too old." ;;
      Linux)
        _hint="Auto-download failed (no network?). Install Python yourself:
   Debian/Ubuntu:  sudo apt install python3 python3-venv
   Fedora/RHEL:    sudo dnf install python3 ;  HPC: module load python/3.11" ;;
      *)
        _hint="Install Python 3.10+ and ensure it's on your PATH, then re-run." ;;
    esac
    die "Python >= 3.10 not found on PATH.
   $_hint"
  fi
fi
ok "Using $("$PY" --version 2>&1) ($(command -v "$PY"))"

# 2. Isolated venv.
say "Creating venv at $VENV"
"$PY" -m venv "$VENV" || die "could not create venv (is python3-venv available?)"
"$VENV/bin/pip" install --quiet --upgrade pip >/dev/null

# 3. Install the chosen channel: PyPI first for stable/rc (phase 2), then the
#    branch ZIP from GitHub (no git needed), then dev (main) as a last resort.
extra=""; [ "$WITH_CLAUDE" = "1" ] && extra="[claude]"
_src() { local url="$1"; if [ -n "$extra" ]; then echo "${PKG}${extra} @ ${url}"; else echo "$url"; fi; }
if [ -n "${AI4SCIENCE_REF:-}" ]; then
  say "Installing from AI4SCIENCE_REF=$AI4SCIENCE_REF"
  "$VENV/bin/pip" install --quiet "$AI4SCIENCE_REF" || die "install failed"
else
  pre=""; [ "$CHANNEL" = rc ] && pre="--pre"
  ok_install=0
  # 3a. PyPI (stable/rc only; dev is never published to PyPI).
  if [ "$CHANNEL" != dev ]; then
    say "Installing the [$CHANNEL] channel from PyPI…"
    if "$VENV/bin/pip" install --quiet $pre "${PKG}${extra}" 2>/dev/null; then
      ok "Installed $PKG ([$CHANNEL] channel) from PyPI"; ok_install=1
    fi
  fi
  # 3b. GitHub branch ZIP fallback (before PyPI is published / for dev).
  if [ "$ok_install" = 0 ]; then
    say "Installing [$CHANNEL] from the $BRANCH branch zip…"
    if "$VENV/bin/pip" install --quiet "$(_src "$ZIP_URL")" 2>/dev/null; then
      ok "Installed $PKG ([$CHANNEL] channel) from GitHub"; ok_install=1
    elif [ "$BRANCH" != main ]; then
      # stable/rc branch absent (before first cut) → fall back to dev (main).
      say "[$CHANNEL] not published yet — falling back to dev (main)."
      CHANNEL=dev
      "$VENV/bin/pip" install --quiet "$(_src "$GH/main.zip")" \
        && ok_install=1 || die "install failed — check network access to github.com"
    fi
  fi
  [ "$ok_install" = 1 ] || die "install failed — check network access"
fi

# Record the channel so `ai4science update` keeps the user on this line.
mkdir -p "$INSTALL_DIR"; printf '%s\n' "$CHANNEL" > "$INSTALL_DIR/channel"

# 4. Expose the command on PATH.
mkdir -p "$BIN_DIR"
ln -sf "$VENV/bin/ai4science" "$BIN_DIR/ai4science"
ok "Linked $BIN_DIR/ai4science"

VER="$("$VENV/bin/ai4science" version 2>/dev/null || echo "ai4science")"
ok "Installed: $VER"

# 5. Put BIN_DIR on PATH — auto-add to the user's shell rc (idempotent).
#    Opt out with AI4SCIENCE_NO_MODIFY_PATH=1 (then we only print guidance).
NO_MODIFY_PATH="${AI4SCIENCE_NO_MODIFY_PATH:-0}"
PATH_LINE="export PATH=\"$BIN_DIR:\$PATH\""

add_path_to() {  # append PATH_LINE to a shell rc unless it's already there
  local rc="$1"
  [ -e "$rc" ] || return 1                       # only touch files that exist…
  grep -qF "$BIN_DIR" "$rc" 2>/dev/null && return 0   # …already references it → done
  printf '\n# Added by AI4Science installer\n%s\n' "$PATH_LINE" >> "$rc" \
    && echo "$rc"                                 # echo which file we changed
}

case ":$PATH:" in
  *":$BIN_DIR:"*)
    ok "$BIN_DIR already on PATH"
    ;;
  *)
    if [ "$NO_MODIFY_PATH" = "1" ]; then
      printf '\n\033[33m%s is not on your PATH.\033[0m Add this (and put it in ~/.bashrc):\n' "$BIN_DIR"
      printf '    %s\n' "$PATH_LINE"
    else
      # Write to the rc for the user's ACTUAL shell, creating it if missing.
      # macOS defaults to zsh, which never reads ~/.profile — the old behavior of
      # only creating ~/.profile on a fresh box left the command off-PATH there.
      shell_name="$(basename "${SHELL:-sh}")"
      case "$shell_name" in
        zsh)  primary_rc="$HOME/.zshrc" ;;
        bash) primary_rc="$HOME/.bashrc" ;;
        *)    primary_rc="$HOME/.profile" ;;
      esac
      touch "$primary_rc" 2>/dev/null || true
      changed=""
      # primary rc first (now exists), then any other existing rc files; add_path_to
      # is idempotent so a file listed twice is only written once.
      for rc in "$primary_rc" "$HOME/.zshrc" "$HOME/.zprofile" "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile"; do
        [ -e "$rc" ] || continue
        out="$(add_path_to "$rc")" && [ -n "$out" ] && changed="$changed $out"
      done
      if [ -n "$changed" ]; then
        ok "Added $BIN_DIR to PATH in:$changed"
      else
        ok "$BIN_DIR already configured in your shell startup files"
      fi
      printf '\033[33mOpen a new terminal, or run:\033[0m  export PATH="%s:$PATH"\n' "$BIN_DIR"
    fi
    ;;
esac

echo
if [ "$WITH_CLAUDE" = "1" ]; then
  ok "Chat agent (Claude Code-like) installed."
  echo "Start a chat session:"
  echo "    ai4science"
  if ! command -v claude >/dev/null 2>&1; then
    printf '\n\033[33mThe chat agent also needs the `claude` CLI:\033[0m\n'
    echo "    npm install -g @anthropic-ai/claude-code   # then: claude login"
    echo "    (or set ANTHROPIC_API_KEY). Until then, the commands below work offline.)"
  fi
  echo
  echo "Or run a deterministic command (no agent needed):"
  echo "    ai4science init my-first-contribution"
  echo "    ai4science --help"
  echo
  echo "Lean install without the chat agent:  AI4SCIENCE_WITH_CLAUDE=0 curl … | bash"
else
  cat <<'EOF'
Done. Try:
    ai4science --help
    ai4science init my-first-contribution

The chat agent was skipped (AI4SCIENCE_WITH_CLAUDE=0). To enable it, reinstall
with the default (omit AI4SCIENCE_WITH_CLAUDE) and install the `claude` CLI:
    npm install -g @anthropic-ai/claude-code   # then: claude login
EOF
fi
