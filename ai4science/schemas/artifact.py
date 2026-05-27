"""Base artifact type + YAML-front-matter parser.

Every PWM artifact lives in a Markdown file whose top is a YAML
front-matter block (between two ``---`` lines). The body below is
prose; the front matter is the structured spec consumed by validate
and judge.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Optional, Tuple

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ArtifactType(str, Enum):
    PRINCIPLE = "principle"
    SPEC = "spec"
    BENCHMARK = "benchmark"
    SOLUTION = "solution"


class Artifact(BaseModel):
    """Shared base for all four artifact schemas."""
    model_config = ConfigDict(extra="allow")  # subclasses constrain; base is permissive

    artifact_type: ArtifactType = Field(..., description="One of principle/spec/benchmark/solution")
    name: str = Field(..., min_length=2, max_length=300)


def parse_front_matter(path: Path) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
    """Read a Markdown file and return (front_matter_dict, error_message).

    The dict is None and a message is returned when:
      - the file is missing
      - there is no YAML front matter (no leading ``---``)
      - the YAML is malformed

    Otherwise the dict carries every key from the front matter, and
    error_message is None.
    """
    if not path.exists():
        return None, f"file not found: {path}"

    text = path.read_text(encoding="utf-8")
    if not text.lstrip().startswith("---"):
        return None, "no YAML front matter (file must start with `---`)"

    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, "unterminated YAML front matter (need a second `---`)"

    yaml_block = parts[1]
    try:
        data = yaml.safe_load(yaml_block)
    except yaml.YAMLError as e:
        return None, f"YAML parse error: {e}"

    if data is None:
        return None, "empty YAML front matter"
    if not isinstance(data, dict):
        return None, f"YAML front matter must be a mapping, got {type(data).__name__}"

    return data, None
