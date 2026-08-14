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
            "show</p><table><tr><th>agent<th>tasks<th></tr>"
            + "".join(rows) + "</table>"
            "<p class=sub><a href='/groups'>groups</a> — the agents that are a "
            "group on the inside, and what each is made of · "
            "<a href='/federation'>federation</a> — which of these is the "
            "brain, and which is a motor</p>")
    return _page("sarsi", body)


def federation(config: Config) -> str:
    """`/federation` — brain vs executor, and what each actually did here.

    The plan of record puts this structure in `openclaw.json`, which is mode
    0600. This is the same fact where a person can read it. `federation.py`
    says which fields it will touch and which it refuses to.
    """
    from ai4science.harness.agents.sarsi import federation as fed

    ids = fed.load()
    if not ids:
        return _page("sarsi · federation",
                     "<h1>federation</h1><p class=sub><a href='/'>all agents</a>"
                     "</p><p>no federation config is readable from here.</p>")

    rows = []
    for i in ids:
        if i.role == "brain":
            what = "plans and verifies · holds the lesson index"
            drives = f"<code>{escape(i.model or 'default model')}</code>"
        else:
            what = "executes — the brain routes work to it"
            drives = (f"drives <code>{escape(i.drives or '?')}</code> via "
                      f"<code>{escape(i.backend or '?')}</code>"
                      + (f" ({escape(i.mode)})" if i.mode else ""))
        css = "pass" if i.ran_here else "unv"
        rows.append(
            f"<tr><td><code>{escape(i.id)}</code></td>"
            f"<td><strong>{escape(i.role)}</strong></td>"
            f"<td>{drives}</td>"
            f"<td class={css}>{escape(str(i.sessions))}</td>"
            f"<td class=why>{escape(i.what_it_did)}<br>{escape(what)}</td></tr>")

    warn = fed.model_pin_warning(ids, fed.default_model())
    note = f"<p class=unv>⚠ {escape(warn)}</p>" if warn else ""

    idle = [i.id for i in ids if i.role == "executor" and not i.ran_here]
    if idle:
        note += ("<p class=why>" + escape(", ".join(idle)) +
                 " left no session here. This page cannot tell an executor "
                 "that was never asked from one that could not run — both "
                 "look like an empty directory — so it says only what the "
                 "disk shows.</p>")

    body = ("<h1>federation</h1><p class=sub><a href='/'>all agents</a> · "
            "the brain plans and verifies; the executors run. Two identities, "
            "one machine — read from the agent config, not from a name</p>"
            "<table><tr><th>identity<th>role<th>runs on<th>sessions"
            "<th>what it did here</tr>" + "".join(rows) + "</table>"
            + note +
            "<p class=why>Role is derived from the declared runtime — an "
            "<code>acp</code> runtime means it drives a harness — never from "
            "the id, because a name is a label and the runtime is what "
            "decides. Only the agents subtree of the config is read; nothing "
            "else in that file reaches this page.</p>")
    return _page("sarsi · federation", body)


def groups(config: Config) -> str:
    """`/groups` — a research agent from the inside (design §11b, 1436-1570).

    Read-only, like everything else here: the ceiling this page computes is
    *printed*, never applied. `group.py` says why that boundary is where it is.
    """
    from ai4science.harness.agents.sarsi import group as grp

    got = grp.all_of(config)
    if not got:
        return _page("sarsi · groups",
                     "<h1>groups</h1><p class=sub><a href='/'>all agents</a>"
                     "</p><p>no agent here is modelled as a group.</p>")

    blocks = []
    for g in got:
        agent = config.agents.get(g.agent_id)
        rows = []
        for m in g.members:
            note = []
            if not m.built:
                note.append("not built")
            if m.irreversible:
                note.append("irreversible — no undo")
            if not m.may_verify_own_act:
                note.append("may not verify its own act")
            rows.append(
                f"<tr><td>{escape(m.name)}</td>"
                f"<td><code>{escape(m.kind)}</code></td>"
                f"<td>{escape(m.acts_on)}</td>"
                f"<td>{escape(m.ceiling)}</td>"
                f"<td class=why>{escape(m.refusal)}"
                + (f"<br>{escape(' · '.join(note))}" if note else "")
                + "</td></tr>")

        gap = g.gap_against(agent) if agent else None
        head = (f"<h2>{escape(g.agent_id)}</h2>"
                f"<p class=sub>one workspace · one task list · "
                f"{len(g.members)} members · "
                f"group ceiling <strong>{escape(g.ceiling)}</strong> — "
                f"the lowest of its members', per the design</p>")
        table = ("<table><tr><th>member<th>kind<th>acts on<th>ceiling"
                 "<th>its refusal</tr>" + "".join(rows) + "</table>")
        note = ""
        if gap:
            note = f"<p class=unv>⚠ {escape(gap)}</p>"
        if g.has_unbuilt:
            note += ("<p class=why>Nothing embodied is built. The design says "
                     "so of itself (§11b): the bench row is a design that "
                     "states what would have to be true first — irreversible "
                     "by default, no self-verification of an act, and the "
                     "group's ceiling set by its lowest member.</p>")
        blocks.append(head + table + note)

    body = ("<h1>groups</h1><p class=sub><a href='/'>all agents</a> · "
            "a research agent is one agent from outside and several members "
            "from inside</p>" + "".join(blocks) +
            "<p class=why>This page computes the group ceiling and prints it. "
            "It does not enforce it — making that rule bind would narrow what "
            "every research agent may do, which is the owner's decision.</p>")
    return _page("sarsi · groups", body)


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
    # `groups` is a reserved path. An agent with that id would be shadowed by
    # it — named here rather than left to be discovered, because a board that
    # silently hid one agent would break the one promise this page makes: that
    # it shows the same records the CLI does.
    if name == "groups":
        return 200, groups(config)
    if name == "federation":
        return 200, federation(config)
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
