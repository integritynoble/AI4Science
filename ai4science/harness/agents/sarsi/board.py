"""`BRD` — the board's third face: a page, served from this machine only.

`sarsi tasks` in the CLI and `/tasks` in a chat already render the same records.
This is the third, over the same source, so a task cannot look ready in one
place and blocked in another.

It is **local**, and that is the whole design. The board holds goals, criteria
and verdicts — `abraham`'s are somebody's personal life — and every other part
of this system refuses to let a local fact leave the machine: the vault, `W_host`,
the ledger that stores a digest instead of a body. A page is not an exception:

  * **it binds to loopback and refuses anything else.** `0.0.0.0` would put a
    personal board on the network, which is exactly the choice the owner made
    when they kept it local.
  * **it is read-only.** No form, no button, no route that changes anything —
    a page that could start work would be an unauthenticated door into the
    fleet, reachable by anything running on this host.
  * **no secret value.** A grant is named so the owner knows what is held; the
    value stays in the vault, as everywhere else.
  * **every row carries its reason**, because `waiting` without what it waits
    on is indistinguishable from idle.
  * **everything is escaped.** A goal is the owner's text, not markup — a board
    that renders it as HTML is a board that can be made to render anything.
"""
from __future__ import annotations

from html import escape
from typing import Optional, Tuple

from ai4science.harness.agents.sarsi import task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

#: The only hosts this will bind. Not a default — a refusal.
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
DEFAULT_PORT = 8140


class NotLocal(Exception):
    """A bind address that is not this machine alone."""


_STYLE = """
body{font:15px/1.5 ui-sans-serif,system-ui,sans-serif;margin:2rem auto;
max-width:52rem;padding:0 1rem;color:#111}
h1{font-size:1.3rem;margin:0 0 .2rem}
.sub{color:#666;font-size:.85rem;margin:0 0 1.5rem}
table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:.5rem .6rem;border-bottom:1px solid #e5e5e5;
vertical-align:top}
th{font-size:.75rem;text-transform:uppercase;letter-spacing:.04em;color:#666}
code{background:#f4f4f5;padding:.1rem .3rem;border-radius:3px;font-size:.85em}
.why{color:#666;font-size:.85rem}
.pass{color:#0a7}.fail{color:#c33}.unv{color:#a70}
a{color:#06c}
@media(prefers-color-scheme:dark){body{background:#111;color:#eee}
th,td{border-color:#333}th,.sub,.why{color:#999}code{background:#222}
a{color:#6af}}
"""


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{escape(title)}</title><style>{_STYLE}</style>{body}"
            f"<p class=sub>read-only · served from this machine only · "
            f"nothing here leaves it</p>")


def index(config: Config) -> str:
    """One line per worker. The manager holds no tasks, so it is not a board."""
    rows = []
    for agent in config.workers():
        held = tsk.all_of(config, agent)
        closed = len(tsk.all_of(config, agent, archived=True))
        rows.append(
            f"<tr><td><a href='/{escape(agent.id)}'>{escape(agent.id)}</a></td>"
            f"<td>{len(held)}</td><td class=why>{closed} archived</td></tr>")
    body = ("<h1>sarsi</h1><p class=sub>the same records the CLI and the chat "
            "show · <a href='/research'>research agents</a></p>"
            "<table><tr><th>agent<th>tasks<th></tr>"
            + "".join(rows) + "</table>")
    return _page("sarsi", body)


def research_index(config: Config) -> str:
    """The seven research agents: field, members, and the group ceiling.

    A research agent is a group; its ceiling is the lowest of its members' — so
    the ceiling column carries that reason, the way every row on this board
    carries its own."""
    from ai4science.harness.agents.research_agents import registry as ra

    rows = []
    for name, agent in ra.build_all().items():
        ceiling = agent.group.ceiling() or "—"
        rows.append(
            f"<tr><td><a href='/research/{escape(name)}'>{escape(name)}</a></td>"
            f"<td>{escape(agent.charter.field)}</td>"
            f"<td>{len(agent.group.members)}</td>"
            f"<td><code>{escape(ceiling)}</code> "
            f"<span class=why>the lowest any member's act needs</span></td></tr>")
    body = ("<h1>research agents</h1>"
            "<p class=sub><a href='/'>all agents</a> · a research agent is a "
            "group; its ceiling is the lowest of its members', not the "
            "agent's</p>"
            "<table><tr><th>agent<th>field<th>members<th>group ceiling</tr>"
            + "".join(rows) + "</table>")
    return _page("research agents", body)


def render_research(config: Config, agent) -> str:
    """One research agent in full — the same content as `research show`, escaped.

    Takes the built `ResearchAgent` so the same renderer can be handed any group:
    the charter, the group ceiling stated as the rule, and a members table where
    a judging member shows `—` because it never acts and so caps nothing.
    Everything here is agent-authored text and goes through `escape`."""
    from ai4science.harness.agents.research_agents import group as g
    from ai4science.harness.agents.sarsi.registry import EVERYDAY_CEILING

    ch = agent.charter
    grp = agent.group
    # declared → group → effective: the agent's own ceiling no longer decides.
    declared = EVERYDAY_CEILING
    gceil = grp.ceiling() or "—"
    effective = grp.capped(declared)

    member_rows = []
    for m in grp.members:
        cap = m.ceiling if m.ceiling is not None else "—"
        member_rows.append(
            f"<tr><td><code>{escape(m.name)}</code></td>"
            f"<td>{escape(m.kind.value)}</td>"
            f"<td>{escape(m.acts_on)}</td>"
            f"<td><code>{escape(cap)}</code></td>"
            f"<td class=why>{escape(m.refusal)}</td></tr>")

    parts = [
        f"<h1>{escape(ch.name)}</h1>",
        f"<p class=sub><a href='/research'>all research agents</a> · "
        f"{escape(ch.field)}</p>",
        f"<p>subfields: {escape(', '.join(ch.subfields))}</p>",
        # the rule, in words: declared A2 · group A1 · effective A1
        f"<p>ceiling: <code>declared {escape(declared)}</code> · "
        f"<code>group {escape(gceil)}</code> · "
        f"<code>effective {escape(effective)}</code> "
        f"<span class=why>the lowest any member's act needs</span></p>",
        "<table><tr><th>member<th>kind<th>acts on<th>ceiling<th>its refusal"
        "</tr>" + "".join(member_rows) + "</table>",
    ]
    if any(m.kind is g.Kind.JUDGING for m in grp.members):
        parts.append("<p class=why>a judging member shows — because it never "
                     "acts, so it does not cap the group.</p>")
    # Refusals and scope are different things and stay apart: a refusal travels
    # to any agent in the subfield, a scope note is about this agent's own role
    # and does not.
    if ch.refusals:
        parts.append("<h1>refuses</h1><p class=sub>these travel to any agent in "
                     "the subfield</p><ul>"
                     + "".join(f"<li>{escape(r)}</li>" for r in ch.refusals)
                     + "</ul>")
    if ch.scope:
        parts.append("<h1>not its job</h1><p class=sub>scope — does not travel"
                     "</p><ul>"
                     + "".join(f"<li>{escape(s)}</li>" for s in ch.scope)
                     + "</ul>")
    return _page(f"research · {ch.name}", "".join(parts))


def render(config: Config, agent: Agent) -> str:
    """One worker's board — the same rows `sarsi tasks` prints."""
    held = tsk.all_of(config, agent)
    closed = len(tsk.all_of(config, agent, archived=True))
    if not held:
        body = (f"<h1>{escape(agent.id)}</h1>"
                f"<p class=sub><a href='/'>all agents</a></p>"
                f"<p>no tasks."
                + (f" {closed} archived." if closed else "") + "</p>")
        return _page(f"sarsi · {agent.id}", body)

    rows = []
    for t in held:
        # the reason, always: `waiting` with nothing after it is idle
        waiting = ", ".join(t.awaiting) or (t.blocked_by or "")
        state = escape(t.state) + (f" <span class=why>— {escape(waiting)}</span>"
                                   if waiting else "")
        verdict = t.verdict or {}
        word = str(verdict.get("state") or "")
        if word:
            css = {"PASS": "pass", "FAIL": "fail"}.get(word.upper(), "unv")
            said = (f"<span class={css}>{escape(word)}</span> "
                    f"<span class=why>{escape(str(verdict.get('why') or ''))}</span>")
        else:
            said = "<span class=why>not judged yet</span>"
        rows.append(f"<tr><td><code>{escape(t.id)}</code></td>"
                    f"<td>{escape(t.goal)}</td><td>{state}</td>"
                    f"<td>{said}</td></tr>")

    body = (f"<h1>{escape(agent.id)}</h1>"
            f"<p class=sub><a href='/'>all agents</a> · {len(held)} task(s)"
            + (f" · {closed} archived" if closed else "") + "</p>"
            "<table><tr><th>task<th>goal<th>state<th>verdict</tr>"
            + "".join(rows) + "</table>")
    return _page(f"sarsi · {agent.id}", body)


def page(config: Config, path: str) -> Tuple[int, str]:
    """(status, html) for a request path. The whole routing table."""
    name = (path or "/").strip("/")
    if not name:
        return 200, index(config)
    # The `research` prefix is handled BEFORE the agent lookup, so `/research`
    # is never mistaken for an agent id.
    if name == "research":
        return 200, research_index(config)
    if name.startswith("research/"):
        from ai4science.harness.agents.research_agents import registry as ra
        rname = name[len("research/"):]
        try:
            agent = ra.build(rname)
        except KeyError:
            return 404, _page("not found",
                              "<h1>not found</h1>"
                              "<p><a href='/research'>all research agents</a></p>")
        return 200, render_research(config, agent)
    agent = config.agents.get(name)
    if agent is None or not agent.is_worker:
        return 404, _page("not found",
                          "<h1>not found</h1><p><a href='/'>all agents</a></p>")
    return 200, render(config, agent)


def serve(config: Config, *, host: str = "127.0.0.1", port: int = DEFAULT_PORT,
          make_server=None, serve_forever: bool = True):
    """Serve the board on loopback. Refuses to bind anything else.

    The refusal is the point: a board on `0.0.0.0` is a personal task list on
    the network, and nothing about a read-only page makes that acceptable.
    """
    if host not in LOCAL_HOSTS:
        raise NotLocal(
            f"{host!r} is not this machine alone. The board holds goals, "
            f"criteria and verdicts — putting it on the network is exactly "
            f"what keeping it local means not doing. Use 127.0.0.1.")

    if make_server is None:
        import http.server

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):                       # noqa: N802 (stdlib name)
                status, body = page(config, self.path.split("?", 1)[0])
                data = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):           # keep the terminal quiet
                pass

        make_server = lambda addr, handler: http.server.HTTPServer(addr, handler)
        server = make_server((host, port), Handler)
    else:
        server = make_server((host, port), None)

    if serve_forever and server is not None:
        server.serve_forever()
    return server
