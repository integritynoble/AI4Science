"""ai4science — session-style CLI for Physics World Model contributions.

Two surfaces:

1. **Subcommand mode** (deterministic):
       ai4science init <name>
       ai4science contribute <type>
       ai4science validate
       ai4science judge cassi --submission .
       ai4science overseer review --submission .
       ai4science package
       ai4science submit --dry-run

2. **Prompt-first mode** (one-shot):
       ai4science --agent claude "Help me draft a CASSI spec"
       ai4science --agent none "Validate my PWM contribution"

   The router first tries rule-based intent detection (free, deterministic).
   If nothing matches and --agent is claude/codex AND is_available(), it
   hands the prompt off to the selected agent provider for an LLM call.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from ai4science import __version__
from ai4science.agents import get_agent
from ai4science.commands import (
    init as init_cmd,
    contribute as contribute_cmd,
    validate as validate_cmd,
    judge as judge_cmd,
    overseer as overseer_cmd,
    package as package_cmd,
    submit as submit_cmd,
    status as status_cmd,
    chat as chat_cmd,
)

# On Windows the default console code page (cp1252) cannot encode the Unicode
# glyphs (✓ ✗ ⚠ box-drawing) that Rich emits, raising UnicodeEncodeError mid-
# render. Force UTF-8 on the standard streams so the CLI works without the user
# having to set PYTHONIOENCODING=utf-8 by hand.
if os.name == "nt":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

# Terminals that don't answer ESC[6n (some SSH/web/CI shells — e.g. agent-prod)
# would otherwise trap prompt_toolkit in a repeating "Press ENTER to continue…
# (CPR not supported)" loop. The full-screen TUI paints from (0,0) and never
# needs cursor-position reports, so disable CPR process-wide BEFORE any
# prompt_toolkit Application is created. setdefault → an explicit
# PROMPT_TOOLKIT_NO_CPR in the environment still wins.
os.environ.setdefault("PROMPT_TOOLKIT_NO_CPR", "1")

console = Console()

# Module-level state for the agent the user selected via --agent. We thread
# it through sys.argv parsing because Typer's no_args_is_help wraps the app
# in a way that doesn't naturally compose with our prompt-first dispatcher.
_SELECTED_AGENT: Optional[str] = None


app = typer.Typer(
    name="ai4science",
    help=(
        "AI4Science — session-style CLI for Physics World Model contributions.\n"
        "Run with a subcommand (init, contribute, validate, judge, overseer, package, "
        "submit, status) OR with a free-form English prompt in quotes."
    ),
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    add_completion=False,
)


# ─── Subcommands ───────────────────────────────────────────────────────


app.add_typer(contribute_cmd.app, name="contribute",
              help="Create a Principle / Spec / Benchmark / Solution from the template.")
app.add_typer(judge_cmd.app, name="judge",
              help="Run the deterministic Physics Judge on a submission.")
app.add_typer(overseer_cmd.app, name="overseer",
              help="Local Overseer review combining validate + judge + claim checks.")

from ai4science.commands import compute as compute_cmd
app.add_typer(compute_cmd.app, name="compute",
              help="Wallet-bound GPU compute providers (dispatch + judge-verified rewards).")

from ai4science.commands import provider as provider_cmd
app.add_typer(provider_cmd.app, name="provider",
              help="Become a paid compute provider in one command: provider start --wallet 0x…")

from ai4science.commands import llm as llm_cmd
app.add_typer(llm_cmd.app, name="llm",
              help="Wallet-bound LLM providers (subscription / api-key / comparegpt).")

from ai4science.commands import stake as stake_cmd
app.add_typer(stake_cmd.app, name="stake",
              help="Provider stake / collateral (lock PWM to be eligible).")

# Optional: the `plugins` command ships separately. Import defensively so a
# build WITHOUT ai4science/commands/plugins.py can never crash the whole CLI on
# startup (which would also break `ai4science update`, making it unrecoverable).
try:
    from ai4science.commands import plugins as plugins_cmd
    app.add_typer(plugins_cmd.app, name="plugins",
                  help="Install community plug-ins (agents/tools) from physicsworldmodel.org.")
except Exception:
    plugins_cmd = None

try:
    from ai4science.commands import tools as tools_cmd
    from ai4science.commands.tools import app as tools_app
    app.add_typer(tools_app, name="tools",
                  help="Install community protools (kind=tool) from physicsworldmodel.org.")
except Exception:
    tools_cmd = None

# Single-command leaves
app.command("init", help="Create a new contribution workspace.")(init_cmd.init)
app.command("validate", help="Validate YAML front matter and required fields.")(validate_cmd.validate)
app.command("package", help="Package the submission and generate hashes.")(package_cmd.package)
app.command("submit", help="Submit (dry-run for v0.1).")(submit_cmd.submit)
app.command("status", help="Show local workspace status.")(status_cmd.status)
app.command("chat", help="Open a persistent REPL chat session with the agent.")(chat_cmd.chat)

from ai4science.commands import login as login_cmd
app.command("login", help="Log in via browser approval on physicsworldmodel.org (like `claude login`). Flags: --provider for your own LLM, --wallet for the local hot-key wallet.")(login_cmd.login)
app.command("whoami", help="Show how the agent is currently powered.")(login_cmd.whoami)
app.command("logout", help="Clear the current login.")(login_cmd.logout)
app.command("prefer", help="Set credential preference: user | wallet | <provider_id>.")(login_cmd.prefer)

from ai4science.commands import update as update_cmd
app.command("update", help="Upgrade ai4science to the latest build (like `claude update`).")(update_cmd.update)

from ai4science.commands import register_agent as register_agent_cmd
app.command("register-agent", help="Self-register a plug-in agent/tool you authored to physicsworldmodel.org (counts toward the Developer Winner after admin approval).")(register_agent_cmd.register_agent)
from ai4science.commands import feedback as feedback_cmd
app.command("feedback", help="Give feedback on an ai4science agent and earn PWM for useful, novel signal (Track 2).")(feedback_cmd.feedback)
app.command("report-bug", help="Report a bug in an ai4science agent and earn PWM if it's real + reproducible. Attach the error via --log or by piping it in.")(feedback_cmd.report_bug)


@app.command("version", help="Print the AI4Science CLI version + release channel.")
def version_cmd() -> None:
    try:
        from ai4science.commands.update import read_channel
        chan = read_channel()
    except Exception:
        chan = "stable"
    console.print(f"ai4science {__version__} ({chan})")


@app.command("agents", help="List configured agent providers and their availability.")
def agents_cmd() -> None:
    """Report on each known agent provider's availability + auth hint."""
    from rich.table import Table
    table = Table(title="Agent providers", show_lines=True)
    table.add_column("Provider", style="cyan")
    table.add_column("Available")
    table.add_column("Notes")
    for name in ("none", "claude", "codex"):
        agent = get_agent(name)
        ok = agent.is_available()
        notes = getattr(agent, "unavailable_reason", lambda: "")()
        table.add_row(name, "[green]yes[/green]" if ok else "[yellow]no[/yellow]", notes)
    console.print(table)


# ─── Prompt-first dispatch ─────────────────────────────────────────────


# Routing splits into UTILITY intents (always rule-dispatched — no LLM is
# useful for `validate`, `judge`, `package`, etc.) and DRAFTING intents
# (rule-dispatched only when --agent=none; routed to the agent otherwise,
# because that's why the user picked an agent).
#
# The v0.1 bug was that "draft a CASSI principle" matched "cassi" → judge_cassi.
# Two structural fixes here:
#   1. Split utility (always deterministic) from drafting (LLM if available)
#   2. Inside each tier, verbs and explicit artifact nouns rank above
#      domain keywords like "cassi"


def _route_utility(prompt: str) -> Optional[str]:
    """Match prompts that should ALWAYS run a deterministic command, even
    when an agent is selected (validate / judge / package / submit / status
    / overseer). Returns a dispatcher key or None."""
    p = prompt.lower()
    if "validate" in p or "missing" in p:
        return "validate"
    if "package" in p:
        return "package"
    if "submit" in p:
        return "submit"
    if "overseer" in p or "review" in p:
        return "overseer"
    if "status" in p:
        return "status"
    # "judge" / "cassi" → judge_cassi, but NOT when paired with a drafting
    # verb (e.g. "draft a CASSI principle" must NOT route to judge_cassi).
    DRAFT_VERBS = ("draft", "create", "make", "write", "compose", "generate", "build",
                   "revise", "edit", "improve", "fix", "rewrite", "update")
    has_draft_verb = any(v in p for v in DRAFT_VERBS)
    if not has_draft_verb:
        if "judge" in p or (("cassi" in p) and "principle" not in p and "spec" not in p
                            and "benchmark" not in p and "solution" not in p):
            return "judge_cassi"
    return None


def _route_drafting(prompt: str) -> Optional[str]:
    """Match prompts that ask for a contribution-template (no LLM). Returns
    a dispatcher key or None. Only consulted when --agent=none."""
    p = prompt.lower()
    if any(v in p for v in ("contribute principle", "create principle", "draft principle")):
        return "principle"
    if any(v in p for v in ("contribute spec", "create spec", "draft spec")):
        return "spec"
    if any(v in p for v in ("contribute benchmark", "create benchmark", "draft benchmark")):
        return "benchmark"
    if any(v in p for v in ("contribute solution", "create solution", "draft solution")):
        return "solution"
    DRAFT_VERBS = ("draft", "create", "make", "write", "compose", "generate", "build",
                   "revise", "edit", "improve", "fix", "rewrite", "update")
    if any(v in p for v in DRAFT_VERBS):
        if "principle" in p:
            return "principle"
        if "spec" in p:
            return "spec"
        if "benchmark" in p:
            return "benchmark"
        if "solution" in p:
            return "solution"
    if "principle" in p:
        return "principle"
    if "spec" in p:
        return "spec"
    if "benchmark" in p:
        return "benchmark"
    if "solution" in p:
        return "solution"
    return None


def _rule_route(prompt: str) -> Optional[str]:
    """Back-compat helper exposed for tests: applies utility AND drafting rules.

    NOT used directly by the prompt dispatcher anymore; the dispatcher
    splits the two paths explicitly based on --agent.
    """
    return _route_utility(prompt) or _route_drafting(prompt)


def _dispatch_rule(name: str) -> int:
    """Run a matched deterministic subcommand."""
    here = Path(".")
    if name == "principle":
        console.print("→ intent: [cyan]contribute principle[/cyan]")
        contribute_cmd.principle()
    elif name == "spec":
        console.print("→ intent: [cyan]contribute spec[/cyan]")
        contribute_cmd.spec()
    elif name == "benchmark":
        console.print("→ intent: [cyan]contribute benchmark[/cyan]")
        contribute_cmd.benchmark()
    elif name == "solution":
        console.print("→ intent: [cyan]contribute solution[/cyan]")
        contribute_cmd.solution()
    elif name == "package":
        console.print("→ intent: [cyan]package[/cyan]")
        package_cmd.package(workspace=here, output_dir=here, skip_validate=False)
    elif name == "submit":
        console.print("→ intent: [cyan]submit --dry-run[/cyan]")
        submit_cmd.submit(workspace=here, dry_run=True)
    elif name == "validate":
        console.print("→ intent: [cyan]validate[/cyan]")
        validate_cmd.validate(workspace=here)
    elif name == "overseer":
        console.print("→ intent: [cyan]overseer review[/cyan]")
        overseer_cmd.review(submission=".")
    elif name == "judge_cassi":
        console.print("→ intent: [cyan]judge cassi[/cyan]")
        judge_cmd.cassi(submission=".")
    elif name == "status":
        console.print("→ intent: [cyan]status[/cyan]")
        status_cmd.status(workspace=here)
    else:
        return 2
    return 0


def _route_prompt(prompt: str, agent_name: str,
                  read_only: bool = False, auto_yes: bool = False,
                  plan_mode: bool = False) -> int:
    """Two-tier routing:
       1. Utility commands (validate/judge/package/submit/status/overseer) always
          dispatch deterministically — an LLM adds nothing.
       2. Everything else: if --agent=none, try the template-based contribute
          rules; otherwise hand off to the selected agent.

    When --agent claude is selected, tool use (Edit/Write/Bash) is ON by
    default; every change triggers a confirmation prompt. Pass --read-only
    to disable tool use entirely (text-only response).
    """
    console.print(f"[purple]✨ AI4Science[/purple]: [italic]{prompt!r}[/italic]")

    # Tier 1: utility commands — always deterministic (no LLM cost regardless
    # of agent selection). Resolve this BEFORE probing agent availability so
    # `ai4science "validate my contribution"` never imports an agent SDK.
    util = _route_utility(prompt)
    if util is not None:
        return _dispatch_rule(util)

    # Resolve the 'auto' default to the best available real agent now that we
    # know this is an open-ended (non-utility) prompt.
    resolved = _resolve_agent(agent_name)
    if agent_name == "auto" and resolved != "none":
        console.print(f"[dim]→ auto-selected agent: {resolved!r} "
                      f"(set --agent or AI4SCIENCE_AGENT to override)[/dim]")
    agent_name = resolved

    # Tier 2: drafting / open-ended.
    if agent_name == "none":
        # No agent available (either explicitly --agent none, or auto-detect
        # found neither claude nor codex). Try the template-based contribute
        # rules; otherwise explain how to enable a real agent.
        draft = _route_drafting(prompt)
        if draft is not None:
            return _dispatch_rule(draft)
        console.print(
            "[yellow]No rule matched and no agent is available.[/yellow]\n"
            "Enable a real agent (works like Claude Code):\n"
            "  • Claude:  [cyan]pip install 'pwm-ai4science\\[claude]'[/cyan] then [cyan]claude login[/cyan]\n"
            "  • Codex:   install the [cyan]codex[/cyan] CLI then [cyan]codex login[/cyan]\n"
            "Then re-run, or pass [cyan]--agent claude[/cyan] / [cyan]--agent codex[/cyan] explicitly.\n"
            "Or use a deterministic command directly:\n"
            "  ai4science contribute principle | spec | benchmark | solution\n"
            "  ai4science validate / judge cassi / overseer review / package / submit"
        )
        return 2

    agent = get_agent(agent_name, read_only=read_only, auto_yes=auto_yes,
                       plan_mode=plan_mode)
    if not agent.is_available():
        reason = getattr(agent, "unavailable_reason", lambda: "")()
        console.print(f"[red]Agent {agent_name!r} not available:[/red] {reason}")
        return 2

    # Gather workspace context: any artifact .md files in cwd.
    workspace = Path(".").resolve()
    context_files = [p for p in (
        workspace / "principle.md",
        workspace / "spec.md",
        workspace / "benchmark.md",
        workspace / "solution.md",
    ) if p.exists()]

    # Any @-mentions in the prompt also become attached files (dedup'd).
    from ai4science.agents.mentions import parse_mentions
    mentioned = parse_mentions(prompt, workspace)
    extra = [p for p in mentioned if p not in context_files]
    context_files.extend(extra)
    if extra:
        rels = [str(p.relative_to(workspace)) for p in extra]
        console.print(f"[dim]📎 @attached: {', '.join(rels)}[/dim]")

    mode_label = "plan" if plan_mode else ("read-only" if read_only else "tool-use enabled")
    console.print(f"[dim]→ delegating to {agent_name!r} agent "
                  f"(workspace={workspace.name}, context files={len(context_files)}, "
                  f"mode={mode_label})[/dim]")
    if not read_only and agent_name == "claude":
        console.print(
            "[dim]   Edit/Write/Bash will prompt for confirmation. Use "
            "[cyan]--read-only[/cyan] to disable tool use, or [cyan]--yes[/cyan] to "
            "auto-approve all edits.[/dim]"
        )

    # When tool use is on, the agent prints progress to stderr (permission
    # prompts). Don't wrap in a status spinner; it would clobber the prompt.
    if read_only:
        with console.status(f"[purple]{agent_name} thinking…", spinner="dots"):
            result = agent.run_task(prompt, workspace, context_files)
    else:
        result = agent.run_task(prompt, workspace, context_files)

    if result.status == "ok":
        console.print()
        console.print(f"[bold]── {agent_name} response ──[/bold]")
        console.print(result.message)
        if getattr(result, "changed_files", None):
            console.print("\n[bold]Files the agent edited:[/bold]")
            for f in result.changed_files:
                console.print(f"  - {f}")
        if result.suggestions:
            console.print("\n[bold]Suggestions[/bold]")
            for s in result.suggestions:
                console.print(f"  - {s}")
        return 0
    elif result.status == "not_available":
        console.print(f"[yellow]{agent_name}: not available.[/yellow] {result.message}")
        return 2
    else:
        console.print(f"[red]{agent_name} error:[/red] {result.message}")
        return 1


def _pop_session_flags(argv: List[str]) -> tuple[List[str], bool, Optional[str], Optional[str]]:
    """Strip session/launch flags so bare `ai4science` supports them like `claude`.

    Returns (cleaned_argv, continue_session, resume_id, mode). Composes with
    _pop_agent_flag (kept separate so neither signature has to keep growing):
        --continue / -c   → resume the most recent conversation
        --resume <id>     → resume a specific session by id
        --mode <m>        → session mode: common | research
    Env: AI4SCIENCE_RESUME / AI4SCIENCE_MODE set defaults.
    """
    continue_session = False
    resume = os.environ.get("AI4SCIENCE_RESUME") or None
    mode = os.environ.get("AI4SCIENCE_MODE") or None
    cleaned: List[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--continue", "-c"):
            continue_session = True
            i += 1
            continue
        if a == "--resume" and i + 1 < len(argv):
            resume = argv[i + 1]
            i += 2
            continue
        if a.startswith("--resume="):
            resume = a.split("=", 1)[1]
            i += 1
            continue
        if a == "--mode" and i + 1 < len(argv):
            mode = argv[i + 1]
            i += 2
            continue
        if a.startswith("--mode="):
            mode = a.split("=", 1)[1]
            i += 1
            continue
        cleaned.append(a)
        i += 1
    return cleaned, continue_session, resume, mode


def _pop_agent_flag(argv: List[str]) -> tuple[List[str], str, bool, bool, bool, Optional[str]]:
    """Strip agent-related flags from argv.

    Returns (cleaned_argv, agent_name, read_only, auto_yes, plan_mode, model).

    Env defaults:
      AI4SCIENCE_AGENT      — agent name (default 'auto')
      AI4SCIENCE_READ_ONLY  — '1' to default to read-only mode
      AI4SCIENCE_AUTO_YES   — '1' to default to auto-approve edits
      AI4SCIENCE_PLAN       — '1' to default to plan mode
      AI4SCIENCE_MODEL      — default model for the session (e.g. opus/sonnet)
    """
    agent = os.environ.get("AI4SCIENCE_AGENT", "auto").lower()
    read_only = os.environ.get("AI4SCIENCE_READ_ONLY") == "1"
    auto_yes = os.environ.get("AI4SCIENCE_AUTO_YES") == "1"
    plan_mode = os.environ.get("AI4SCIENCE_PLAN") == "1"
    model = os.environ.get("AI4SCIENCE_MODEL") or None

    cleaned: List[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--agent", "-a") and i + 1 < len(argv):
            agent = argv[i + 1].lower()
            i += 2
            continue
        if a.startswith("--agent="):
            agent = a.split("=", 1)[1].lower()
            i += 1
            continue
        if a in ("--model", "-m") and i + 1 < len(argv):
            model = argv[i + 1]
            i += 2
            continue
        if a.startswith("--model="):
            model = a.split("=", 1)[1]
            i += 1
            continue
        if a in ("--read-only", "--readonly"):
            read_only = True
            i += 1
            continue
        if a in ("--yes", "-y"):
            auto_yes = True
            i += 1
            continue
        if a in ("--plan",):
            plan_mode = True
            i += 1
            continue
        cleaned.append(a)
        i += 1
    if agent not in ("none", "claude", "codex", "auto"):
        console.print(f"[yellow]Unknown --agent value {agent!r}; falling back to 'auto'.[/yellow]")
        agent = "auto"
    return cleaned, agent, read_only, auto_yes, plan_mode, model


def _resolve_agent(name: str) -> str:
    """Resolve the 'auto' sentinel to the best available real agent.

    Preference order: claude → codex → none. This makes a bare
    ``ai4science "draft a principle"`` behave like ``claude "…"`` — it uses a
    real agent when one is installed and authenticated, instead of falling
    back to the rule-based template router. Explicit ``--agent`` / the
    ``AI4SCIENCE_AGENT`` env var always win (they never resolve to 'auto').

    Only called on the prompt-first path, so subcommands like ``validate``
    don't pay the import cost of probing agent availability.
    """
    if name != "auto":
        return name
    for candidate in ("claude", "codex"):
        try:
            if get_agent(candidate).is_available():
                return candidate
        except Exception:
            continue
    return "none"


# Sub-subcommands that live under a group. Used to turn a mistyped
# `ai4science dispatch …` (group prefix omitted) into a "did you mean
# `ai4science compute dispatch …`" suggestion instead of routing it to the LLM.
_SUBCOMMAND_PARENTS = {
    "providers": "compute", "providers-add": "compute", "dispatch": "compute",
    "verify": "compute", "serve": "compute", "credits": "compute",
    "cassi": "judge", "review": "overseer",
    "principle": "contribute", "spec": "contribute",
    "benchmark": "contribute", "solution": "contribute",
}


def _suggest_subcommand(argv: List[str]) -> Optional[str]:
    """If argv[0] is a known group sub-subcommand, return the corrected
    `ai4science <group> <argv…>` invocation; otherwise None."""
    parent = _SUBCOMMAND_PARENTS.get(argv[0])
    if parent is None:
        return None
    return " ".join(["ai4science", parent, *argv])


def _agent_powered() -> bool:
    """Can the chat agent run? True if ANY LLM credential is available — a PWM
    login (founder-served models), a configured own-provider, an API key in env,
    or the `claude` CLI (subscription auth). None of these except the last needs
    Node, so this is what gates the Node-free native-harness default."""
    import os
    # 1. PWM account login → founder LLM proxy.
    try:
        from ai4science import pwm_account
        if (pwm_account.load() or {}).get("token"):
            return True
    except Exception:
        pass
    # 2. Own provider configured via `ai4science login --provider …` / --wallet.
    try:
        from ai4science import user as user_cfg
        cfg = user_cfg.load() or {}
        if cfg.get("power") in ("own", "wallet"):
            return True
    except Exception:
        pass
    # 3. Raw provider API keys in the environment.
    if any(os.environ.get(k) for k in
           ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")):
        return True
    # 4. The genuine Claude Code engine (claude login subscription auth).
    import shutil
    if shutil.which("claude"):
        return True
    return False


def _bare_launch(read_only: bool, auto_yes: bool, plan_mode: bool,
                 model: Optional[str] = None, continue_session: bool = False,
                 resume: Optional[str] = None, mode: Optional[str] = None) -> None:
    """Bare `ai4science` (no subcommand/prompt) → interactive chat, like `claude`.

    If the chat agent isn't installed/authed yet, show a short getting-started
    panel instead of a raw error, so a first run is welcoming.
    """
    # The default chat mode is research = the native Python harness, which
    # needs NO Node / `claude` CLI — only an LLM credential (a PWM login using
    # founder-served models, your own provider, or an API key). So we gate the
    # bare launch on "is any credential available?", NOT on the `claude` CLI.
    # (The genuine Claude Code engine is opt-in via `--mode claude`; when its CLI
    # is missing, chat() already falls back to the native harness.)
    if _agent_powered():
        import typer
        try:
            # NOTE: chat() is a Typer command; calling it directly means every
            # parameter we omit defaults to a Typer OptionInfo object (not the
            # option's default value). So we must pass EVERY parameter explicitly
            # — a missing one (e.g. resume) reaches the SDK as an OptionInfo and
            # crashes the connect with "expected str … not OptionInfo".
            chat_cmd.chat(
                agent="claude", workspace=Path("."),
                read_only=read_only, yes=auto_yes, plan=plan_mode,
                no_subagents=False, no_mcp=False,
                continue_session=continue_session,
                model=model, backend=None, resume=resume, mode=mode,
            )
        except typer.Exit as e:
            sys.exit(e.exit_code or 0)
        return

    # Not powered yet — welcome + the Node-free way to start, then options.
    console.print(f"\n[bold purple]AI4Science[/bold purple]  {__version__}\n")
    console.print("[bold]Start chatting — no Node, no API key required:[/bold]")
    console.print("  1. [cyan]ai4science login[/cyan]   "
                  "[dim]browser approval → founder-served models[/dim]")
    console.print("     [dim]or your own LLM:[/dim] "
                  "[cyan]ai4science login --provider anthropic|openai|gemini[/cyan]")
    console.print("  2. [cyan]ai4science[/cyan]         "
                  "[dim]drops you into a chat session (native engine)[/dim]\n")
    console.print("[dim]Optional — the exact Claude Code engine ([cyan]ai4science --mode claude[/cyan]):[/dim]")
    console.print("  [cyan]npm install -g @anthropic-ai/claude-code[/cyan] "
                  "[dim]then[/dim] [cyan]claude login[/cyan]  "
                  "[dim](without it, --mode claude uses the native engine)[/dim]\n")
    console.print("Works right now without a login (deterministic, offline):")
    console.print("  [cyan]ai4science init <name>[/cyan]   start a contribution workspace")
    console.print("  [cyan]ai4science validate[/cyan]      check artifacts")
    console.print("  [cyan]ai4science judge cassi[/cyan]   run the Physics Judge")
    console.print("  [cyan]ai4science --help[/cyan]        all commands\n")
    sys.exit(0)


def main() -> None:
    """Entry point: `ai4science` (bare → chat), `ai4science <subcommand>`, or
    `ai4science "prompt"`."""
    argv_raw = sys.argv[1:]
    # Friendly command aliases — a bare synonym should run the command, not get
    # routed to the LLM as a prompt. `ai4science upgrade` == `update` (the CLI
    # accepts both, like `claude update`); without this, `upgrade` fell through
    # to prompt-first mode and errored inside the agent.
    _ALIASES = {"upgrade": "update"}
    if argv_raw and argv_raw[0] in _ALIASES:
        argv_raw = [_ALIASES[argv_raw[0]]] + argv_raw[1:]
        sys.argv = [sys.argv[0]] + argv_raw
    # Subcommand path: flags after the subcommand belong to it
    # (e.g. `chat --mode research`). Skip session/agent-flag stripping and let
    # typer dispatch with the original argv intact, otherwise --mode/--resume/
    # --agent get consumed here before the subcommand can bind them.
    _subcommands = {
        "init", "contribute", "validate", "judge", "overseer", "package",
        "submit", "status", "version", "agents", "chat", "compute", "llm",
        "stake", "plugins", "tools", "login", "whoami", "logout", "prefer", "update",
    }
    if any(tok in _subcommands for tok in argv_raw):
        app()
        return

    raw, continue_session, resume, mode = _pop_session_flags(argv_raw)
    argv, agent_name, read_only, auto_yes, plan_mode, model = _pop_agent_flag(raw)

    # Bare invocation (only flags, no subcommand or prompt) → interactive chat,
    # exactly like typing `claude`. `--help`/`-h` still fall through to Typer.
    if not argv:
        _bare_launch(read_only, auto_yes, plan_mode, model,
                     continue_session=continue_session, resume=resume, mode=mode)
        return

    if not argv[0].startswith("-"):
        registered = {
            "init", "contribute", "validate", "judge", "overseer",
            "package", "submit", "status", "version", "agents", "chat",
            "compute", "llm", "stake", "plugins", "tools", "login", "whoami", "logout",
            "prefer", "update", "register-agent",
        }
        if argv[0] not in registered:
            # A mistyped subcommand (e.g. `ai4science dispatch --provider …`,
            # meaning `ai4science compute dispatch …`) must fail fast — not get
            # silently routed to the LLM as a prompt. Signal: an unregistered
            # first token followed by CLI-style flags is a command, not English.
            # Genuine prompts are quoted (one argv element) or plain words with
            # no standalone `--flags`.
            if any(tok.startswith("-") for tok in argv[1:]):
                console.print(f"[red]Unknown command:[/red] {argv[0]!r}")
                suggestion = _suggest_subcommand(argv)
                if suggestion:
                    console.print(f"Did you mean:  [cyan]{suggestion}[/cyan]")
                else:
                    console.print("Run [cyan]ai4science --help[/cyan] to list commands.")
                console.print("[dim]To send a free-form prompt to the agent, quote it:  "
                              f"[cyan]ai4science \"{' '.join(argv)}\"[/cyan][/dim]")
                sys.exit(2)
            # Prompt-first mode. Treat the whole argv as the user's prompt.
            prompt = " ".join(argv)
            sys.exit(_route_prompt(prompt, agent_name,
                                    read_only=read_only, auto_yes=auto_yes,
                                    plan_mode=plan_mode))

    # Subcommand mode (or --help): hand off to Typer with the cleaned argv.
    sys.argv = [sys.argv[0]] + argv
    app()


if __name__ == "__main__":
    main()
