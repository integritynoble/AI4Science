from ai4science.harness.agents.social.mastodon_tools import timeline_command, post_command


def test_timeline_command_shape():
    argv = timeline_command("mastodon.example")
    assert argv[0] == "python3" and argv[1] == "-c"
    assert "/api/v1/timelines/home" in argv[2]
    assert "/run/egress.sock" in argv[2]
    assert "mastodon.example" in argv[2]
    assert "Bearer" not in argv[2] and "token" not in argv[2].lower()   # no secret in the script


def test_post_command_shape():
    argv = post_command("mastodon.example", "hello from the agent")
    assert "/api/v1/statuses" in argv[2]
    assert "hello from the agent" in argv          # text passed as an arg
    assert "Bearer" not in argv[2]
