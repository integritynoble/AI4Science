"""Social-media agent: governed timeline read -> deterministic draft -> owner-gated post.

``run_social_task`` mirrors the shape of ``run_imaging_task``
(``ai4science/harness/agents/imaging/agent.py``): it opens an A2 run on the
dual-mode runtime, then drives two governed sandbox executions —

1. **read** the Mastodon home timeline (``timeline_command``), confined by
   ``scope`` and ``net_allowlist=[mastodon_host]`` so the sandboxed process
   can reach nothing but the declared host, via the egress proxy that injects
   the auth token itself (the generated command never carries a token);
2. **draft** a deterministic summary of that timeline (``draft_post``, no
   network, no randomness);

and then consults the owner gate before ever touching the network again.
Posting a status is an external write, so it is always approval-required:
``client.classify(...)`` is called to mirror the runtime's mode-gateway
pattern (the same call ``run_task`` makes for boundary decisions in
``ai4science/harness/runtime/pev.py``), but the actual go/no-go is the
``approve(draft) -> bool`` callback supplied by the caller. No ``approve``,
or ``approve`` returning falsy, means the run stops at the draft — the post
sandbox_execute is never invoked. Only when ``approve(draft)`` is truthy
(and the gateway hasn't hard-denied) does the **post** step run
(``post_command``), and only the parsed ``id`` field of the response is
returned — raw sandbox stdout is never echoed back beyond the fields this
function explicitly parses.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional


def _parse_stdout(res: dict) -> Any:
    """Defensively parse a sandbox_execute result's stdout as JSON.

    Returns ``None`` on any sign of failure (``is_error``, non-JSON, missing
    stdout) instead of raising, so a hostile or broken sandbox response can
    never crash the agent.
    """
    if not isinstance(res, dict) or res.get("is_error"):
        return None
    stdout = res.get("stdout")
    if not isinstance(stdout, str) or not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except (TypeError, ValueError):
        return None


def run_social_task(*, client, store, task_id, mastodon_host: str,
                     scope: str = "mastodon", interaction_mode: str = "I2",
                     approve: Optional[Callable[[str], bool]] = None,
                     seed=None, agent_id: str | None = None) -> dict:
    """Read a Mastodon home timeline, draft a summary, and post it only if approved.

    Args:
        client: dual-mode runtime client (``open_run``, ``sandbox_execute``,
            ``classify``).
        store: task store; accepted for interface symmetry with
            ``run_imaging_task`` (not used — this flow has no repair/replan
            loop to checkpoint).
        task_id: caller-supplied task identifier; accepted for the same
            reason as ``store``.
        mastodon_host: the Mastodon instance host the sandbox is allowed to
            reach (used for both the timeline read and the post, and as the
            sole entry of ``net_allowlist``).
        scope: sandbox network scope passed to every ``sandbox_execute``
            call.
        interaction_mode: interaction profile for the opened run (e.g.
            ``"I2"``).
        approve: owner gate. ``approve(draft) -> bool``. ``None``, or a
            falsy return, means "not approved" — the post is never sent.
        seed: accepted for interface symmetry; the draft is deterministic
            and does not depend on it.

    Returns:
        ``{"status": "drafted", "draft": ..., "timeline_count": ...}`` if
        not approved; ``{"status": "posted", "draft": ..., "id": ...}`` if
        approved and the post succeeded; ``{"status": "error", ...}`` if the
        timeline or post response could not be parsed.
    """
    from .mastodon_tools import timeline_command, post_command
    from .draft import draft_post

    run = client.open_run("social: read+draft", "A2", {"actions": 4},
                          interaction_profile=interaction_mode, agent_id=agent_id)
    run_id = run["run_id"]

    # 1. Read — governed sandbox execution, confined to the declared host.
    read_res = client.sandbox_execute(run_id, timeline_command(mastodon_host),
                                      scope=scope, net_allowlist=[mastodon_host])
    timeline = _parse_stdout(read_res)
    if not isinstance(timeline, list):
        return {"status": "error", "task_id": task_id, "why": "could not parse timeline"}

    # 2. Draft — local, deterministic, no network.
    draft = draft_post(timeline)

    # 3. Owner gate — posting is an external write, so it is always
    #    approval-required. Consult the mode gateway (mirrors run_task's
    #    boundary-decision pattern in pev.py) as well as the owner callback;
    #    either one refusing means the run stops at the draft. No
    #    action_type is passed here: action_type only participates in the
    #    gateway's capability-CEILING override (real ceiling action types
    #    like "network_egress"/"sandbox_exec" -- see policy.CEILINGS),
    #    which "external_post" is not a member of for any profile; passing
    #    it would make every call DENY regardless of interaction mode. The
    #    boundary_kind "irreversible_or_external" alone already guarantees
    #    ASK (never ACT) for every profile, which is what this gate needs.
    decision = client.classify(run_id, "irreversible_or_external",
                               step_summary="post status to mastodon").get("decision")
    approved = bool(approve and approve(draft))
    if decision == "DENY" or not approved:
        return {"status": "drafted", "draft": draft, "timeline_count": len(timeline)}

    # 4. Post — only reached once the owner has approved.
    post_res = client.sandbox_execute(run_id, post_command(mastodon_host, draft),
                                      scope=scope, net_allowlist=[mastodon_host])
    posted = _parse_stdout(post_res)
    if not isinstance(posted, dict) or "id" not in posted:
        return {"status": "error", "task_id": task_id, "why": "could not parse post response"}

    return {"status": "posted", "draft": draft, "id": posted["id"]}
