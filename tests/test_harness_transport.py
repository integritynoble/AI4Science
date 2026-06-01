import io
from ai4science.harness import transport


def test_sse_post_parses_data_lines(monkeypatch):
    body = (b'data: {"a": 1}\n\n'
            b'data: {"a": 2}\n\n'
            b'data: [DONE]\n\n')

    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(transport.urllib.request, "urlopen",
                        lambda req, timeout=None: _Resp(body))
    chunks = list(transport.sse_post("http://x/v1/chat/completions",
                                     {"Authorization": "Bearer k"}, {"stream": True}))
    assert chunks == [{"a": 1}, {"a": 2}]


def test_post_json(monkeypatch):
    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(transport.urllib.request, "urlopen",
                        lambda req, timeout=None: _Resp(b'{"ok": true}'))
    assert transport.post_json("http://x", {}, {})["ok"] is True
