from ai4science.harness import mentions


def test_text_mention_inlined(tmp_path):
    (tmp_path / "note.md").write_text("hello world")
    text, images = mentions.expand("see @note.md please", tmp_path)
    assert "hello world" in text and "note.md" in text
    assert images == []


def test_image_mention_becomes_attachment(tmp_path):
    (tmp_path / "p.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    text, images = mentions.expand("look at @p.png", tmp_path)
    assert len(images) == 1 and images[0].media_type == "image/png"
    assert "[image: p.png]" in text


def test_nonfile_mention_left_alone(tmp_path):
    text, images = mentions.expand("email @someone and @missing.txt", tmp_path)
    assert "@someone" in text and "@missing.txt" in text
    assert images == []


def test_no_mention_passthrough(tmp_path):
    text, images = mentions.expand("just a line", tmp_path)
    assert text == "just a line" and images == []


def test_mention_outside_workspace_not_inlined(tmp_path):
    # a file OUTSIDE the workspace must not be inlined, even though it exists
    outside = tmp_path.parent / "secret_outside.txt"
    outside.write_text("TOP-SECRET")
    ws = tmp_path / "ws"
    ws.mkdir()
    text, images = mentions.expand("read @../secret_outside.txt", ws)
    assert "TOP-SECRET" not in text
    assert "@../secret_outside.txt" in text and images == []


def test_absolute_path_mention_not_inlined(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    text, images = mentions.expand("read @/etc/hostname", ws)
    assert "@/etc/hostname" in text and images == []
