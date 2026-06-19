"""ai4science feedback / report-bug — test agents, find bugs, earn PWM (Track 2).

Submit feedback or a bug report on an ai4science agent. A quality judge scores it
(actionable / specific / reproducible / novel) and credits PWM instantly for
useful signal — **finding real, reproducible bugs pays**. Junk / generic /
duplicate feedback earns nothing (and is not an error). Uses your
`ai4science login` token; no PWM balance is required to earn.
"""
from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

from ai4science import wallet

console = Console()


def _submit(agent: str, text: str) -> None:
    token = wallet.platform_token()
    if not token:
        console.print("[red]Not logged in.[/red] Run [bold]ai4science login[/bold] first "
                      "(or set PWM_TOKEN to your physicsworldmodel.org token).")
        raise typer.Exit(2)
    base = wallet.platform_base()
    path = f"/api/v1/agent-pool/{agent.strip()}/feedback"
    try:
        status, resp = wallet.http_post(base, path, token, {"text": text})
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Request failed:[/red] {e}")
        raise typer.Exit(1)
    if status >= 400:
        detail = resp.get("detail") if isinstance(resp, dict) else resp
        console.print(f"[red]✗ HTTP {status}[/red] {detail}")
        raise typer.Exit(1)

    st = (resp.get("status") or "").strip() if isinstance(resp, dict) else ""
    reward = resp.get("reward") if isinstance(resp, dict) else None
    quality = resp.get("quality") if isinstance(resp, dict) else None
    reason = (resp.get("reason") or "") if isinstance(resp, dict) else ""
    if reward:
        msg = f"[green]✓ accepted[/green] — earned [bold]{reward} PWM[/bold]"
        if quality is not None:
            msg += f"  (quality {quality})"
        if reason:
            msg += f" — {reason}"
        console.print(msg)
    else:
        # soft outcomes (low_quality, duplicate, rate_limited, judge_unavailable,
        # or judge disabled) earn nothing and are NOT errors.
        console.print(f"[yellow]submitted[/yellow] ({st or 'recorded'})"
                      f"{' — ' + reason if reason else ''}. No reward this time "
                      "(low quality / duplicate / rate-limited / bounty off).")


def feedback(
    agent: str = typer.Argument(..., help="Agent slug, e.g. 'research', 'computational-imaging'."),
    text: str = typer.Argument(..., help="Be SPECIFIC + ACTIONABLE — name a real problem or concrete change."),
) -> None:
    """Give feedback on an ai4science agent and earn PWM for useful, novel signal."""
    _submit(agent, text.strip()[:4000])


def report_bug(
    agent: str = typer.Argument(..., help="Agent slug the bug is in, e.g. 'computational-imaging'."),
    note: str = typer.Argument("", help="What went wrong: steps + expected vs actual."),
    log: str = typer.Option("", "--log", help="Path to an error/transcript file to attach (its tail)."),
    severity: str = typer.Option("", "--severity", "-s",
                                 help="Optional hint: critical | major | minor."),
) -> None:
    """Report a bug in an ai4science agent and earn PWM if it's a real, reproducible bug.

    Attach the error so the judge can verify it — either:
      ai4science report-bug research "crash on /clear" --log err.txt
    or pipe the failing output straight in:
      some-cmd 2>&1 | ai4science report-bug research "crash on /clear"
    """
    parts = []
    sev = severity.strip().lower()
    if sev:
        parts.append(f"severity: {sev}")
    if note.strip():
        parts.append(note.strip())
    repro = ""
    if log:
        try:
            repro = Path(log).read_text(errors="replace")[-3000:]
        except Exception as e:  # noqa: BLE001
            console.print(f"[yellow]could not read --log {log}: {e}[/yellow]")
    elif not sys.stdin.isatty():
        repro = sys.stdin.read()[-3000:]
    if repro.strip():
        parts.append("repro / error:\n" + repro.strip())
    if not parts:
        console.print("[red]Nothing to report.[/red] Give a note, --log <file>, or pipe the error "
                      "(e.g. `cmd 2>&1 | ai4science report-bug <agent> \"...\"`).")
        raise typer.Exit(2)
    _submit(agent, ("[BUG] " + "\n\n".join(parts))[:4000])
