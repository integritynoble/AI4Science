# ai4science on one machine — design

**Status: design, 2026-08-04. The agent loop is built and tested; the market and
the token economy are not.**

> **Where this lives.** Written in the singularity repository as
> `docs/specs/2026-08-04-ai4science-one-machine-design.md` and copied here,
> because it describes ai4science and belongs beside the code it describes.
> Two copies diverge; if they do, **this one is the design of record for
> ai4science** and the other should become a pointer.

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

---

## 1. What ai4science is

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
    ├── work             the 9-to-5 job · reads mail, never sends
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

## 4. The entry: the machine agent

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
| **`sarsi-worker`** | any task with no better home | shell, editor, browser | nothing — its work stays here |
| **`work`** | the 9-to-5 job | qupath, matlab, mail.read | **nothing** — it reads mail and drafts; sending is not its act |
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

### `work` — mail is the sharp edge

| It may | It may not |
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

## 9. How the workspaces talk to each other

Every agent has its own workspace and its own history. They still need to share:
`funding` should know the deadline `work` found in a mail, and `jobs` should know
which CV `abraham` filed. The question is how, without dissolving the reason
there are seven of them.

### The four tiers

| Tier | Who sees it | Holds | Written by |
|---|---|---|---|
| **`W_user`** | every agent | who the owner is, standing preferences, the do-not list | the owner |
| **`W_shared`** | every agent that was granted it | published facts — decisions, deadlines, entities, outcomes | any agent, deliberately |
| **`W_name`** | **one agent** | its mission, its plans, its conversation, what it decided and why | itself |
| **`W_host`** | **one agent, one machine** | tools present, paths, sessions, resources | itself |

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

## 10. Both doors

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

## 11. The market

Three kinds of listing — **agents**, **tools**, **sub-agents** — each uploadable,
accepted by the governor, and installable. This is where they live, because an
agent is a thing you install on your own machine and run with your own keys; a
market that lived anywhere else would make using an agent require something else.

Acceptance asks a different question of each: an agent, *what may it do*; a tool,
*what does it touch* — it is closer to the hardware than any agent; a sub-agent,
*does it obey the ceiling and report honestly*. A verifier is the sharpest to
accept, because a lenient one inflates the record of every agent it judges.

**Trust is not transitive.** An agent may bring its own tools — one author, one
review — or require ones from the market, and then the install screen names every
author whose code comes with it and what each part may touch.

## 11a. The tools and sub-agents this system needs

A **tool** is something a task needs *present* to run — checked at `CAP`,
declared per agent as a profile, and refused by name when absent. A **sub-agent**
is something that does the work or judges it, plugging into a socket the runtime
provides.

### Sub-agents

| Sub-agent | Socket | Status |
|---|---|---|
| **`sarsi-claude`** | the session backend — start · send · interrupt · stop · ceiling · has · capture | **built.** The reference implementation, and the shape every other sub-agent matches |
| **the planner** | drafts the seed plan the session then grounds | **built** |
| **the verifier** | given criteria and evidence, answers PASS/FAIL or refuses | **built.** A domain verifier is a market listing |
| **a domain runner** | reconstruction, docking, simulation — work that is not code editing | market |

### Tools the seven need

| Tool | Who | What it touches |
|---|---|---|
| `shell` | `sarsi-worker` | the machine, as the owner |
| `editor` | `sarsi-worker` | files in the task's reach |
| `browser` | `sarsi-worker`, `social`, `funding`, `jobs`, `abraham` | the network, and pages that can lie to it |
| `mail.read` | `work` | the mailbox — **read only; there is no `mail.send`** |
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
| **notification** | the digest and `attention` have no way to reach an owner who is not looking | it can interrupt a person |

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

## 11b. Research agents

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

## 13. What runs it costs

Every run has a **metered cost**: the provider's reported usage, priced at the
provider's rate. Not an estimate, and not a number the agent reports about
itself.

| Share | Goes to |
|---|---|
| **10%** | the PWM treasury pool |
| **0–5%** | the agent's author, at the fraction of the slice they chose |
| the rest | the LLM provider |

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

> **Money buys nothing that matters.** Not a ceiling, not a gate, not a verdict,
> not a position in agents-search. A paid run that failed, failed.

## 14. What this does not do

- **No second machine.** No placement decision, no cross-host fold, no
  contradiction to resolve. Those are deleted rather than stubbed, because a stub
  that always answers the same way reads as a working mechanism.
- **No manager.** Routing across agents beyond this machine is the app's job.
- **No agent starts work on its own.** `start` is the owner's opt-in, and it is
  the only thing separating *"I asked a question"* from *"I authorised work"*.
- **No auto-approval of gates**, at any ceiling, for any agent, ever.

## 15. What it owes

1. **Telegram has never carried a message.** The code exists; *"one agent, two
   doors"* is proven in tests only.
2. **The vault has never carried live traffic.** No real credential has been
   asked for through it.
3. **The outward gate has never held a real act.**
4. **Evidence can only keep what it was shown.** Output that scrolled past the
   terminal's history before the first capture is gone.
5. **One agent's loop must not take the daemon down.** One process now hosts
   every agent, which trades an address space for a discipline, and nothing
   checks that a raise in one agent's turn is contained.
6. **Nothing in §11 or §13 is built.** The loop underneath them is.
