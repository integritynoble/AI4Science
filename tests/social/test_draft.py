from ai4science.harness.agents.social.draft import draft_post


def test_draft_is_deterministic_summary():
    tl = [{"account": {"acct": "alice"}, "content": "hello world"},
          {"account": {"acct": "bob"}, "content": "second post"}]
    d = draft_post(tl)
    assert isinstance(d, str) and len(d) > 0
    assert "2" in d                        # mentions the count
    assert draft_post(tl) == d             # deterministic
    assert draft_post([]) != ""            # handles empty timeline
