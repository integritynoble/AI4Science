# A00 model pin — a proposal, not a decision

**For the owner to accept, amend or reject.** A00's exit evidence asks for
"revisions/config identities", and the plan's own wording is *one named model
revision*. This note proposes one, names what the proposal actually costs, and
says where the mechanism cannot give the owner what A00 asks for.

**Proposed pin for the strong profile:** the model revision recorded for the
strong reference is **`claude-opus-5`**, reached through
`claude -p --model claude-opus-5 --output-format json` on this account. The
reference run that produced it cost **$0.0152605, metered by the provider**
(`total_cost_usd`), in 4.53 s wall, for 2 fresh input tokens, 20,743 cached
input tokens and 139 output tokens; the record is sealed as
`f57205cbe5fb0ddd…` in `docs/references/records.jsonl` and scored 3/3 against
the frozen LDCT judging task, negative control included. The basic profile's pin
is **`claude-haiku-4-5-20251001`**, whose reference run cost **$0.0059623**
metered. Both were recorded on 2026-09-22 at 14:11 UTC against task digest
`4a5edb80775f6775…`.

**The caveat that matters more than the string, and the reason this is a proposal
rather than a pin.** `claude-opus-5` is an **alias, not a dated revision**. The
provider's own `modelUsage` block keys the basic run by the dated revision
`claude-haiku-4-5-20251001` but keys the strong run by `claude-opus-5`, whose
`canonicalModel` is the identical string — so this path exposes no dated identity
for Opus 5 at all, and the record says so in `notes.revision_is_dated: false`
rather than dressing an alias up as a revision. Pinning an alias pins nothing
durable: the weights behind it can change while every record still reads
`claude-opus-5`, and A05's "validation against strong reference" would then be
validating against a moving target without any signal that it moved. A second
finding cuts the same way: **one `claude -p --model claude-opus-5` invocation
billed two models**, Opus 5 ($0.0138565) *and* `claude-haiku-4-5-20251001`
($0.001404) for a side call, so "the cost of an Opus call" on this path is a
composite and is stored as one (`per_model_usd`). The owner's decision should
therefore be either (a) accept `claude-opus-5` as the pin *with* the alias
caveat recorded beside it, or (b) require a dated revision, which means obtaining
the identity from a path that reports one — the Anthropic API's response
`model` field rather than the CLI envelope — before A00 is called done.

See `docs/REFERENCE_RECORDS.md` for the mechanism and for why both records are
`status: candidate` rather than `reference`.
