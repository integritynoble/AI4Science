"""The fixed, vetted operation registry — the Machine Agent's whole action surface.

There is deliberately NO "run an arbitrary command" operation. Every operation is
a closed, reviewed recipe with declared OS support, a side-effect class, and
whether it is consequential (⇒ owner-gated). This is what makes the agent safer
than an autonomous computer-use agent: the blast radius is the union of these
recipes, not "anything the shell can do".

Recipes are vetted argv (or a shell one-liner for the official installer). The
Linux/macOS paths are the real native installer; Windows is the PowerShell
installer. Only `install_claude_code`'s Linux recipe is exercised on this host;
the others are declared recipes selected by OS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple

# side effects that are consequential (require owner approval + audit)
CONSEQUENTIAL_SIDE_EFFECTS = ("install", "config", "credential")


@dataclass(frozen=True)
class Operation:
    name: str
    summary: str
    os_support: Tuple[str, ...]                 # subset of ("linux","macos","windows")
    side_effect: str                            # read | install | config | credential
    match: Tuple[str, ...] = field(default_factory=tuple)
    recipes: Dict[str, Tuple[str, ...]] = field(default_factory=dict)   # os -> argv
    account_scope: Optional[str] = None         # for credential ops: the lease scope

    @property
    def consequential(self) -> bool:
        return self.side_effect in CONSEQUENTIAL_SIDE_EFFECTS

    @property
    def owner_gated(self) -> bool:
        return self.consequential

    def recipe_for(self, os_id: str) -> Optional[Tuple[str, ...]]:
        return self.recipes.get(os_id)


# vetted install recipes for Claude Code (native installer; npm is the fallback path)
_CLAUDE_INSTALL = {
    "linux": ("sh", "-c", "curl -fsSL https://claude.ai/install.sh | bash"),
    "macos": ("sh", "-c", "curl -fsSL https://claude.ai/install.sh | bash"),
    "windows": ("powershell", "-Command", "irm https://claude.ai/install.ps1 | iex"),
}

# the specific permissions Claude Code needs — surfaced for the owner to grant,
# never blanket access.
CLAUDE_PERMISSIONS = (
    "fs:project-dir",      # read/write within the working project directory
    "net:anthropic-api",   # outbound to the Anthropic API
    "exec:bash-approved",  # run shell commands under Claude Code's own approval prompts
)


def default_operations() -> Tuple[Operation, ...]:
    return (
        Operation("detect", "report OS, arch, and what is installed",
                  ("linux", "macos", "windows"), "read",
                  match=("detect", "what os", "capabilities", "what's installed", "system info")),
        Operation("is_installed", "check whether Claude Code (or a tool) is installed",
                  ("linux", "macos", "windows"), "read",
                  match=("is claude installed", "check installed", "do i have claude", "already installed")),
        Operation("required_permissions", "list the specific permissions Claude Code needs",
                  ("linux", "macos", "windows"), "read",
                  match=("what permissions", "which permissions", "required permissions", "permissions does claude")),
        Operation("find_sessions", "find running Claude Code sessions on this machine (pid, cwd, governed?)",
                  ("linux", "macos", "windows"), "read",
                  match=("find claude", "claude session", "running claude", "check claude process",
                         "claude process", "find the claude", "which claude are running", "list claude")),
        Operation("install_claude_code", "install Claude Code via the official installer",
                  ("linux", "macos", "windows"), "install",
                  match=("install claude", "set up claude", "get claude code", "bootstrap claude"),
                  recipes=_CLAUDE_INSTALL),
        Operation("grant_permission", "record an owner-approved, specific permission for Claude Code",
                  ("linux", "macos", "windows"), "config",
                  match=("grant permission", "allow claude", "give claude permission", "approve permission")),
        Operation("broker_login", "log in to an account for Claude Code via the credential broker",
                  ("linux", "macos", "windows"), "credential",
                  match=("log in", "login", "authenticate", "sign in", "connect account"),
                  account_scope="claude-login"),
    )
