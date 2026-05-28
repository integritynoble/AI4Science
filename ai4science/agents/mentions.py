"""@-mention parsing for prompts.

Users can reference files in the workspace by typing ``@path`` inside a
prompt — e.g.

    ai4science> @code/run_solver.py why does this crash on cube shape (256,256,28)?

The mention is resolved to a path inside the workspace; existing files
become attached context (read-only, like the canonical PWM artifact
files). Non-resolving tokens are left as literal text (they might be
prose like "the @property decorator").

Sandboxing rules (mirror the permission callback):
  - Absolute paths are refused.
  - Anything that resolves outside the workspace is refused (covers
    ``../`` traversal).
  - Directories are skipped (we attach files only).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

# A mention is `@` at a word boundary followed by a path-like token.
# We intentionally avoid matching inside identifiers like `foo@bar.com`
# by requiring the `@` to be preceded by start-of-string or whitespace.
# Path chars: word chars + dot + slash + dash + underscore.
_MENTION_RE = re.compile(r"(?:^|(?<=\s))@([A-Za-z0-9_\-./]+)")

# Per-file budget for inlined contents (matches the agents/_context.py budget).
PER_FILE_CHAR_BUDGET = 8_000


def parse_mentions(text: str, workspace: Path) -> List[Path]:
    """Return the list of files referenced by @mentions that exist inside
    *workspace*. Order preserved; duplicates removed. Returns [] if no
    @mentions resolve to existing files."""
    workspace = workspace.resolve()
    attached: List[Path] = []

    for m in _MENTION_RE.finditer(text):
        token = m.group(1).rstrip(".,;:!?")   # strip trailing punctuation
        if not token:
            continue

        # Reject absolute paths.
        candidate_path = Path(token)
        if candidate_path.is_absolute():
            continue

        # Resolve relative to workspace and confirm it lives inside.
        try:
            resolved = (workspace / candidate_path).resolve()
            resolved.relative_to(workspace)
        except (ValueError, OSError):
            continue

        if not resolved.is_file():
            continue   # silently skip directories / non-existent paths

        if resolved not in attached:
            attached.append(resolved)

    return attached


def expand_mentions_inline(text: str, workspace: Path) -> Tuple[str, List[Path]]:
    """Like ``parse_mentions``, but ALSO returns the prompt with the
    referenced files appended as fenced attachments. Used by chat.py
    where attachments must be embedded in the message that goes to the
    SDK (unlike one-shot mode, which has a separate context-files list).
    """
    attached = parse_mentions(text, workspace)
    if not attached:
        return text, []

    parts = [text, "", "## Attached files (via @mention)"]
    for p in attached:
        rel = p.relative_to(workspace.resolve())
        try:
            body = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            parts.append(f"\n### `@{rel}` (could not read: {e})")
            continue
        if len(body) > PER_FILE_CHAR_BUDGET:
            body = body[:PER_FILE_CHAR_BUDGET] + "\n[... truncated]"
        parts.append(f"\n### `@{rel}`\n```\n{body}\n```")
    return "\n".join(parts), attached
