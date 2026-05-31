import base64
from pathlib import Path
from ai4science.harness.events import ImagePart, Message, load_image


def test_message_images_default():
    m = Message(role="user", content="hi")
    assert m.images == []


def test_image_part_fields():
    p = ImagePart(media_type="image/png", data_b64="AAAA")
    assert p.media_type == "image/png" and p.data_b64 == "AAAA"


def test_load_image(tmp_path):
    img = tmp_path / "x.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    part = load_image(img)
    assert part.media_type == "image/png"
    assert base64.b64decode(part.data_b64) == b"\x89PNG\r\n\x1a\n"


def test_session_run_turn_attaches_images(tmp_path):
    from ai4science.harness.session import AgentSession
    from ai4science.harness.adapters.stub import StubAdapter
    from ai4science.harness.events import TextDelta, Done
    sess = AgentSession(adapter=StubAdapter([[TextDelta("ok"), Done("end")]]),
                        model="stub", backend="anthropic", workspace=tmp_path,
                        read_only=True, auto_yes=False, on_text=lambda t: None, meter=lambda u: None)
    sess.run_turn("look", images=[ImagePart("image/png", "AAAA")])
    user = [m for m in sess.history if m.role == "user"][0]
    assert user.images and user.images[0].data_b64 == "AAAA"
