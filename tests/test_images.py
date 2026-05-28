"""Tests for image input (multimodal @mentions)."""
from __future__ import annotations

import base64
from pathlib import Path

import pytest

from ai4science.agents.images import (
    media_type_for, encode_image, build_user_message, MAX_IMAGE_BYTES,
)
from ai4science.agents.mentions import (
    is_image, parse_image_mentions, parse_mentions, expand_mentions_inline,
)

# A minimal valid 1x1 PNG.
_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def _write_png(path: Path):
    path.write_bytes(_PNG_1x1)


# ─── media type + encoding ───────────────────────────────────────────


def test_media_type_for_extensions():
    assert media_type_for(Path("a.png")) == "image/png"
    assert media_type_for(Path("a.jpg")) == "image/jpeg"
    assert media_type_for(Path("a.jpeg")) == "image/jpeg"
    assert media_type_for(Path("a.gif")) == "image/gif"
    assert media_type_for(Path("a.webp")) == "image/webp"


def test_encode_image_roundtrip(tmp_path):
    p = tmp_path / "x.png"
    _write_png(p)
    media_type, b64 = encode_image(p)
    assert media_type == "image/png"
    assert base64.b64decode(b64) == _PNG_1x1


def test_encode_image_rejects_oversize(tmp_path, monkeypatch):
    p = tmp_path / "big.png"
    p.write_bytes(b"\x00" * 16)
    monkeypatch.setattr("ai4science.agents.images.MAX_IMAGE_BYTES", 8)
    with pytest.raises(ValueError, match="too large"):
        encode_image(p)


# ─── build_user_message ──────────────────────────────────────────────


def test_build_user_message_shape(tmp_path):
    p = tmp_path / "recon.png"
    _write_png(p)
    msg = build_user_message("what's wrong here?", [p])
    assert msg["type"] == "user"
    content = msg["message"]["content"]
    assert content[0] == {"type": "text", "text": "what's wrong here?"}
    img = content[1]
    assert img["type"] == "image"
    assert img["source"]["type"] == "base64"
    assert img["source"]["media_type"] == "image/png"


def test_build_user_message_multiple_images(tmp_path):
    a = tmp_path / "a.png"; b = tmp_path / "b.png"
    _write_png(a); _write_png(b)
    msg = build_user_message("compare", [a, b])
    content = msg["message"]["content"]
    assert sum(1 for c in content if c["type"] == "image") == 2


# ─── mentions image classification ───────────────────────────────────


def test_is_image():
    assert is_image(Path("plot.png")) is True
    assert is_image(Path("PLOT.PNG")) is True   # case-insensitive
    assert is_image(Path("spec.md")) is False


def test_parse_image_mentions_only_images(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_png(tmp_path / "recon.png")
    (tmp_path / "spec.md").write_text("---\nx: 1\n---\n")
    imgs = parse_image_mentions("look at @recon.png and @spec.md", tmp_path)
    assert [p.name for p in imgs] == ["recon.png"]


def test_expand_mentions_inline_skips_images(tmp_path):
    """An image @mention must NOT be inlined as (broken) text, but should
    still appear in the returned attachment list."""
    _write_png(tmp_path / "recon.png")
    expanded, attached = expand_mentions_inline("see @recon.png", tmp_path)
    # No 'could not read' garbage; image not inlined as text.
    assert "could not read" not in expanded
    assert "Attached files" not in expanded   # nothing text to inline
    assert [p.name for p in attached] == ["recon.png"]


def test_expand_mentions_inline_mixed(tmp_path):
    """Text file inlined; image listed but not inlined as a fenced block."""
    _write_png(tmp_path / "recon.png")
    (tmp_path / "notes.md").write_text("hello notes")
    expanded, attached = expand_mentions_inline("@notes.md @recon.png", tmp_path)
    assert "hello notes" in expanded                 # text inlined
    assert "### `@notes.md`" in expanded             # text got a fenced block
    assert "### `@recon.png`" not in expanded        # image did NOT
    names = {p.name for p in attached}
    assert names == {"notes.md", "recon.png"}        # both listed
