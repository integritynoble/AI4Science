"""ai4science plugins — install community plug-ins from physicsworldmodel.org.

The website plug-in gallery (browser upload flow) publishes agent/tool manifests
at:
  GET {base}/api/v1/plugins                 → the gallery list
  GET {base}/api/v1/plugins/{name}/manifest → one manifest (JSON)

`pull` downloads manifests into the local plugins dir
(`AI4SCIENCE_PLUGINS_DIR`, default `~/.ai4science/plugins/`), validating each with
the same parser the harness uses, so a bad manifest is never written. They are
picked up at the next `registry.reload()` (i.e. the next agent start).

Subcommands:
  list                 show the gallery on physicsworldmodel.org
  pull <name>...       install named plug-ins (or --all for the whole gallery)
  installed            list plug-ins already in your local plugins dir
  test <manifest>      embed a plug-in into an agent (default research) and chat
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import typer
from rich.console import Console
from rich.table import Table

from ai4science.harness import transport
from ai4science.harness.agents import plugins as plugmod

app = typer.Typer(help="Install community plug-ins from physicsworldmodel.org.")
console = Console()

DEFAULT_BASE = "https://physicsworldmodel.org"


def _base(base: Optional[str]) -> str:
    return (base or os.environ.get("PWM_BASE") or DEFAULT_BASE).rstrip("/")


def _gallery(base: str) -> List[dict]:
    data = transport.get_json(f"{base}/api/v1/plugins")
    return data.get("plugins", []) if isinstance(data, dict) else []


def _fetch_manifest(base: str, name: str) -> dict:
    return transport.get_json(f"{base}/api/v1/plugins/{name}/manifest")


@app.command("list")
def list_cmd(
    base: Optional[str] = typer.Option(None, "--base", help="gallery base URL "
                                       f"(default {DEFAULT_BASE})"),
) -> None:
    """List the plug-in gallery published on physicsworldmodel.org."""
    b = _base(base)
    try:
        rows = _gallery(b)
    except Exception as exc:
        console.print(f"[red]Could not reach the gallery at {b}:[/red] {exc}")
        raise typer.Exit(1)
    if not rows:
        console.print(f"[yellow]No plug-ins published at {b} yet.[/yellow]")
        return
    table = Table(title=f"Plug-in gallery — {b}", show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Kind")
    table.add_column("Pool / target")
    table.add_column("Price", justify="right")
    table.add_column("Title")
    for p in rows:
        price = p.get("price_pwm") or 0
        table.add_row(p.get("name", "?"), p.get("kind", "?"),
                      p.get("target_agent") or "—",
                      f"{price:g}" if price else "free", p.get("title") or "")
    console.print(table)
    console.print("[dim]Install with:[/dim] ai4science plugins pull <name>  "
                  "[dim](or --all)[/dim]")


@app.command("installed")
def installed_cmd() -> None:
    """List plug-ins already installed in your local plugins dir."""
    d = plugmod.plugins_dir()
    agents, tools, errors = plugmod.load_plugins(d)
    console.print(f"[bold]Plugins dir:[/bold] {d}")
    if not agents and not tools and not errors:
        console.print("[yellow](empty — pull some with `ai4science plugins pull`)[/yellow]")
        return
    for a in agents:
        console.print(f"  [cyan]agent[/cyan]  {a.name}  [dim]{a.title}[/dim]")
    for t in tools:
        console.print(f"  [green]tool [/green]  {t.name}")
    for e in errors:
        console.print(f"  [red]bad[/red]   {e}")


def _write_manifest(directory: Path, name: str, manifest: dict, *, force: bool) -> str:
    """Validate then write one manifest. Returns a short status string."""
    # Validate with the SAME parser the harness loads with — never write garbage.
    try:
        plugmod.parse_manifest(manifest)
    except Exception as exc:
        return f"[red]invalid[/red] {name}: {exc}"
    dest = directory / f"{name}.json"
    if dest.exists() and not force:
        return f"[yellow]skip[/yellow]    {name} (already installed; --force to overwrite)"
    directory.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return f"[green]installed[/green] {name} → {dest}"


@app.command("pull")
def pull_cmd(
    names: List[str] = typer.Argument(None, help="plug-in name(s) to install"),
    all_: bool = typer.Option(False, "--all", help="install every plug-in in the gallery"),
    base: Optional[str] = typer.Option(None, "--base", help="gallery base URL "
                                       f"(default {DEFAULT_BASE})"),
    directory: Optional[str] = typer.Option(None, "--dir", help="target plugins dir "
                                            "(default AI4SCIENCE_PLUGINS_DIR)"),
    force: bool = typer.Option(False, "--force", help="overwrite already-installed plug-ins"),
) -> None:
    """Install plug-ins from the physicsworldmodel.org gallery into your plugins dir."""
    b = _base(base)
    d = Path(directory).expanduser() if directory else plugmod.plugins_dir()

    want = list(names or [])
    if all_:
        try:
            want = [p["name"] for p in _gallery(b) if p.get("name")]
        except Exception as exc:
            console.print(f"[red]Could not reach the gallery at {b}:[/red] {exc}")
            raise typer.Exit(1)
    if not want:
        console.print("[red]Name a plug-in to pull[/red] (or pass --all). "
                      "See `ai4science plugins list`.")
        raise typer.Exit(2)

    console.print(f"[dim]Pulling from {b} into {d}[/dim]")
    installed = 0
    for name in want:
        try:
            manifest = _fetch_manifest(b, name)
        except Exception as exc:
            console.print(f"[red]error[/red]   {name}: {exc}")
            continue
        status = _write_manifest(d, name, manifest, force=force)
        console.print("  " + status)
        if "installed" in status:
            installed += 1
    if installed:
        console.print(f"\n[green]Installed {installed} plug-in(s).[/green] "
                      "They load on the next agent start "
                      "([cyan]ai4science plugins installed[/cyan] to verify).")


# ── test: embed a plug-in into an agent and chat ────────────────────────────

class TestPrepError(Exception):
    """A blocking problem while preparing a `plugins test` session."""


def _resolve_manifest(arg: str) -> Tuple[dict, str, str]:
    """(manifest, kind, name) from a file path or an installed plug-in name.
    Validates with the harness parser (raises TestPrepError on anything bad)."""
    p = Path(arg).expanduser()
    if p.is_file():
        path = p
    else:
        cand = plugmod.plugins_dir() / (arg if arg.endswith((".json", ".toml")) else f"{arg}.json")
        if not cand.is_file():
            raise TestPrepError(f"no manifest found: {arg!r} is not a file, and "
                                f"{cand} does not exist")
        path = cand
    try:
        if path.suffix == ".toml":
            import tomllib
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TestPrepError(f"could not read manifest {path}: {exc}")
    if not isinstance(data, dict):
        raise TestPrepError("manifest must be a JSON/TOML object")
    try:
        plugmod.parse_manifest(data)            # validate (same rules the loader uses)
    except Exception as exc:
        raise TestPrepError(f"invalid manifest: {exc}")
    return data, data.get("kind", "agent"), data["name"]


def _embed_manifest(data: dict, kind: str, name: str, target: str, into_dir: Path) -> None:
    """Write the manifest into an isolated dir; for a tool, ensure it attaches to
    the target agent so it embeds there."""
    out = dict(data)
    if kind == "tool":
        out["attach_to"] = list(dict.fromkeys((out.get("attach_to") or []) + [target]))
    into_dir.mkdir(parents=True, exist_ok=True)
    (into_dir / f"{name}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


def _logged_in() -> Optional[str]:
    """Return the account email/label if logged in (token present), else None."""
    if os.environ.get("PWM_TOKEN"):
        return os.environ.get("PWM_EMAIL") or "PWM_TOKEN"
    try:
        from ai4science import pwm_account
        acct = pwm_account.load() or {}
        return (acct.get("email") or "your account") if acct.get("token") else None
    except Exception:
        return None


def _verify_embedded(name: str, kind: str, target: str) -> List[str]:
    """Reload the registry from the isolated dir and confirm the plug-in embedded
    into the target. Returns warnings (empty = clean)."""
    from ai4science.harness.agents import registry
    from ai4science.harness.agents.capabilities import CAPABILITY_BUNDLES
    registry.reload()
    warns = list(registry.PLUGIN_ERRORS)
    tspec = registry.get(target)
    if tspec is None:
        raise TestPrepError(f"target agent {target!r} is not a known agent")
    if kind == "tool":
        # A tool plug-in is a capability bundle, not an agent in the registry.
        if name not in CAPABILITY_BUNDLES:
            raise TestPrepError(f"tool plug-in {name!r} did not register "
                                + (f"({warns})" if warns else ""))
        if name not in tspec.capabilities:
            warns.append(f"tool {name!r} not attached to {target!r}")
    else:
        spec = registry.get(name)
        if spec is None:
            raise TestPrepError(f"agent plug-in {name!r} did not load "
                                + (f"({warns})" if warns else ""))
        if name not in registry.dispatchable_targets(tspec):
            warns.append(f"agent {name!r} is not dispatchable by {target!r} "
                         f"(target tier {tspec.tier!r} cannot reach a "
                         f"{spec.tier!r} plug-in) — try --into a science agent")
    return warns


def _launch_chat(*, into: str, workspace: str, model: Optional[str]) -> None:
    """Open the test chat session (separated for testability)."""
    from ai4science.commands import chat as chat_cmd
    chat_cmd.chat(mode=into, workspace=Path(workspace), model=model)


@app.command("test")
def test_cmd(
    manifest: str = typer.Argument(..., help="path to a manifest file, or an "
                                   "installed plug-in name"),
    into: str = typer.Option("research", "--into", help="agent to embed into "
                             "(default research; e.g. paper, computational-imaging)"),
    free: bool = typer.Option(False, "--free", help="skip login + PWM (offline dev; "
                              "testing normally spends PWM)"),
    workspace: str = typer.Option(".", "--workspace", "-w", help="workspace dir"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="model for the session"),
) -> None:
    """Embed a plug-in (agent or tool) into an agent and open a chat to test it.

    Loads ONLY the plug-in under test (isolated temp dir — non-destructive).
    Requires `ai4science login` and runs with the PWM gate ON, so testing spends
    PWM (use --free for offline dev)."""
    try:
        data, kind, name = _resolve_manifest(manifest)
    except TestPrepError as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)
    console.print(f"  [green]✓[/green] valid manifest [cyan]{name}[/cyan] ({kind})")

    target = into.strip()

    # Login + PWM (the testing loop spends PWM, like real usage).
    if not free:
        who = _logged_in()
        if not who:
            console.print("[red]✗ Not logged in.[/red] Testing spends PWM — run "
                          "[cyan]ai4science login[/cyan] first (or --free for offline dev).")
            raise typer.Exit(1)
        os.environ["AI4SCIENCE_PWM_GATE"] = "1"
        console.print(f"  [green]✓[/green] logged in as {who} — PWM gate ON (testing spends PWM)")
    else:
        console.print("  [yellow]●[/yellow] --free: no login, PWM gate OFF")

    # Isolated install: only this plug-in loads for the test session.
    tmp = Path(tempfile.mkdtemp(prefix="ai4science-plugtest-"))
    _embed_manifest(data, kind, name, target, tmp)
    os.environ["AI4SCIENCE_PLUGINS_DIR"] = str(tmp)

    try:
        warns = _verify_embedded(name, kind, target)
    except TestPrepError as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1)
    verb = "embedded into" if kind == "tool" else "dispatchable by"
    console.print(f"  [green]✓[/green] {verb} [cyan]{target}[/cyan] "
                  f"[dim](isolated: {tmp})[/dim]")
    for w in warns:
        console.print(f"  [yellow]⚠[/yellow] {w}")

    console.print(f"  [green]→[/green] opening [cyan]{target}[/cyan] chat… "
                  f"test your plug-in, then /exit")
    _launch_chat(into=target, workspace=workspace, model=model)
