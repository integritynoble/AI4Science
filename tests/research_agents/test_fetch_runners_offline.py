"""Offline unit tests for the real-corpus fetch helpers."""
from __future__ import annotations

import json
import math
import socket
import urllib.error
from unittest.mock import Mock

import pytest

from ai4science.harness.agents.research_agents.runners import corpus
from ai4science.harness.agents.research_agents.runners.fetch import __main__
from ai4science.harness.agents.research_agents.runners.fetch import runners


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network access is forbidden in fetch tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(runners, "_get", blocked)
    monkeypatch.setattr(runners, "_open_stream", blocked)
    monkeypatch.setattr(runners, "_tcia", blocked)


@pytest.mark.parametrize("value", ["", "   ", "NA", "na", "NaN", "NULL"])
def test_to_float_missing_values_are_nan(value):
    assert math.isnan(runners._to_float(value))


@pytest.mark.parametrize(("value", "expected"), [("\"0.25\"", 0.25), ("0.75", 0.75)])
def test_to_float_parses_quoted_and_plain_numbers(value, expected):
    assert runners._to_float(value) == expected


def test_kbp_sparse_skips_header_and_bad_index_and_fills_empty_values():
    volume = runners._kbp_sparse("index,value\nnot-an-index,9\n7,\n9,2.5\n")

    assert volume.shape == (128, 128, 128)
    assert volume.flat[7] == 1.0
    assert volume.flat[9] == 2.5
    assert volume.flat[0] == 0.0


def test_dude_smiles_retries_503_then_returns_smiles(monkeypatch):
    unavailable = urllib.error.HTTPError("", 503, "busy", {}, None)
    get = Mock()
    monkeypatch.setattr(runners, "_get", get)
    get.side_effect = [unavailable, "CCO ethanol\n\nN#N nitrogen\n"]
    sleep = Mock()
    monkeypatch.setattr(runners.time, "sleep", sleep)

    assert runners._dude_smiles("ampc", "active") == ["CCO", "N#N"]
    assert get.call_count == 2
    sleep.assert_called_once_with(3)


def test_dude_smiles_gives_up_after_tries(monkeypatch):
    get = Mock(side_effect=urllib.error.URLError("offline"))
    monkeypatch.setattr(runners, "_get", get)
    sleep = Mock()
    monkeypatch.setattr(runners.time, "sleep", sleep)

    with pytest.raises(RuntimeError, match="after 4 tries"):
        runners._dude_smiles("ampc", "decoy")
    assert get.call_count == 4
    assert sleep.call_count == 4


@pytest.mark.parametrize("args", [[], ["--status"]])
def test_main_status_returns_zero(args, capsys):
    assert __main__.main(args) == 0
    assert "tcga-survival" in capsys.readouterr().out


def test_main_unknown_key_returns_two(capsys):
    assert __main__.main(["not-a-corpus"]) == 2
    assert "unknown corpus" in capsys.readouterr().out


def test_every_corpus_key_resolves_to_its_fetcher():
    for key in corpus.ALL:
        fetcher = getattr(runners, key.replace("-", "_"), None)
        assert callable(fetcher), key
        assert fetcher.__name__ == key.replace("-", "_")


def test_provenance_records_source_and_licence(tmp_path):
    path = runners._provenance(tmp_path, corpus.OPENKBP)

    record = json.loads(path.read_text())
    assert record["source"] == corpus.OPENKBP.source
    assert record["licence"] == corpus.OPENKBP.licence
