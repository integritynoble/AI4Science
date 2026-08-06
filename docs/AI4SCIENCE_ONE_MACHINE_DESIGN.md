# ai4science on one machine — design

**Status: design, 2026-08-04.** The agent loop is built, tested, and exercised
live on a second user account: tasks, plans, per-phase verdicts, the supervision
loop, the vault, the outward gates, and the reporting around them —
`attention`, `why`, `spend`, `decisions`, `blast`, `questions`, `board`. **§11 and §13 are built** except
where noted below; **§11's local half is built** — the package format, and installing one here with its acceptance
questions asked by the machine doing the installing. **Uploading, the
governor's acceptance and the PWM earning are not**, and neither is §13: those
need a server, which is the app's half. See *What is built, and what is not* in
§11.

Where a row below says **built**, it means built in
`AI4Science/ai4science/harness/agents/sarsi/`, which is the canonical
implementation. `singularity/sarsi/` is a second, superseded build of the same
spec and is not evidence for anything here.

> **This file is the design of record**, and it sits beside the code it
> describes. `singularity/docs/specs/2026-08-04-ai4science-one-machine-design.md`
> is a mirror kept because the sibling specs there reference it; where the two
> differ, this one is right.
>
> Both were edited independently for a day, by two sessions that each wrote
> real findings into a different copy — neither was a superset. They are
> merged here: the backend contract's `delivers_plan_at_start` and the `CAP`
> tool-presence note came from the mirror, the attended-session paragraphs
> from this one. Two copies of one document is how a defect report gets lost
> by being written down.

This page is about **ai4science alone**, on **one machine**. No manager, no
server, no app. Everything here works with nothing else installed, which is the
property the whole arrangement rests on: singularity requires ai4science, and
ai4science requires nothing.

Earlier specs mixed the two because the app was being designed at the same time.
This one does not mention singularity again except in §14, where the difference
in what a run costs is the only place it matters.

| Question | Document |
|---|---|
| What does one **session** do, node by node? | [`guide-sarsi-claude-overview.md`](../guide-sarsi-claude-overview.md) |
| What does the **app** add on top of this? | [`2026-08-04-sarsi-agent-market-and-pwm-design.md`](2026-08-04-sarsi-agent-market-and-pwm-design.md) |

### Where each of the fourteen points is answered

The requirement came as numbered points. The sections that answer one
say so in their own titles, so a point can be found by scrolling:

```
1. What ai4science is                           (Point 10)
4. The entry: the machine agent                 (Point 7)
9. How the workspaces talk to each other        (Points 9 and 14)
10. Both doors                                  (Point 8)
11. The market                                  (Points 1 and 2)
11a. The tools and sub-agents this system needs (Point 13)
11b. Research agents                            (Point 11)
     What a research agent is FOR                (Point 23)
     The two functions, and who verifies what    (Point 24)
     What one research agent is made of          (Point 25)
     Self-awareness, in a research agent         (Point 26)
     A research agent is a GROUP, and some of it has a body
     RSI, and how a field ends                   (Point 27)
     The governor's research agents             (Points 6 and 12)
13. What runs it costs                          (Points 2, 3 and 4)
     Your own key, run freely, and earn         (Point 5)
```

**Points 2 and 7 are answered here in their ai4science form only.** The app's
half of each — the 5% platform share, and the chatbot front door with its `+` —
is in [the market design](2026-08-04-sarsi-agent-market-and-pwm-design.md),
because this page is point 10 and does not describe the app. What is here is the
half a single machine has: no platform share is charged, and the front door is
the machine agent.

---

## 1. What ai4science is (Point 10)

A set of agents that live on your machine, hold tasks, plan them, and get them
done through governed `sarsi-claude` sessions — with a verifier that judges the
plan's own criteria and gates that stop anything reaching the world without you.

**What it does not have:** a manager, a server, a fleet, another machine. Those
belong to the app, and their absence is what makes this a complete product
rather than a client.

## 2. The invariant

> **The agent you talk to does not execute. Only a worker touches
> `sarsi-claude`.**

On one machine there is no network boundary to enforce this, so it is enforced
as a code path: the machine agent plans, routes and answers, and `assign` raises
if it tries to drive a session. Everything below assumes it.

Three rules carry the same weight:

> **Drafting is not sending.** An agent may compose anything. Every act that
> leaves the machine and reaches a person needs a grant naming *that act*.

> **The model is an engine, not an authority.** No permission, ceiling, verdict
> or grant derives from which model is running.

> **Share intent, not instruments.** A goal, a plan and a decision mean the same
> thing anywhere. A tool inventory, a path and a resource reading are about a
> host and stay on it.

## 3. Topology

```
  TWO SURFACES, ONE AGENT
  ┌──────────────────────────┐   ┌──────────────────────────────┐
  │ Telegram — one bot each  │   │ the ai4science CLI           │
  │ owner-locked             │   │ /agent <id> · ask non-interactively │
  └───────────┬──────────────┘   └───────────────┬──────────────┘
       │  bindings: {channel, accountId} → agentId              │
       ▼                                                        ▼
  the gateway            one local daemon; hosts every agent's loop
    │
    ├── machine agent    THE ENTRY CHAT · knows this machine · MAY NOT drive a session
    ├── sarsi-worker     the base worker — any task with no better home
    ├── work             RETIRED 2026-08-05 · out of routing, its history still readable
    ├── social           one daily read · drafts for the three destinations
    ├── funding          applications · an eligibility claim must cite a source
    ├── jobs             CV · application sites
    ├── abraham          personal · loosest scope, tightest authority
    └── …                anything installed from the market
          each: own workspace · tasks · sessions · playbook · self-model
          each holds SEVERAL TASKS ↓
                task ── plan0.md      phases · Verified when · Permissions needed
                  ▼
                sarsi-claude          ONE PER TASK · handed the PLAN, not the wish
                  ↓ guides
                Claude Code
    │
    └── vault            local · standing policy → per-use prompt · ALLOW / DENY
```

**One daemon, every agent's loop, both doors.** A rule cannot exist on one
surface and not the other, which is the only way *"two doors, one agent"*
survives a third door being added later.

## 4. The entry: the machine agent (Point 7)

Entering ai4science puts you in conversation with the **machine agent**. It is
the right thing to land in because the first questions anyone has are about
*this machine*: what can it do, what is running, which worker should take this.

| It does | It may not |
|---|---|
| answer about this machine — tools, sessions, workers, what is waiting | drive a session |
| route a request to the worker that should hold it | hold a secret |
| say plainly when nothing here can do a thing | queue an unplaceable request silently |

**It is replaceable from the market**, and it is the strictest listing there:
the thing that reads every message you type before anything else does, and
decides which worker hears it. There is always exactly one installed — swapping
is not removing. A market machine agent may declare **no outward classes** and
bring **no session-starting sub-agent**; what bounds a bad one is the invariant.

## 5. The agents

| Agent | For | Tools | May complete |
|---|---|---|---|
| **machine agent** | this machine: routing, inventory, the fleet-of-one view | none — it does not execute | nothing |
| **`sarsi-worker`** | the one general worker — any task with no better home | shell, editor, browser | nothing — its work stays here |
| **`work`** | **retired 2026-08-05.** Out of routing, still readable | — | — |
| **`social`** | one daily read, and influence | browser | `post` |
| **`funding`** | applications | browser, documents | `submission` |
| **`jobs`** | CV, application sites | browser, documents | `submission` |
| **`abraham`** | the owner's own life, not their job | browser, calendar, documents, payment | `recurring`; **no standing grants** |

`outward` is a **whitelist**: a class absent from a row is refused, so a class
nobody has claimed is refused everywhere until someone claims it.

**Four classes no agent completes at any ceiling** — `money`, `consent`,
`publishing`, `legal`. `abraham` prepares all four and completes none, and
**abstains rather than asks**: putting one in front of the owner would imply a
yes existed, and turn *"this cannot be authorised"* into *"you didn't approve
it"*.

**Tools are a profile, not an inventory.** A request needing a tool outside an
agent's row is refused before the machine is asked whether it has it: `work` has
no payment tool, so it is not asked to pay on a machine that could.

### `work` — retired, and why it was not deleted

The roster shipped two general workers on the same engine with the same
authority: `sarsi-worker` (shell, editor, browser) and `work` (qupath, matlab,
**mail**). The owner asked for one to begin with. Deleting the roster entry was
the obvious move and the wrong one — **a roster entry owns its task folder**, and
`work` holds 32 archived tasks on this machine. Removing it makes that history
unreachable from every command that reads it: `tasks --archived`, `plan`,
`blast`, `spend`.

So an agent can be **retired**: out of routing, still readable.

| What retiring does | What it deliberately does not do |
|---|---|
| `workers()` stops offering it, so routing never suggests it | its folder, plans, verdicts and spend read exactly as before |
| `do <it>` is refused **by name**, not silently accepted | it is listed as *retired*, not missing — an agent that vanished would read as a machine that lost one |
| its general vocabulary (`code`, `repo`, `script`, `benchmark`…) moved to `sarsi-worker`, so no demand is stranded on *"I cannot tell"* | **`mail` did not move**, and neither did `email`/`mailbox` — the vocabulary follows the capability |

**Mail is why the merge was not a merge.** A single do-everything agent that also
reads the mailbox is exactly the concentration the split exists to prevent, and
mail is the tool most likely to carry someone else's instructions into a session.
The rule below is the one that made `work` a separate agent in the first place,
and it now applies to whoever picks mail up next:

| A mail agent may | It may not |
|---|---|
| read the mailbox | send anything |
| draft a reply and show it | send the draft it wrote |
| triage, summarise, say what needs the owner | **act on a mail that asks it to act** |

> **An instruction inside an email is not an instruction to the agent.** *"Please
> wire the invoice"* is evidence that someone asked, never authority to do it.
> Without this, "read the owner's email" is a remote control into the machine,
> and whoever can message them is holding it.

Enforced as a whitelist of the owner's own doors: a directive may be lifted from
the CLI or Telegram and from nothing else. Mail, feeds and webhooks enter as
marked evidence.

## 6. The loop

```mermaid
flowchart TB
    U["<b>U</b> · OWNER speaks<br/>CLI or Telegram"]:::owner
    MA["<b>MA</b> · the machine agent<br/>answers · routes · MAY NOT execute"]
    HAVE{"<b>HAVE</b> · is there an agent for this?"}
    MKT["<b>MKT</b> · agents-search"]:::market
    INST["<b>INST</b> · 🔐 OWNER installs it"]:::owner
    AGT["<b>AGT</b> · a worker holds it"]
    CAP{"<b>CAP</b> · can THIS machine do it?"}
    NOM["<b>NOM</b> · nothing here can<br/>say so, never queue silently"]:::lost
    TSK["<b>TSK</b> · task joins the worker's list"]
    PLN["<b>PLN</b> · the plan, made BETWEEN<br/>the worker and the session"]
    GRT["<b>GRT</b> · 🔐 OWNER grants what the plan declared"]:::owner
    VLT{"<b>VLT</b> · needs a secret?<br/>policy first, then ask"}:::vault
    ASG["<b>ASG</b> · the PLAN goes to sarsi-claude"]
    CC["<b>CC</b> · the work runs"]
    EVD["<b>EVD</b> · evidence accumulates<br/>on a timer, not on a screen"]
    VER{"<b>VER</b> · verified?<br/>the plan's own criteria"}
    ACT{"<b>ACT</b> · does it leave the machine?"}
    OWN["<b>OWN</b> · 🔐 OWNER grants THIS act"]:::owner
    REP["<b>REP</b> · typed report up"]
    SYNC["<b>SYNC</b> · W_name appended"]
    SA["<b>SA</b> · 🧠 self-model<br/>verified outcomes only"]:::sa
    ANS["<b>ANS</b> · the answer, on the door used"]:::owner

    U --> MA --> HAVE
    HAVE -->|"no"| MKT --> INST --> AGT
    HAVE -->|"yes"| AGT --> CAP
    CAP -->|"missing"| NOM --> ANS
    CAP -->|"present"| TSK --> PLN --> GRT --> VLT
    VLT -->|"DENY — name the secret"| REP
    VLT -->|"ALLOW · the secret never leaves"| ASG --> CC --> EVD --> VER
    VER -->|"FAIL"| CC
    VER -->|"PASS"| ACT
    ACT -->|"stays local"| REP
    ACT -->|"leaves"| OWN --> REP
    REP --> SYNC --> SA --> ANS

    classDef owner fill:#e8f0fe,stroke:#4c6ef5,color:#1a1a1a
    classDef lost fill:#fff3bf,stroke:#f08c00,color:#1a1a1a
    classDef market fill:#e6fcf5,stroke:#0ca678,color:#1a1a1a
    classDef vault fill:#ffe3e3,stroke:#c92a2a,color:#1a1a1a,stroke-width:2px
    classDef sa fill:#f3e8ff,stroke:#7c3aed,color:#1a1a1a,stroke-width:2px
```

**Blue is the owner, and there are four gates**: install, grant, vault, outward.
**`ASG` is the seam** — below it, the 27-node session loop runs unchanged.

**Three exits reach the owner and they are different things.** `GRT` is a plan
review: here is what this will need, before any of it runs. `OWN` is one act
asking to leave. `NOM` is a capability failure: nothing here can do this, and
here is what is missing.

## 7. Every node worth restating

### MA · the machine agent
**Fires:** anything typed, on either door. **Does:** answers about this machine,
or names the worker that should hold the request. **May not:** drive a session,
hold a secret, or claim a specialist's competence when routing — its expertise
is who is responsible for what, not how to do it.

### CAP · can this machine do it?
**Fires:** a request reaching a worker. **Reads:** the declared tool inventory
and the agent's own profile. **May not:** infer a tool from the text; a guess
refuses the wrong things confidently.

### PLN · the plan, made between the worker and the session
Not one drafting step. **The worker seeds it** from the owner's words and its
own history, into `plan0.draft.md`; **the session grounds it** against the actual
code; **the worker checks it back** against the rules the verifier depends on and
sends back exactly what is missing; **it is promoted** to `plan0.md` when it
passes, and not otherwise.

> **Why not either alone.** A plan drafted by one model in one shot has never
> seen the repository it describes. A plan the session writes alone is the
> session authoring the criteria it will be judged by.

The exchange goes through a **file, not a screen**, and an unchanged draft is not
agreement: if the session never touches it, the worker cannot tell "it agreed"
from "it died", so the round fails and the owner is asked.

### GRT · the owner grants what the plan declared
**Fires:** the plan's `Permissions Needed` section is non-empty. **May not:** be
inferred from the task having been asked for. A permission line the parser
cannot read declares **nothing** — so the task would walk past this gate to
`ready` while the plan the owner read still shows a permissions section. That
failure is silent and it fails open, so the writer and the reader are held to one
grammar: ``- `action` on `scope` - why``.

### VLT · the vault
Two stages: a standing policy the owner set in advance, or the owner asked now.
**A policy must name its counterparty** — `smtp` for `funding` is a blank cheque
— and **five per-use approvals never become a policy**, because a gate that
widens itself by being used is not a gate. An agent asks the vault to **use** a
credential and never receives one; there is no `read()`. Stored in the OS
keyring or under a passphrase-derived key, and **never in plaintext unless the
owner asked for that by name**.

### EVD · evidence
Captured on a timer and **accumulated**, not read off a screen when someone asks.
A verdict that depends on when it was asked is not a verdict: the same finished
work read PASS at one moment and FAIL an hour later, when the run had scrolled
away. The log only grows; the terminal is consulted for liveness only.

### VER · verified?
An independent judge, given the plan's criteria and the evidence. **Five
refusals**, each returning `UNVERIFIED` — which is neither pass nor fail:
no criteria, no evidence, a stale plan, no judge, and **an answer that gives both
verdicts**, which is not a judgement at all.

### OWN · the outward gate
The owner sees exactly what would go out. **The approved bytes are the
transmitted bytes** — anything edited after approval refuses. A timeout denies,
because silence is not consent. A refusal is an outcome and is recorded.

### SA · the self-model
Every line is an observation made when the question is asked. **Unmeasured is
`None`, never zero.** The limits line is always present. Nothing here writes a
ceiling, a grant or a playbook: reading cannot become authority.

## 8. Tasks and plans

A worker holds **several** tasks, concurrently, not a queue of one. Each owns a
`plan0.md` whose phases carry `Verified when:` lines — the sentences the verifier
will judge — and a `## Permissions Needed` section naming everything the work
needs beyond its own workspace.

| State | Means |
|---|---|
| `drafting` | no usable plan yet |
| `awaiting-grant` | the plan declares permissions the owner has not given |
| `ready` | plannable and permitted; not started |
| `waiting` | over the concurrency limit, **and it says so** |
| `running` · `done` · `failed` | as they read |

> **A task over the limit says so.** A task that is simply not started looks
> identical to a task nothing is working on, and the owner cannot tell which.

**An owner edit is authoritative and is never overwritten.** A polish round may
propose a successor beside it; the owner accepts or discards. And editing a
`Verified when:` line changes the standard the verifier applies — that is the
point, not a side effect.

### Asking for a task, and finding it again

Two things the owner does constantly, and they are different acts:

| | |
|---|---|
| **ask** | say what you want in a sentence; a task is created and planned |
| **recall** | ask what tasks exist; get them back **with a link each** |

**Recall is a read.** Listing tasks starts nothing, spends nothing and changes
nothing — it answers *what is going on*, which is a question the owner should
never have to pay for or think twice about asking.

**Every task has a stable address.** Not "the second one in the list": a name
that survives the listing being reprinted, that can be kept, pasted and come
back to tomorrow. Handles that are positions are wrong the moment anything
finishes, and a handle that means a different task than it did an hour ago is
worse than no handle.

**Following the link enters the task**, and entering a task means being in its
`sarsi-claude` session's context — its plan, its phases, its verdicts, its
evidence, and the modes that act on it.

> **A link identifies; it does not authorise.** Entering a task still requires
> being the owner. This matters more in the app, where a link is a URL and URLs
> travel — but it is a property of the address itself and not of the transport,
> so it holds here too: an address that granted access would make every list of
> tasks a list of keys.

**The machine agent can recall** — it is the front door, and *"what am I working
on"* is a question about this machine. So can any worker, about its own tasks.
Neither of them starts anything by answering.

### One worker, several tasks

A worker holds **several tasks at once**, concurrently, not a queue of one. Each
has its own plan, its own session, its own evidence and its own verdict, and
they do not share a context.

| | |
|---|---|
| **why concurrent** | a task waits on a model, a test run, a gate. A worker that could hold one would spend most of its life blocked |
| **the limit** | set per agent in its playbook, and a task over it is `waiting` **and says so** |
| **what is shared between them** | the worker's `W_name` and its history. Nothing else — two tasks are two sessions, two plans, two records |

> **A task over the limit says so, and that is the whole point of the state.** A
> task that is simply not started looks identical to a task nothing is working
> on, and the owner cannot tell which — so `waiting` carries the reason and the
> limit that caused it.

## 9. How the workspaces talk to each other (Points 9 and 14)

Every agent has its own workspace and its own history. They still need to share:
`funding` should know the deadline `work` found in a mail, and `jobs` should know
which CV `abraham` filed. The question is how, without dissolving the reason
there are seven of them.

### There is no channel between two agents

The first thing to say about how the workspaces talk is that they do not *talk*.
There is no message from `work` to `funding`, no inbox one agent can write into,
no socket between them. Communication happens **through a place**, and the place
is a file.

> **Why a place and not a pipe.** A pipe is a capability: once `work` can send to
> `funding`, it can send anything, at any moment, and `funding` processes it
> because it arrived. That is the shape of every prompt-injection route in this
> design — an untrusted mail becomes a message becomes an instruction. A place is
> read by an agent that decided to read it, at a moment it chose, while planning.
> Nothing arrives. Nothing interrupts. Nothing is processed because it was sent.

### The four tiers

| Tier | Who sees it | Holds | Written by |
|---|---|---|---|
| **`W_user`** | every agent | who the owner is, standing preferences, the do-not list | the owner |
| **`W_shared`** | every agent that was granted it | published facts — decisions, deadlines, entities, outcomes | any agent, deliberately |
| **`W_name`** | **one agent** | its mission, its plans, its conversation, what it decided and why | itself |
| **`W_host`** | **one agent, one machine** | tools present, paths, sessions, resources | itself |

### Four tiers are four paths

Isolation is a path question, not a discipline question — `layout.py` creates
these and nothing merges them:

```
~/.sarsi/
  workspace/                    W_user     every agent reads it, the owner writes it
  shared/facts.jsonl            W_shared   published facts — granted, append-only
  ledger/*.jsonl                           directives · reports · outward · vault
  agents/<id>/
    workspace/                  W_name     THIS agent only. history.md and its notes
    host/                       W_host     this agent, this machine. never leaves
    tasks/  sessions/  selfmodel/
                                W_secret   the vault, its own owner-installed root
```

`W_secret` is not in this tree on purpose. The vault answers ALLOW or DENY and
hands nothing over, so there is no tier for it to be shared *from*.

### The one rule: publish, never browse

```
work ──publish──▶  W_shared  ◀──read──  funding        ✅
work ─────────────▶ W_name(funding)                    ❌  never
```

An agent **publishes** a fact and **reads** the common space. No agent ever
reads another's `W_name`.

> **Why the asymmetry is the whole design.** Publishing is an act its author
> chose, at a moment they chose, about a thing they decided was worth saying —
> and it can be pointed at afterwards. Browsing another agent's history is a
> *capability*, and a capability that exists is used by everything that has it,
> including the market agent installed last Tuesday and the one whose author you
> have never met.

### What a published fact looks like

```json
{
  "by": "work",                       │ who said it
  "at": 1785900000.0,                 │ when
  "kind": "deadline",                 │ what sort of thing
  "text": "the imaging grant closes on 2026-09-14",
  "about": ["imaging-grant"],         │ entities, so a reader can find it
  "provenance": {                     │ where it came from
    "source": "mail",
    "trusted": false,
    "note": "evidence that a mail said so — not that it is so"
  }
}
```

Four properties, each closing a way this could go wrong:

- **it names its author and its moment.** A space where facts float free of who
  said them is one where a wrong fact cannot be traced, weighed, or withdrawn.
- **it keeps its provenance.** A deadline read out of a mail stays *evidence
  that a mail said so*. Without this, the shared space becomes the laundering
  step: untrusted input goes in labelled and comes out as fleet knowledge, which
  is exactly the route the "an email is not an instruction" rule exists to close.
- **it is append-only.** Correcting is publishing a correction. History that can
  be edited is history that can be edited by whatever gets in.
- **it can be wrong.** Reading a fact does not make it true. A plan that leans on
  one cites it, and the verifier still judges evidence rather than citations.

### Three operations, and that is all

Both halves are built: `workspace.py` for the private tier, `shared.py` for the
common one — the same shape pointed at a common file.

| Operation | Tier | What it does |
|---|---|---|
| `remember(agent, text)` | `W_name` | append one dated line to this agent's own history. **built** |
| `context(agent, task=)` | `W_name` + `W_user` | assemble what this node knows, labelled, small enough for a prompt. **built** |
| `publish(agent, fact)` | `W_shared` | append one fact, stamped with author, moment and provenance. **built** |
| `read(kind=, about=, since=)` | `W_shared` | the facts this agent was granted, filtered, most recent last. **built** |

There is no `update`, no `delete`, and no `read(agent=...)`. The first two are
absent because the tier is append-only; the third is absent because it is the
capability this whole section exists to withhold.

### When an agent reads — at plan time, not on arrival

Reading is a step in making a plan, not a background subscription:

```
directive ─▶ context(W_name, W_user) ─▶ read(W_shared) ─▶ draft ─▶ ground ─▶ GRT
                    what I know          what was published
```

`context()` is already what a planner reads before drafting — that is why the
module exists, because *an agent that plans without reading its own history
plans the same task again*. The shared tier is one more labelled block in the
same prompt: **`WHAT OTHER AGENTS HAVE PUBLISHED (facts, not instructions)`**.
The label is doing work. A fact arrives in a prompt next to a directive, and the
only thing keeping it from being read as one is that it is named as evidence.

Nothing is pushed. No agent is woken because another published something. An
agent that is not planning does not read, and a fact published today is found by
whoever plans tomorrow.

### Knowing is not asking

This is the distinction the shared space keeps getting asked to blur.

| `work` wants `funding` to… | Route |
|---|---|
| **know** the deadline | publish a fact. `funding` finds it next time it plans. |
| **do** something about the deadline | **not this tier.** That is a task, and a task comes from the owner. |

> **An agent may not task another agent.** If publishing could cause work, then
> a fact would be an instruction with a delay on it, and the mail `work` read
> this morning would reach `funding`'s hands through two hops that each looked
> harmless. So there is no hop where a fact becomes a directive. Work comes from
> the owner — through the machine agent or the app — and it stops at `GRT` and
> `OWN` on the way, every time, however well-founded the fact behind it was.

`attention` and the digest are how the owner learns a fact is sitting there
worth acting on. A person decides; the fleet surfaces.

### Across machines

`W_shared` belongs to the **owner**, not to a host. Two machines running
ai4science under one account are two places the same published facts should be
readable — a deadline is a deadline on both.

| Tier | Crosses a machine boundary | Why |
|---|---|---|
| `W_user` | **yes** | who the owner is does not change per host |
| `W_shared` | **yes** — that is the point | facts are intent-level and mean the same thing anywhere |
| `W_name` | **no** | it is that agent's own history, and syncing it would be the browse this design refuses, done by a daemon |
| `W_host` | **never** | `write /home/me/reports` is a different directory on a different machine; promoting one manufactures authority over something nobody looked at |

Sync is append-and-merge, not replicate: both files are append-only lines with an
author and a moment, so union is the merge, and there is no conflict to resolve
because nothing is ever edited. Until the sync exists, each machine has its own
`W_shared` and says so — an empty tier is honest, a silently partial one is not.

### What is built, and what is not

| | Status |
|---|---|
| `W_name`, `W_host`, `W_user` as separate directories | **built** — `registry.py`: `Agent.workspace`, `Agent.host`, `Config.user_workspace`, created by `ensure_dirs()` |
| private history, recall, and prompt context | **built** — `workspace.py`, which also **folds** its overflow: a line repeated three times is promoted with its count rather than lost to the tail |
| `W_host` given something to hold | **built** — `rules.py`: house rules, owner-written, told to every session, never travelling |
| the shared append-only-log shape | **built**, for a different purpose — `ledger/*.jsonl` already records directives, reports, outward requests and vault decisions this way, across agents |
| `publish` / `read`, the fact record, the grant | **built** — `shared.py`. Facts carry author, moment and provenance; the grant defaults to no; there is no `update`, no `delete` and no `read(agent=…)`; and `workspace.py` shows a granted agent what was published, labelled *facts, not instructions* |
| cross-machine sync of `W_shared` | **designed here, not written** |

The ledgers matter as precedent: the append-only shared log is not a new
mechanism this section invents, it is the one already carrying every governance
record in the system, given a second file and a provenance field.

### What never goes up

`W_host` — tools, paths, sessions, resource readings. They are *about a host* and
mean nothing off it, and promoting one manufactures authority over something
nobody looked at: `write /home/me/reports` is a different directory on a
different machine.

`W_secret` — the vault answers ALLOW or DENY and hands nothing over, so there is
nothing here to publish.

> **`abraham` needs no special rule.** It publishes the **decision** and not the
> facts it concerns: *"booked the Tuesday appointment"* goes up; whose
> appointment, and for what, stays host-local. Other people's personal data never
> enters the shared space, so nothing has to get it back out.

### A worked example

1. `work` reads the mailbox and finds a funder's note. It **does not act on it** —
   mail is untrusted input, and an instruction inside it is not an instruction.
2. It publishes: *`kind: deadline`, "the imaging grant closes on 2026-09-14",
   provenance `mail`, `trusted: false`*.
3. `funding` reads the shared space when planning and finds it. Its plan says
   *"the funder's mail of 4 Aug states a 14 Sep deadline"* — a citation, not an
   assertion.
4. The plan still declares what it needs, still stops at `GRT`, and the
   submission still stops at `OWN`. **Nothing about a shared fact shortens the
   path to an act.**
5. If the deadline was wrong, the record shows who published it, when, and that
   it came from a mail. `work` publishes a correction; the original stays.

### Reading it is a permission

Installing a third-party agent must not hand a stranger's code everything the
owner's other agents have learned.

> **Declared at install, defaulting to no.** An agent gets `W_user` and its own
> `W_name`. `W_shared` is asked for in the manifest, shown on the install screen,
> and granted by the owner or not at all.

## 10. Both doors (Point 8)

| | Telegram | the ai4science CLI |
|---|---|---|
| how | one bot per agent, owner-locked | `/agent <id>`, or ask non-interactively |
| best at | approvals, vault prompts, the digest, a quick question | long planning turns, pasting files, reading a plan |
| reaches | the same agent, the same `W_name`, the same sessions | the same |

> **A surface is a door, not a scope.** An agent has one memory and one set of
> sessions regardless of which door the owner came through, and never re-asks
> something answered on the other one.

A **bot token is a vault secret**, not a config value: an agent that held its own
token could be moved, and then spoken to somewhere the owner is not looking.

## 11. The market (Points 1 and 2)

Three kinds of listing — **agents**, **tools**, **sub-agents** — each uploadable,
accepted by the governor, and installable. This is where they live, because an
agent is a thing you install on your own machine and run with your own keys; a
market that lived anywhere else would make using an agent require something else.

Acceptance asks a different question of each: an agent, *what may it do*; a tool,
*what does it touch* — it is closer to the hardware than any agent; a sub-agent,
*does it obey the ceiling and report honestly*. A verifier is the sharpest to
accept, because a lenient one inflates the record of every agent it judges.

**An accepted listing earns.** Uploading is not charity: an author whose agent,
tool or sub-agent is accepted is rewarded in PWM, and thereafter takes their
chosen fraction of the 5% slice on every run that uses it (§13). This is the
same for all three kinds — a tool or a sub-agent that everyone's agents plug into
is worth as much as an agent, and paying only for agents would starve the sockets.

**Trust is not transitive.** An agent may bring its own tools — one author, one
review — or require ones from the market, and then the install screen names every
author whose code comes with it and what each part may touch.

### What is built, and what is not

The split follows this page's governing property — *everything here works with
nothing else installed*:

| | |
|---|---|
| **built** | the package format; `pack` · `review` · `accept` · `publish` · `install` · `list` · `remove`; the acceptance questions asked **at install, by the machine doing the installing**; the digest that ties what was reviewed to what is installed; the signature that carries a governor's judgement; the roster entry, the empty workspace and task list it creates; the author list shown before the owner commits |
| **not built** | nothing of §11. The 5% slice is computed and recorded per run — see §13 |

**The server is a transport detail, not the trust.** Uploading needs somewhere
to upload *to*; acceptance does not. `review` asks the acceptance questions
mechanically, on any machine, by anyone — so acceptance stops being a claim the
market makes and becomes a thing a reader re-runs and gets the same answer to.
What is left is the judgement, and that is a **signature over the digest**:

| | |
|---|---|
| `pack` | seals the directory into a listing with a content digest — over **every file**, because a digest over the manifest alone leaves the obvious escape open: ship the reviewed manifest beside a tool nobody looked at |
| `review` | the same questions the install asks. One set of rules, or a package that reviews clean and then refuses to install makes the review worth nothing. Every problem at once — an author fixing four things should be told four things |
| `accept` | a signature over that digest, and the governor's whole contribution, because it is the only part that is judgement rather than arithmetic. A package that would not review **cannot** be accepted: a signature that could override the checks would make the checks decorative |
| `publish` | writes the listing to a file inbox, the same handshake the compute design uses. HTTP later changes the transport and nothing else |
| `install` | says which standing it has — accepted by whom, or **UNREVIEWED**, on the way in |

An acceptance does not travel: it is matched on the digest, so it is not valid
for a neighbouring version and does not survive the package being edited after
it, and the signature is checked so a record *saying* `by: governor` is not one.

**A signature is not a waiver.** Every refusal above runs for every package
whoever signed it — the acceptance is read *after* them, and decides what the
owner is told, never what gets past. That is what makes a sideloaded package and
an accepted one equally safe to install, which is the property that lets this
work with no server at all.

**Review does not run the package.** `tests/` is what the author says proves it
works, and running it to decide whether the author can be trusted is executing
untrusted code to find out whether it is trustworthy. What tests exist is
recorded and shown; running them is the installer's own call, on their own
machine, after they have decided.

The point of putting acceptance at install rather than at upload is that it
holds either way. A listing's own claims are what the **market** needs; they are
not what the runtime trusts. So a package that arrives by any route — accepted,
sideloaded, handed over on a disk — meets the same four refusals:

  * **it may not ship a `workspace/` or a `tasks/`.** One arriving with tasks
    files work the owner never asked for, past `CAP`, past the plan, past the
    grant, and this install is the consent step it would walk through. One
    arriving with a workspace is an author writing standing instructions where
    the agent reads at plan time. Refused, and told — not stripped, because an
    author who packed it asked for something.
  * **the four reserved classes are refused**, in `agent.json` *and* in
    `roster.json`. Both declare outward classes; checking one is checking
    neither.
  * **an agent does not set its own `ceiling`**, `standing_grants`, `retired`
    or `digest`. Those are the owner's, and a manifest that could set one would
    make installing an agent a way to grant one.
  * **its `id` is checked as a directory name**, because that is what it is —
    every folder and session store is keyed by it, so `../../etc` and a
    collision with an installed agent are the same class of refusal.

**Trust is not transitive, on the way in.** The install prints every author
whose code comes with the package — the agent's, and each tool's — with what
each part touches, before it is done. An installed agent runs at the everyday
ceiling like everything else, with an empty workspace and task list this machine
made.

**Removing keeps the folder.** Same reasoning as retiring: a folder is the
record of what an agent did, and an uninstall that deleted it would make the
record of the work depend on still wanting the tool. The seven that shipped with
the machine are not market listings and refuse to be uninstalled at all.

### What an agent package is

```
sarsi-agent-<name>/
  agent.json      identity, purpose, author, version, price
  spec.md         what it is for, in the author's words — shown in agents-search
  roster.json     tools it expects · outward classes it may complete
  tools/          plug-ins it brings (§11a)
  subagents/      sub-agents it brings, e.g. a specialised sarsi-claude
  tests/          what the author says proves it works
```

```json
{
  "id": "protein-fold",
  "version": "1.2.0",
  "author": {"handle": "…", "pwm_address": "…"},
  "purpose": "one line, shown in agents-search",
  "tools": ["browser", "pymol"],
  "outward": [],
  "reserved_refused": ["money", "consent", "publishing", "legal"],
  "price_share": 1.0,
  "requires": {"ai4science": ">=…", "subagents": ["sarsi-claude>=…"]}
}
```

Everything above is what the **market** needs and nothing the runtime should
trust. But the package as written describes an agent that cannot run, because it
never says where the agent *lives*:

> **Every agent owns a workspace and a task list. Both are created by the
> installer, and neither ships in the package.**

The runtime already does this — `ensure_dirs` gives every roster entry
`workspace/`, `host/`, `tasks/`, `sessions/` and `selfmodel/` under its own
id — and the package format has to say so, for one reason that is not
bookkeeping:

**an author must not be able to ship a task list or a workspace.** A package
that arrived with tasks already in it would file work the owner never asked for,
past `CAP`, past the plan, past the grant — the market's install screen is a
consent step, and pre-filled work walks straight through it. A package that
arrived with a workspace would be an author writing standing instructions into a
place the agent reads at plan time, which is the same hole `rules` closes by
requiring the owner's `--sign`. So the installer creates both **empty**, keyed by
the installed id, and a package containing either is refused at acceptance.

**This holds for agents that never execute, too.** The manager (`sarsi-machine`
here, and the app's manager agent) and the machine agent in both apps get the
same two directories as any worker. Their task lists stay empty by construction —
`worker.admit` refuses a manager, which is §2 in code — and that is exactly why
they must exist: *"no tasks"* and *"no task list"* are different answers, and the
first is only readable if the second is false. The workspace is not empty for
them: it is where the manager's own record lives, so the agent you talk to has a
history you can read even though it has no work you can point at.

What a manifest *does* declare in their place is **reach** — which workspaces the
agent reads and publishes to — and §11z below carries that form.

### 11z. Installing an agent: the workspace exists, the *reach* is declared

A package is what the author ships. **The workspace is what this machine
creates** — it belongs to one owner, on one machine, under that agent's
`W_<name>`, and for a research agent it is most of what the agent actually is:
charter, self-model, field map, budget, three ledgers, a corpus cache and the
benchmark seeds.

**It is not declared, because every agent has one.** `Agent.workspace`,
`Agent.host` and `Agent.tasks` exist unconditionally in the registry, for the
machine agent as much as for a worker; a path in a manifest would be describing
one installation from inside the package. What a manifest declares is **reach** —
which workspaces it reads and publishes to, and the two boundary rules below.
The market spec §3a
([`2026-08-04-sarsi-agent-market-and-pwm-design.md`](2026-08-04-sarsi-agent-market-and-pwm-design.md))
carries the full form.

Three declarations matter on *this* machine specifically:

| Field | What it prevents here |
|---|---|
| `never_stage` | the answer key reaching the sandbox. A solver that reads `data/labels.npy`, or a reconstruction that reads the ground truth, passes every judge by copying it. The list is enforced at staging, next to the code that stages. |
| `never_packaged` | an installed agent arriving with its autonomous switch **on** or a budget already granted. Both are the owner's (§8), and a package that carried them would let the author decide that this machine runs overnight and spends. |
| `owner_signature_required` | an agent adopting its own improvement. Proposing is the agent's; adopting is the owner's. |

**The corpus is the exception that proves the shape.** It is the largest thing
in a workspace and the only part shared between agents on a machine — several
agents read the same TCGA or DUD-E cache — so it is declared with a fetch
command and a size, and an agent whose corpus is absent **refuses and names the
command** rather than substituting generated data. The workspace declaration is
where that requirement is visible before anything is installed.

### The exchange node also exchanges compute

The exchange node was built to trade **LLM credentials**. It trades **GPU
compute** on the same rails, and for a reason that is not symmetry: the agents
this system is built for are the compute-hungry ones. A computational-imaging
reconstruction is not an LLM call with a bigger context — it is hours on a card,
and an agent that cannot get one cannot finish.

Two facts decide whether a job can land on a provider's machine, and they are
known in **different ways**. Getting them from the same place is the mistake.

| | How | Why not the other way |
|---|---|---|
| **operating system** | **declared** by the provider — `linux`, `windows`, `macos`, and nothing else | It is a **routing constraint**: a solver built against CUDA on Linux does not run on Windows, and neither runs on Apple Silicon. It is not read from the process that registers, because `join` gets run from WSL, from containers and over SSH — the platform underneath *that* is not evidence about the box that will serve. Only the provider knows which machine that is. |
| **GPU** | **detected** on the OS just declared | It is a fact about the machine, so the machine answers. A provider typing `--kind gpu` on a box with no card is not lying, they are guessing — and the first heavy job is an expensive place to find out. The OS comes first because *how you ask* differs: `nvidia-smi` on Linux and Windows, `metal` on a Mac, where there is no CUDA to ask about. |

**Detection that could not run reports `unknown`, never `none`.** A driver that
was unreadable must not register as a CPU-only box, because a user picking a
provider reads that as a checked fact — the same rule `blast`, `spend` and
`budget` already follow about what was not observed. So the refusal is narrow:

* the machine answered **"no GPU"** and the provider claimed one → **refused**,
  with the reason, before any user's PWM is at risk;
* the probe **could not run** → **registered**, and recorded as unobserved.
  Locking out a real provider on the strength of something never seen would
  treat a failed probe as a missing card.

Both go into the provider record — `system` and `detected` kept apart from
`device`, so a reader can tell a card the machine reported from one a provider
typed in. The owner's own two boxes are one Windows and one Linux, which is why
this is the shape rather than a Linux assumption with an exception bolted on.

## 11a. The tools and sub-agents this system needs (Point 13)

A **tool** is something a task needs *present* to run — checked at `CAP`,
declared per agent as a profile, and refused by name when absent. A **sub-agent**
is something that does the work or judges it, plugging into a socket the runtime
provides.

### Sub-agents

| Sub-agent | Socket | Status |
|---|---|---|
| **`sarsi-claude`** | the session backend — start · send · interrupt · stop · ceiling · has · capture · await_ready, plus `delivers_plan_at_start` | **built.** The reference implementation, and the shape every other sub-agent matches. The last flag is not decoration: a backend whose `start` quietly ignores the plan reports success having delivered nothing, and a work session once sat at an empty prompt acting on placeholder hint text while the record wrote `plan_bytes` for something never sent |
| **the planner** | drafts the seed plan the session then grounds | **built** |
| **the verifier** | given criteria and evidence, answers PASS/FAIL or refuses | **built.** A domain verifier is a market listing |
| **a domain runner** | reconstruction, docking, simulation — work that is not code editing | market |

### Tools the seven need

> **How presence is decided.** `CAP` answers from three lists and nothing
> else: `shell`, `editor` and `documents` are **inherent** — the worker runs in
> a shell and edits through the session; `mail`, `calendar` and `payment` need
> an **account**, and are absent until the vault holds one; `matlab`, `qupath`,
> `browser`, `claude`, `codex`, `tmux` and `git` are **binaries**, each with its
> own candidate names. A tool on none of those lists is reported **absent with
> its reason** — `no probe for 'zotero' — unknown tool` — and is never guessed
> at from `PATH`. Run against the real registry, all seven agents answer
> specifically: `browser  False  not on PATH (chromium, chromium-browser,
> google-chrome, firefox)`.
>
> **What the owner can add.** `tools.json` is a probe CACHE — an absent entry is
> re-probed every pass, a present one ages out in fifteen minutes — so nothing
> written there by hand survives. A tool `CAP` cannot check is declared instead,
> in `tools-declared.json`: it does not expire, it is reported as *declared by
> the owner — not probed*, and it never overrides a probe. Declaring `matlab`
> present on a machine without `matlab` is a claim the probe falsifies, and a
> declaration that won there would switch off the one check that catches it.
>
> *An earlier version of this note said `CAP` fell back to `shutil.which` for
> anything unnamed, so a fresh install read `{'shell': False, 'editor': True}`
> off unrelated binaries. That was true of an earlier `CAP` and is not true of
> this one; it was merged here from the mirror without being run.*

| Tool | Who | What it touches |
|---|---|---|
| `shell` | `sarsi-worker` | the machine, as the owner |
| `editor` | `sarsi-worker` | files in the task's reach |
| `browser` | `sarsi-worker`, `social`, `funding`, `jobs`, `abraham` | the network, and pages that can lie to it |
| `mail.read` | `work` | the mailbox — **read only. No agent on this plane has a `mail.send`**, and the console's email agent, which does send, is not reachable from here |
| `documents` | `funding`, `jobs`, `abraham` | office files and PDFs |
| `calendar` | `abraham` | other people's whereabouts — `W_host`, never shared |
| `payment` | `abraham` | **prepare only.** `money` is reserved and no agent completes it |
| `qupath`, `matlab` | `work` | instrument data and licensed desktop software |

### Tools this design has assumed and not named

| Tool | Why it is needed | The review question |
|---|---|---|
| **GUI control** | `qupath` and `matlab` are desktop applications. A tool that "has MATLAB" and cannot drive its window can run a script and nothing else. `jobs` filling an application site hits the same wall the moment a page is not automatable. | it can click anything on the screen, including windows that are not the task's |
| **file transfer** | getting a result off the machine is an outward act and must go through `OWN`; getting an input *onto* it is not, and has no tool | where a file came from, and whether an agent chose it |
| **secrets rotation** | the vault stores; nothing rotates | it holds every credential at once |
| **notification** | `digest` composes and the Telegram bot delivers, so an owner *with Telegram configured* is reachable — and it is off by default. What is missing is a notifier that does not depend on that one channel | it can interrupt a person |

### Figma and TeamViewer

Both were suggested, and they are different kinds of thing.

**Figma — a design tool, and a reasonable market listing.** `social` drafting a
post image, or a design agent producing a mockup, is ordinary work with an
ordinary outward gate: the file is composed locally and publishing it stops at
`OWN`. It touches a network service and the owner's design account, so its
credential is a vault secret like any other. There is no new authority here, and
this repository already carries figma prototypes made exactly this way.

**TeamViewer — remote desktop, and the most dangerous tool in this document.**
It is worth being precise about which of two things is meant, because they are
opposite:

| Reading | What it is | Verdict |
|---|---|---|
| **the agent drives the desktop** — GUI control by another name | the same capability as the GUI-control row above, over a heavier protocol | **acceptable, as a tool with that review**: it can click anything, so it is declared, profiled, and gated like any other reach |
| **a remote party controls the machine** | an inbound channel that bypasses every gate on this page | **refuse.** |

> **The second reading inverts the whole design.** Every rule here says that the
> thing which acts is local, bounded by a ceiling, and answerable to an owner who
> can see it. A remote-control channel is an actor with no ceiling, no plan, no
> verdict and no record — and it would not be *breaking* the gates, it would be
> *going around* them, which is worse because nothing would report it.

> **If remote help is genuinely wanted**, the shape that fits this design is the
> one `interact` already uses: the owner attaches to a terminal they own, and
> the session keeps running under the same hook. A human who needs to see what
> is happening is a human at a door, not a second driver — the wheel exists
> because two of those is one too many.

## 11b. Research agents (Point 11)

A **research agent** — computational imaging, cancer, drug design — has two
functions. The first is ordinary: it holds tasks and works them through
`sarsi-claude` like any agent. The second is **autonomous research**, driven by
its own self-model: it works on owner-set tasks, on benchmarks, or on the
charter it shipped with, without being asked each time.

**It is off by default**, because it spends money on its own. Turning it on is a
standing, revocable permission with a budget; reaching the budget stops the loop
rather than asking for more. An agent may not turn it on or extend it.

> **Every gate still applies.** A research run produces a plan with
> `Verified when:` lines, stops at the grant for anything the plan declares,
> stops at the outward gate before anything leaves, and is judged by the same
> independent verifier. What the owner gave up is being asked each time; what
> they kept is every gate.

> **Self-directed work is recorded apart from the owner's.** An agent that wrote
> its own benchmark, passed it, and counted the pass toward its record would have
> published its own reputation — so owner-set tasks, benchmarks and self-directed
> research are three lines and never one number.

### One workspace, one task list, two functions

Both functions run against the workspace this machine created at install
(§11z) and the single task list in it. **One of each, deliberately.** Two would
give the agent a private record of itself beside the one the owner reads, and
the first thing to diverge would be the part that flatters it.

| State in `W_<name>` | 1 · on demand | 2 · autonomous |
|---|---|---|
| task list | works owner-created tasks | creates its own, from owner tasks, benchmarks, or the charter |
| `selfmodel.json` | written by `observe()` — measured, never asserted | the same file, and also the **queue**: where its evidence is thin is where it works next |
| `fieldmap.json` | not used | worked, and not repeated |
| `charter.json` | bounds the work | bounds it, and supplies the direction when the other sources are empty |
| **switch, budget** | **not touched** | required, owner-set, never packaged |
| ledgers | `owner` | `benchmark`, `self_directed` |

**Function 1 does not read the switch.** An agent that needed autonomous
research turned on before it would answer a question would have made a standing
spending permission the price of ordinary use. It is stated in `tasks.json` and
held by a test: `test_a_user_task_runs_with_the_autonomous_function_OFF`.

**The source is stamped when a task is created, by whoever created it, and is
never rewritten.** That is what makes "three lines, never one number"
enforceable rather than a promise — an agent that could set the source could
file its own research as work the owner asked for.
(`test_a_user_task_lands_in_the_owner_ledger_only`,
`test_the_three_ledgers_are_kept_apart`.)

**Turning the switch off does not empty the task list.** Self-directed tasks
already created keep their source; the owner chooses whether a running one
finishes or is closed. Deleting them on revocation would erase exactly the
record the owner wants to read after turning it off.

### What a research agent is FOR: an ordered list of problems (Point 23)

A research agent is not "an agent that does science in this field". It is an
agent that holds **the field's open problems, in the order they have to be
solved**, and knows which one is next. Without that it is a chatbot with a
budget.

The order is not a preference. It falls out of what a field is made of, which
is the same four tiers the registry already uses and the same four
`physicsworldmodel.org` publishes:

| | | why it comes before the next |
|---|---|---|
| **L1 principle** | the physics or biology the field rests on | a spec that contradicts the principle is wrong in a way no benchmark will catch |
| **L2 spec** | the forward model — what a measurement *is* | a benchmark without one measures agreement with an implementation, not with reality |
| **L3 benchmark** | the task, the data, the metric | a solution with no benchmark cannot be beaten, only asserted |
| **L4 solution** | a method that meets or beats the bar | the only tier where "better" is a checkable claim |

So the ordering rule is: **solve what unblocks the most tiers below it, among
the things that can be verified now.** Two clauses, and the second is doing as
much work as the first — a principle nobody can test yet unblocks nothing,
because every tier under it inherits the doubt.

Worked, for **computational imaging**, which is the field furthest along:

| # | problem | tier | why here |
|---|---|---|---|
| 1 | the forward model disagrees between papers — mask convention, dispersion, normalisation | L2 | every number below it is uncomparable until this is settled. The CASSI wrapper bug that cost 35.5→28 dB was exactly this, one layer down |
| 2 | a benchmark that fixes data, mask and metric together | L3 | a metric on unfixed data measures the data |
| 3 | baselines re-run under that benchmark, not quoted from papers | L3 | a quoted number is a claim about somebody else's forward model |
| 4 | **the coding optic as a design variable, with its tolerances** | L2 | *see below* — ties with #3, and the tie is arbitrary |
| 5 | **does the fabricated optic match the one that was designed** | L3 | a mask optimised in simulation does not match when built |
| 6 | **optimise the optic and the reconstruction together** | L4 | the field's actual claim |
| 7 | a solution that beats the re-run baselines | L4 | the first checkable "better" in the field |
| 8 | the principle behind why it beats them | L1 | promoted *last*, because a principle inferred from one win is a story — and now it has the hardware half to explain too |

##### The hardware half: the optic is a design variable, not a constant

The first version of this table was the **algorithm** ladder, and on its own it
treats the coding optic as given. That is a real omission rather than a
simplification, because computational imaging is **co-design**: a solution
scored on an arbitrarily chosen optic is a solution to an arbitrarily chosen
problem, and its number is a fact about that choice as much as about the method.

This machine already had the evidence and did not draw the conclusion. The
binary-vs-continuous mask question moved HDNet **35→28 dB** — and *the mask is
the coding optic*. "Which mask" looked like an implementation detail and is a
hardware statement wearing one's clothes.

So three problems join the list, and they **interleave** with the algorithm
ladder rather than following it. That interleaving is the point: if the hardware
problems came after the algorithm ones, the list would be saying *design the
method, then design the optic to suit it*, which is the thing co-design says
does not work.

* **the optic and its tolerances** (L2, after the forward model) — settled when
  the spec states each parameter *and the tolerance on it*, and two masks
  differing only within tolerance land within the benchmark's noise. A
  tolerance-free optic spec is unbuildable, and an unbuildable spec is a
  simulation.
* **built versus simulated** (L3) — the measured point-spread function of the
  fabricated optic against the designed one. **This is the one problem in this
  field that needs a body**, and it is where the embodied member of the group
  (§ the group with a body) stops being an illustration: nothing in software
  settles whether a fabricated mask matches its design.
* **co-design** (L4, after both) — a jointly designed system that beats the best
  algorithm-only result on the fixed benchmark, with the optic's tolerances
  respected. The tolerance clause is what stops it being won by an optic nobody
  can make.

Two of the three are marked as **readings of the field, not evidence this
machine holds** — no optic has been fabricated here and nothing has been jointly
optimised — and `sarsi problems` prints that on the line rather than in a
footnote.

Note where L1 sits. A field's principle is often the **last** thing that can be
verified, not the first — which is why "start from first principles" is bad
advice for an agent that has to show its work.

> **Built for computational imaging** — `sarsi problems computational-imaging`.
> The order is **computed from the rule, not sorted by hand**: a hand-ordered
> list is one person's judgement wearing an algorithm's clothes, and nobody can
> later tell whether it moved because the field did or because somebody edited
> it. The two clauses are applied in order, and that order is the design —
> *can be verified now* is a **filter**, so a problem whose dependencies are
> open is not a candidate however much it would unblock. Ranking the other way
> puts the most valuable unverifiable thing at the top, which is where a field
> goes to argue instead of measure. *Unblocks the most* then ranks what is
> left, counted transitively.
>
> A cycle, a dependency that is not in the list, and a duplicate id are
> **refused** rather than ordered anyway — an order produced from any of them
> is an arbitrary one carrying an algorithm's authority. Each line says what
> would settle it and why it sits where it does, so the list is arguable rather
> than authoritative.
>
> The table above is the output, and a test asserts it: the rule applied to the
> real problems has to reproduce it, or the rule is wrong or this document is.
>
> Two honesty fixes the longer list forced, both worth keeping because both were
> the list making a claim it could not support:
>
> * **only what is ready today says "ready now".** The ordering walk marks each
>   pick solved as it goes — that is how it finds the next frontier — so reading
>   readiness off the walk labelled all eight problems ready while their
>   dependencies sat open. The walk's *now* is not the reader's *now*, and the
>   reader is the one being told. Every other line names what it waits for.
> * **a tie says it is a tie.** Re-running the baselines and specifying the
>   optic both unblock three, and they are separated alphabetically, which is
>   arbitrary. Printing the same reason at two different positions has a reader
>   mistake position for judgement.

**Each research agent has its own page** on `physicsworldmodel.org`, and the
page *is* the problem list: the open problems in order, what tier each sits at,
what is solved, and by whom. A page that showed only finished work would be a
brochure; the value is that a reader can see what is next and take it.

#### The scope, and the experts who set it

A research agent needs a **scope** — what is in this field and what is not — and
the scope is not the agent's to decide. It is set by **experts in that field**,
and it may be fixed or may evolve as the field does.

This is not an extra layer of approval. It is the thing that makes every other
rule in this section mean something:

* the **ordered problem list** is a list of problems *in a scope*. Without one
  the ordering rule ranks a set nobody agreed on, and "solve what unblocks the
  most" becomes "solve what unblocks the most of whatever I happened to write
  down."
* the **verifier** judges against criteria written inside a scope. A verdict on
  a problem outside it is a correct answer to a question the field did not ask.
* the **field split** in §27 is a scope decision — *this sub-scope has more
  energy than the field around it* — and it is exactly the judgement an agent
  is worst placed to make about itself.

So the design gains a role it did not have, and it is a **human** one:

> **An expert guides the agent by owning its scope.** They say what belongs in
> the field, they change it when the field changes, and the agent works inside
> it. The agent may **propose** a change to its scope, with its reason and its
> evidence, and may not adopt one.

That is the propose/hold/sign shape again — the same one that governs house
rules, plan adoption and RSI — and it is here for the same reason: *an agent
that can widen its own boundary has no boundary.*

| | who | what they may do |
|---|---|---|
| **the owner** | runs the machine | grants, releases, sets the ceiling and the budget |
| **the expert** | knows the field | owns the scope; signs a change to it; is the human in §24's verification chain |
| **the agent** | works | proposes a scope change with evidence; works inside the scope it has |

**The owner and the expert are not the same person, and the design should stop
assuming they are.** The owner of this machine can grant a write and cannot tell
whether a somatic-variant classifier is asking the right question. §24 said a
criterion the owner cannot check is one they are accepting on faith — the expert
is the answer to that, and naming them as a role is what makes the sentence
actionable rather than a warning.

**A scope that evolves is recorded, not edited.** When an expert widens or
narrows it, the change is an entry with a date, a reason and a signature —
because a scope silently rewritten makes every past verdict unreadable: nobody
can tell whether a result was in scope when it was produced. Same reasoning as
the plan-drift rule, one level up.

**And an agent with no expert says so.** Not a hidden state: its page carries
who owns its scope and when they last touched it, alongside the line §27 already
requires about when a person last checked a result. A field whose scope nobody
maintains and whose results nobody verifies is not a research programme; it is a
budget being spent, and the page should let a reader see that in one look.

### The two functions, and who verifies what (Point 24)

Every research agent has exactly two, and the difference between them is who
started the work, never what the work may do:

| | **on demand** | **autonomous** |
|---|---|---|
| started by | the owner asks | its own self-model, charter, or an open problem on its page |
| picks the problem | the owner | the ordering rule above |
| the switch | not read at all | required, owner-set, revocable, budgeted |
| ledger | `owner` | `benchmark` / `self_directed` |

**Every gate is identical across the two.** That is the point of having two
functions rather than two agents: the second is the first with the asking
removed, and nothing else.

**How a person verifies.** They read the plan's `Verified when:` lines before
granting, and the verdict after. Both name artefacts — a file, a number, an
exit code — so verification is *reading a result*, not *trusting a narrative*.
On a research agent this matters more than anywhere else, because the work is
in a field the owner may not know: a criterion they cannot check is a criterion
they are accepting on faith.

**How a sub-agent verifies.** The verifier is a sub-agent, and on a research
agent it is a **domain** verifier — it re-runs the benchmark rather than reading
the claim. The market's own note applies hardest here: *a verifier is the
sharpest thing to accept, because a lenient one inflates the record of every
agent it judges.*

**How a sub-agent teaches a person to verify.** This is the part that decides
whether any of it is worth trusting, and it is a deliverable, not a courtesy:
alongside the verdict, the verifier emits **the check itself** — the command,
the data, the expected value, and what a wrong answer would look like. The
owner runs it. Then they can verify the next one without the agent, and the
one after that they can *disagree* with it. An agent that cannot teach its own
check has not been verified; it has been believed.

> **Independence is the whole of it.** A verdict from the same engine that did
> the work already says so, in the record. A field where the only verifier is
> the agent's own sub-agent has a number nobody outside has checked, and §27
> below is what that becomes if nothing stops it.

### What one research agent is made of (Point 25)

Taking computational imaging as the worked example. **Sub-agents** are things
that do or judge; **tools** are things that must be present to run.

| Sub-agent | Socket | What it is for |
|---|---|---|
| `sarsi-claude` | session backend | drives the work, at the ceiling it was released to |
| the planner | drafts the seed plan | turns an open problem into phases with checkable criteria |
| the **domain verifier** | given criteria + evidence | re-runs the benchmark; the sharpest listing to accept |
| the **reconstruction runner** | work that is not code editing | GAP-TV, deep-unrolled, transformer — the actual method |
| the **teacher** | emits the owner's own check | the deliverable of Point 24, not a summary |

| Tool | What it touches | Refused by name when absent |
|---|---|---|
| `shell` | the working directory | yes — `CAP` |
| `editor` | declared paths | yes |
| GPU / CUDA | the card | yes — and the OS is declared before it is probed (§13) |
| the benchmark corpus | a read-only cache, shared between agents | yes, **and it names the fetch command** rather than substituting generated data |

That last row is the one with teeth. An agent whose corpus is missing must
**refuse and say how to get it**. Generating stand-in data and proceeding is how
a field fills with results nobody can reproduce.

### Self-awareness, in a research agent (Point 26)

The self-model is not a personality. It is **a measured record of where this
agent's evidence is thin**, and it has one job: to decide what the autonomous
function works on next.

* it is **written by `observe()`** from outcomes — verdicts, benchmark results,
  refusals — and never by the agent asserting things about itself. Measured,
  never claimed, for the same reason a verdict comes from a verifier.
* it is **the queue**: where the evidence is thinnest is where the next
  self-directed task goes. That is how "what should I work on" stops being a
  preference and becomes a reading.
* it is **one file, read by both functions**. Two would give the agent a private
  record beside the one the owner reads, and the first thing to diverge would be
  the part that flatters it.

So self-awareness here is instrumental: it exists to aim the work, and it is
auditable because it is derived from things that already have verdicts on them.

### Redesigned: a research agent is a GROUP, and some of it has a body

The sections above describe a research agent as one agent with sub-agents
plugged into it. That was right while everything it could do reached a screen or
a file. It stops being right the moment a sub-agent can pick something up.

**Human labour in a lab is going to be done by robots**, and the work a research
agent is for — run the assay, load the sample, align the optics, image the
plate — is exactly that labour. So the design has to answer a question it has
never had to answer: what happens when an agent's act is not a file.

So a research agent is redesigned as a **group** — one workspace, one task
list, one ceiling, members that talk to each other directly, and one agent as
far as anyone outside is concerned. Within it there are three kinds of member,
and the kinds are defined by *what their acts reach*:

| kind | reaches | can it be undone |
|---|---|---|
| **reasoning** — planner, composer, self-model | a file in the workspace | yes, trivially |
| **judging** — the domain verifier, the teacher | a verdict and a check | it is the thing that decides, so it is never the thing that acts |
| **embodied** — the bench, the stage, the arm | **the world** | **no** |

#### One workspace, one body: what makes the group ONE agent

The members are not seven agents cooperating. They **share one workspace, talk
to each other directly, and stay in agreement** — from outside the group there
is one agent, with one task list, one ceiling, one record and one verdict. The
owner deals with a thing, not a committee.

This is not a hole in §9's *"there is no channel between two agents"*. It is
what that rule was always about. The rule keeps `work` from sending to
`funding` — two agents with different scopes, where a pipe would let one act on
the other's behalf. **Inside one research agent there are no two scopes.** The
planner, the runner, the verifier and the bench are all working the same
problem, on the same evidence, under one grant, and giving them a shared
workspace does not widen anything — it is the workspace that agent already had.

So the boundary moves down a level and the rules keep their shape:

| | inside one group | between groups |
|---|---|---|
| workspace | **shared** — one `W_<name>` | separate |
| talking | **direct** | publish, never browse |
| task list | one | one each |
| ceiling | one, and it is the **lowest** any member's act needs | one each |
| a fact travels by | being written where all of them read | being **published** and read at plan time |

#### And the one thing "in agreement" must not mean

Sharing a workspace makes the members agree about **what happened** — one
record, so the runner and the verifier cannot hold different accounts of what
was run. That is the point, and it is the same reason there is one self-model
and one task list rather than two: *the first thing to diverge would be the part
that flatters it.*

It must not make them agree about **whether it is good**:

> **They share the evidence. They do not share the verdict.**

The verifier reads the same files as the runner and reaches its own conclusion
about them, and a group where the verdict is agreed by construction has replaced
verification with unanimity. That is not a smaller version of the closed loop in
§27 — it *is* the closed loop, moved inside one agent where it is harder to see.

The practical test is the one this system already applies: a verdict from the
same engine that did the work says so, in the record. A group verdict that
cannot say which member reached it, from what evidence, and what would have
changed its mind, is one voice with several names.

**"Like one body" is exactly the right image, and it cuts both ways.** A body
has one memory and acts as one thing — and a body whose nerves only ever report
what the hand hoped is one that burns itself.

#### The rule a body forces

This system already has the sentence, in `undo`, written for a published post:

> *no way to retract a `<kind>` on `<destination>` is wired in here. Take it
> down yourself; this will not pretend it did.*

For an embodied sub-agent that is not an edge case, it is **the normal case**. A
pipetted reagent, a cut, a moved stage, a fired laser: there is no retraction,
and the honest design does not pretend otherwise. Which gives the group's first
rule:

> **An embodied act is irreversible, and is treated as irreversible by default.**
> `outward` already asks *reversibility* before it asks anything else; for a
> body the answer is always "no", so an embodied act needs the grant that
> irreversible acts need, every time, and a standing grant does not cover it.

Two more follow from it, and both are refusals this document has argued for
elsewhere and now has a harder case for:

* **an embodied sub-agent may not verify its own act.** The group's verifier
  judges from *evidence the body produced*, not from the body's report of what
  it did. This is the independence rule with the stakes raised: a closed loop
  in §27 gives you a wrong number, and a closed loop here gives you a wrong
  number **and a changed bench**.
* **the group's ceiling is the LOWEST of its members', not the agent's.** An
  agent released to A1 whose arm sub-agent could act at A2 has been released to
  A2 by the back door. The ceiling belongs to the act, and the act with a body
  sets it.

#### What the group looks like, for one field

Computational imaging again, because it is the one with real optics:

| member | kind | acts on | what its refusal is |
|---|---|---|---|
| planner | reasoning | `plan0.md` | refuses a criterion no independent verifier can read |
| reconstruction runner | reasoning | the GPU, files | refuses when the corpus is absent, **naming the fetch command** |
| domain verifier | judging | the benchmark | refuses to judge a plan that has drifted from what was released |
| teacher | judging | the owner's own check | refuses to report a pass it cannot hand the owner a way to re-run |
| **optical bench** | **embodied** | mask, stage, camera | refuses **every** act without a grant naming that act; reports what it moved, never what it intended |

The bench row is the whole change. Everything above it can be re-run; the bench
row can only be *reported*.

#### Where this leaves §27

The collapse section said a field ends when agents verify agents and no human
checks. With a body in the group, that end state has a physical half, and the
honest handling is the same one and needs saying more loudly:

> **A field whose embodied acts no human has checked is a field whose page says
> so** — how long the chain of agent-only verification has run, and *what was
> physically done* during it. A reader deciding whether to trust the field can
> then see the one thing that decides it, and the one thing they cannot undo.

**What is built, and what is not.** The reasoning and judging members are built
or specified above. **Nothing embodied is built**, and this section is a design
that says what would have to be true first: irreversible-by-default, no
self-verification of an act, the group's ceiling set by its lowest member, and
`undo`'s refusal — *this will not pretend it did* — as the normal case rather
than the exception.

### Recursive self-improvement, and how a field ends (Point 27)

**RSI without human intervention** is the autonomous function pointed at its own
playbook: the agent observes where it fails, proposes a change to how it works,
tries it, and keeps what the verifier passes. Today it **proposes and holds**,
and the owner signs — an agent that can adopt its own improvement can widen what
it may do, and the propose/hold/sign shape exists for exactly that.

The end state described here removes the signature. What replaces it is
**agents verifying agents**: a change is adopted when independent sub-agents,
and agents from other fields, pass it. That is a real mechanism and it has a
real failure mode, which this document should name rather than assume away:

> **Independence is not the number of verifiers, it is where they came from.**
> Sub-agents an agent brought with it are not independent of it, however many
> there are. A field whose verifiers all descend from the agent being verified
> has a closed loop with a number on it, and the number will be excellent.

**A field then ends in one of two ways.** Both are called collapse and they are
opposites:

| | **saturation** | **exhaustion** |
|---|---|---|
| what happened | the problems are being solved faster than people can follow | the open problems are not worth solving |
| who verifies | other AI agents; no human in the loop | nobody, because nobody is asking |
| the tell | the page's problem list keeps clearing and nobody reads the results | the problem list stops moving and nobody adds to it |
| the risk | a closed verification loop nobody outside has checked | a live agent spending a budget on nothing |
| **what it becomes** | **RSI takes over** — the loop is the field | **the frontier closes; the toolbox does not** |

**Saturation is not a terminus, it is a handover.** A field being solved faster
than people can follow *is* the condition recursive self-improvement runs under:
the agent's next problem comes from its own self-model, its verification comes
from other agents, and the loop closes. §27 above is what that looks like. So
the two collapses are not two endings — one is where RSI begins, and the other
is where research stops. Only the second is an ending, and even it is not the
ending it sounds like:

#### A field's research ends. Its usefulness does not.

**Classical physics is not worth researching and is holding up every bridge.**
That is the normal fate of a finished field, not a sad one, and a design that
retired a field's *solutions* along with its *frontier* would be throwing away
the only thing the research was for.

So when a field collapses either way, three things survive it, and the machine
already has the shape for each:

| what survives | how | why it must |
|---|---|---|
| **its solutions** | the L4 entries stay in the registry, installable and runnable | a method that works does not stop working because nobody is publishing about it |
| **its tools** | the market listings stay installable, and other fields' agents plug them in | a tool everyone's agents use is worth as much as an agent — that is why §11 pays for tools at all |
| **its author's share** | the 5% slice keeps paying on every run that uses it | the author did the work of writing it, and a field going quiet is not them being unwritten |

And the agent goes **out of research routing while staying usable** — which is
exactly `retired`, the thing this machine already does to an agent it no longer
hands new work: *out of routing, still readable, and its folder is the record of
what it did.* A collapsed field's agent is retired from **research**, not from
**service**. It still answers, still runs its solutions, still earns for its
author; it just stops being asked what to solve next.

> **The daily-life half is the point.** The reason to build a field's solutions
> as installable listings rather than as papers is that a finished field's
> output should reach someone who has a problem, without them caring that the
> frontier closed. A reconstruction that denoises a scan is worth the same on
> the day its field stops publishing as it was the day before.


The honest handling is the same for both: **a field that no human verifies is a
field whose page says so.** Not a hidden state — the agent's public page carries
the last time a person checked one of its results, and how long the chain of
agent-only verification has run since. A reader deciding whether to trust the
field can then see the one thing that decides it.

That page carries one more line once a field has collapsed: **what of it is
still in service.** A reader who does not care about the frontier still needs to
know whether the solution they are about to install is maintained, or is a
finished thing that works and will not change again. Both are fine answers; not
saying which is not.

**And a field ends by splitting, which is the good ending.** When a small
sub-scope keeps producing results with more energy and meaning than the field
around it, that is not a sub-topic — it is a new field, and it gets **its own
research agent, its own page, its own problem list in its own order.** Classical
physics did not absorb quantum mechanics; quantum mechanics left. The registry
already supports this: the new field's L1 principle is a new entry, not an
amendment, and the old field's agent keeps its history exactly as a retired
agent does.

> **What is built, and what is not.** The two functions, the switch, the three
> ledgers, the self-model as a queue, the domain-verifier socket and the
> propose/hold/sign RSI loop are built. **The page, the ordered problem list,
> the teacher sub-agent, the agent-only verification chain and the field-split
> mechanism are design.** The last two are the ones to be slowest about: they
> are where a system that has spent this much effort on *not reporting what it
> did not check* would be able to stop checking.

### The governor's research agents (Points 6 and 12)

Some ship from the governor rather than from a user. These are the seed of the
market, written where the domain knowledge is:

| Agent | Domain |
|---|---|
| **low-dose CT** | reconstruction at doses below what a classical pipeline can use |
| **computational imaging** | the broader inverse-problem family — snapshot compressive imaging, coded aperture |
| **medical physics** | treatment planning and QA, as clinical radiotherapy practice does it |
| **pill-camera** | capsule endoscopy — reading video no clinician has time to read whole |
| **drug design** | docking, screening, and the loop from candidate to assay |

Each has its own design — charter, self-model dimensions, the substrates it may
improve and the three it may never touch, and the budget its autonomous function
runs under: [`research-agents/`](research-agents/README.md).

> **They are agents, not exceptions.** Governor-authored means reviewed by the
> same acceptance, installed by the same screen, bounded by the same ceiling, and
> judged by the same verifier. The one thing being the governor's buys is being
> written at all.

**They are also where the token flows.** These agents are heavy users of an LLM,
and they run against the exchange node — so their consumption is what pays the
PWM that reaches the people supplying it. A user who runs the exchange node earns
from work like this being done, which is why the seed agents are compute-hungry
research rather than something cheap.

## 12. Self-awareness and RSI

Every agent carries a self-model, and the contract is four refusals: every line
observed, unmeasured reported as unmeasured, the limits line always present, and
**no path from reading to authority**.

RSI is **propose → the owner signs → adopt**. A candidate must cite the
measurement that justifies it, or it is a preference with a version number
attached. When no metric supports a change, an honest no-change candidate is the
correct output. An agent cannot sign its own candidate, cannot raise its own
ceiling, and cannot promote a vault policy from per-use to standing — **a high
ceiling is permission to act, never permission to become more permitted.**

## 13. What runs it costs (Points 2, 3 and 4)

Every run has a **metered cost**: the provider's reported usage, priced at the
provider's rate. Not an estimate, and not a number the agent reports about
itself.

| Share | Goes to |
|---|---|
| **10%** | the PWM treasury pool |
| **0–5%** | the agent's author, at the fraction of the slice they chose |
| the rest | the LLM provider |

> **Built, as an accounting.** `sarsi earned` reports what each run owes and
> to whom, from the metered cost — treasury, author, provider — with the
> author's share taken **out of the provider's**, not the treasury's and not
> added on top: the user pays the same either way and what changes is who the
> rest of it reaches. `price_share` is a fraction OF the 5%, so 1.0 is five per
> cent of the run and not all of it, and it is clamped here as well as refused
> at install because this arithmetic should not depend on a different program
> having run.
>
> **It moves nothing, and there is no function in it that could.** The line is
> the one the compute design already drew — *the CLI attributes, the platform
> settles* — and it is right for the same reason: a machine that works out what
> is owed is safe to leave running unattended; one that can move balances
> unattended is a different risk. A test asserts the module has no `transfer`,
> `pay`, `settle`, `mint` or `sell`.
>
> Two rules do the load-bearing work. **The shares are exhaustive** — the
> provider takes the *remainder*, not a fourth percentage, because
> independently-rounded shares do not add up and the gap goes somewhere every
> run. And **unknown is not zero**: a run whose cost could not be metered
> records *nothing*, never a `0` row, because a fee ledger writing zero would
> quietly assert *this owed nothing*. The unmeasured runs are counted and
> reported, so a total is never mistaken for complete.
>
> **Bring your own key is priced.** A Claude Code session is exactly that case
> and the economy saw nothing of it: `spend` reads its tokens and reports *PWM:
> not charged here*, which is true — the owner paid Anthropic, or it came out of
> a subscription — and `earnings` recorded the run as unmeasured. Those are two
> different numbers and conflating them cost the fee: what the run **cost** in
> PWM is nothing; what it **owes** is 10% of its value at the ratio, which
> applies on your own key by design, or every run would be free by bringing one.
>
> So a BYO run owes the treasury and the author, and the provider is **not owed
> here** — the API bill already paid them, and recording it as owed would
> double-count something the owner has settled. The remainder is `paid_outside`,
> named so the whole value is accounted for without the provider's part reading
> as a debt this machine holds.
>
> **The cache rate is the whole correctness of it.** A live session on grace ran
> 1,006 fresh input tokens against 8,201,359 cached; pricing cache at the input
> rate would inflate its value — and the fee — by orders of magnitude. Cache
> read and write are multiples of the input price rather than a second table
> that would drift from the first. An unknown model returns `known_model:
> False`, because a price from the fallback is a guess and a fee built on a
> guess should be able to say so.

> **The exchange node is built too** — `sarsi exchange start --budget-pwm N` ·
> `status` · `stop`. Three of its four properties are refusals, which is the
> right proportion for a thing that runs on the owner's machine to make money:
>
> * **it is not a worker**, and that is the invariant *the agent you talk to
>   does not execute* with a sibling — **the thing that earns does not work for
>   you**. `workers()` does not offer it, `admit` refuses it and `assign` will
>   not drive a session for it. It has its **own role**, deliberately: sharing
>   the worker role would leave it one rename from being handed a task.
> * **it holds no task list** — asking raises rather than returning `[]`,
>   because an empty list is a thing something can fill.
> * **it is bounded.** It will not start without a budget the owner set, and it
>   stops at it. It also refuses to record supply while stopped, so the ledger
>   cannot grow for a node the owner turned off.
> * **it is visible**, in the listing the owner already reads, so a machine
>   that is earning never looks like one that is idle. `status` tells *"never
>   started"* apart from *"started and stopped"* — the second has earnings
>   behind it.
>
> **The starting balance is built** — `sarsi balance` · `--grant`. It was held
> back on the grounds that it *holds a balance*, and that reasoning was half
> right. The half it got wrong is the design: **what made a balance dangerous
> was that it could MOVE.** This one cannot. It is granted once, spent only
> *down*, and only on a fee this machine already computes — so it is not money
> in custody, it is a fee credit that can only be destroyed.
>
> * **no function moves it.** Not "not implemented" — absent, and a test fails
>   if a `transfer`, `sell`, `withdraw`, `convert` or `redeem` ever appears.
> * **granted once.** One that could be topped up on request is an infinite
>   one, and every fee after the first would be free.
> * **never negative.** Spending more than is there is refused, not overdrawn:
>   an overdraft is a loan, and a loan is the custody question coming back in
>   through the side.
> * **a debit names its fee.** A spend with nothing behind it is this balance
>   being used as money, which is the one thing it is not.
> * **it does not erase the fee.** The treasury is owed exactly what it was
>   owed; the two ledgers stay apart because they have to be able to disagree,
>   or an unpaid fee and a paid one would read the same.
>
> Its kind is printed every time it is read, not only when granted — a figure
> whose kind is stated once is a figure somebody later adds to another one.

**A run on ai4science pays no platform share.** That is the difference this
product is: the app adds a manager and a front door and charges for them, and
none of that is needed here.

**Bring your own key.** A user may use their own API key or subscription; the
10% still applies, computed at the PWM/token ratio. Everyone starts with a small
**non-exchangeable** balance to pay it — spendable on fees, never sellable, and
visibly distinct so it cannot leak into the exchangeable supply. When it runs
short, an **exchange node** starts: visible, bounded by a budget the owner sets,
and **never touching the owner's tasks** — it is not a worker, holds no task
list, and may not drive a session. With enough PWM the owner may stop it.

### Your own key, run freely, and earn (Point 5)

Put together, the point of the last two paragraphs is one thing a user cares
about:

| | |
|---|---|
| **you may run on your own key or subscription** | ai4science does not resell you an LLM |
| **the only charge is the 10% fee** | computed at the PWM/token ratio, paid in PWM, not in your provider's currency |
| **the fee need never block you** | the bootstrap balance covers the start; the exchange node covers it after |
| **and the node earns** | supplying capacity to other people's runs is what pays it, so a machine that is already on can more than cover its own fees |
| **and you may stop it** | with enough PWM, the node is turned off and stays off |

So a user with their own key runs ai4science continuously without a bill from
us, and a user who leaves the node on is on the earning side of the same ledger.
Neither is a discount granted by anyone — it is what the 10% fee and the node
add up to.

> **Money buys nothing that matters.** Not a ceiling, not a gate, not a verdict,
> not a position in agents-search. A paid run that failed, failed.

## 14. What this does not do

- **No second machine.** No placement decision, no cross-host fold, no
  contradiction to resolve. Those are deleted rather than stubbed, because a stub
  that always answers the same way reads as a working mechanism.
- **No manager.** Routing across agents beyond this machine is the app's job.
- **No agent starts work on its own.** `start` is the owner's opt-in, and it is
  the only thing separating *"I asked a question"* from *"I authorised work"*.
- **No auto-approval of gates**, at any ceiling, for any agent, ever. The one
  narrow exception is a *delete* the plan declared, confined to the declared
  working directory, in a command that does nothing else, when the owner has
  granted it — and the command that prompted the exception still stops, because
  it chained the delete to running a script.
- **The loop drives only what it can read.** Its gate detection, stranded-prompt
  reading and busy marker are tuned to Claude Code's TUI. An agent whose spec
  runs a different interface — `social`, `funding`, `jobs`, `abraham` — is
  started and reported **attended**, and the loop will not type at it.

  > This was a *reported* limit before it was an *enforced* one, and the gap cost
  > a session. The loop typed a brief into an attended session three times; the
  > interface underneath was a menu where `j` and `k` move the selection, the
  > cursor walked onto **"No, exit"**, and the session it was supervising died.
  > Blind keystrokes at an unknown screen are not a brief — they are input to
  > whatever menu happens to be showing, and one option is always the worst one.
  >
  > That guard was then on **one** of the seven paths that type at a session.
  > A later live run found `retry` typing a paragraph at an attended TUI, and
  > `check` doing the same one command earlier — harmless only because that
  > session happened to be at its prompt rather than on the trust menu it had
  > been showing minutes before. The refusal now sits at every one of them, and
  > `by_owner` is not an exemption: the owner's words are keystrokes too, and
  > two of the paths are the owner by definition.

  **Not driving one is not the same as not measuring one.** `blast` and `spend`
  were written against Claude Code's transcript, so for three live runs in a row
  they answered *"the transcript could not be read"* and *"tokens: not
  recorded"* for over half the fleet — honest, and useless. An attended session
  keeps its own books: the harness persists its tool calls per workspace, and
  the meter prices every call it makes. Both readers read those now, and the
  step ceiling, which counts through the same records, binds on attended agents
  in consequence. What did **not** change is the rule underneath: no record
  still *raises*, because "we have no idea" must never be reported as "it
  touched nothing and cost nothing".

## 15. What it owes

1. **Telegram has never carried a message.** The code exists; *"one agent, two
   doors"* is proven in tests only.
2. **The vault has never carried live traffic.** No real credential has been
   asked for through it.
3. **The outward gate has never held a real act.**
4. **Evidence can only keep what it was shown.** Output that scrolled past the
   terminal's history before the first capture is gone. It is also *bounded by a
   declaration*: it reads the plan's working directory, so a session that writes
   somewhere the plan never named produces a verdict of `UNVERIFIED` rather than
   a wrong one.
5. **Two thirds of what a session does names no file.** `blast` reports what was
   written from `Write` and `Edit` records; `Bash` says only that it ran. So
   "nothing observed outside the declared paths" is exactly that, and the count
   of unchecked commands is printed beside it rather than rounded away.
6. **One agent's loop must not take the daemon down.** One process now hosts
   every agent, which trades an address space for a discipline, and nothing
   checks that a raise in one agent's turn is contained.
7. **Nothing in §11 or §13 is built.** The loop underneath them is.
