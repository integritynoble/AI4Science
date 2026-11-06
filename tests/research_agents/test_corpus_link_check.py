"""Offline checks for the non-downloading corpus link checker."""
from __future__ import annotations

from email.message import Message
from urllib.error import HTTPError, URLError

from tools import check_corpus_links as checker


class FakeResponse:
    status = 200

    def __init__(self, length="123", url="https://example.test/data"):
        self.headers = Message()
        if length is not None:
            self.headers["Content-Length"] = str(length)
        self.url = url
        self.reads = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.url

    def read(self, amount=-1):
        self.reads.append(amount)
        return b"x"[:amount]


def reset_rate_limit(monkeypatch):
    monkeypatch.setattr(checker, "_last_request", 0.0)
    monkeypatch.setattr(checker.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(checker.time, "sleep", lambda _seconds: None)


def test_200_uses_head_and_records_content_length(monkeypatch):
    reset_rate_limit(monkeypatch)
    response = FakeResponse("456")
    calls = []
    monkeypatch.setattr(checker.urllib.request, "urlopen",
                        lambda req, timeout: (calls.append(req) or response))

    result = checker.check_url("https://example.test/data")

    assert result.status == 200
    assert result.content_length == 456
    assert calls[0].get_method() == "HEAD"
    assert calls[0].get_header("User-agent") == checker.USER_AGENT
    assert response.reads == []


def test_404_is_reported_without_fallback(monkeypatch):
    reset_rate_limit(monkeypatch)
    calls = []

    def urlopen(req, timeout):
        calls.append(req)
        raise HTTPError(req.full_url, 404, "missing", Message(), None)

    monkeypatch.setattr(checker.urllib.request, "urlopen", urlopen)
    result = checker.check_url("https://example.test/missing")

    assert result.status == 404
    assert len(calls) == 1
    assert calls[0].get_method() == "HEAD"


def test_refused_head_falls_back_to_one_byte_range(monkeypatch):
    reset_rate_limit(monkeypatch)
    calls = []
    response = FakeResponse("789")

    def urlopen(req, timeout):
        calls.append(req)
        if req.get_method() == "HEAD":
            raise HTTPError(req.full_url, 405, "refused", Message(), None)
        return response

    monkeypatch.setattr(checker.urllib.request, "urlopen", urlopen)
    result = checker.check_url("https://example.test/data")

    assert result.status == 200
    assert len(calls) == 2
    assert calls[0].get_method() == "HEAD"
    assert calls[1].get_method() == "GET"
    assert calls[1].get_header("Range") == "bytes=0-0"
    assert response.reads == [1]


def test_timeout_is_returned_as_error(monkeypatch):
    reset_rate_limit(monkeypatch)

    def urlopen(_req, timeout):
        raise URLError(TimeoutError("probe timed out"))

    monkeypatch.setattr(checker.urllib.request, "urlopen", urlopen)
    result = checker.check_url("https://example.test/slow")

    assert result.status is None
    assert "TimeoutError" in result.error


def test_size_mismatch_is_flagged():
    assert checker._size_mismatch(3_000_000, "~1 MB")
    assert not checker._size_mismatch(1_100_000, "~1 MB")


def test_corpus_static_metadata_is_consistent():
    assert checker._static_errors() == []
