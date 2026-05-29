# Model-selection demo (choose the model like Claude Code)

`ai4science` lets you pick the chat model three ways, and switch it **live**
mid-conversation — the same as Claude Code.

| How | Scope | Example |
|---|---|---|
| `--model` / `-m` flag | whole session | `ai4science --model opus` · `ai4science chat -m sonnet` |
| `AI4SCIENCE_MODEL` env | whole session | `export AI4SCIENCE_MODEL=haiku` then `ai4science` |
| `/model` in-session | pick from a menu, switches live | type `/model`, choose by number (or `/model opus`) |

Names accepted: `opus`, `sonnet`, `haiku`, or a full model id
(e.g. `claude-opus-4-1-20250805`). With no model set, the chat uses your
`claude` CLI's default. The in-session switch uses the Claude Agent SDK's
`set_model` (streaming mode), so the conversation continues uninterrupted.

## Run it

```bash
pip install "pwm-ai4science[claude]"   # + the claude CLI: claude login
bash examples/model_selection/run_demo.sh
```

The script drives the in-session path non-interactively (slash commands only,
no LLM turns), so it's quick and needs no API spend.

## Expected output

```
── Start on --model sonnet, then switch live with /model ──
  model:      sonnet  (/model to change)     ← welcome header
model: sonnet                                ← /model (show)
✓ model → haiku                              ← /model haiku (switch)
model: haiku                                 ← /model (show again)
```

## Verified live switch (real conversation)

A switch mid-conversation, with a real turn before and after, confirms the new
model takes over while history is preserved:

```
> Write a Python one-liner to reverse a string + explain.
  reversed_string = s[::-1]  …                 (model: sonnet)
> /model haiku
  ✓ model → haiku
> What is a closure in Python? One sentence.
  A closure is a function that captures and remembers variables from its
  enclosing scope, even after that scope has finished executing.   (model: haiku)
```

## See also

- In-session, type `/help` for all slash commands (`/model`, `/plan`, `/cost`, …).
- `/model` with no argument prints the active model.
