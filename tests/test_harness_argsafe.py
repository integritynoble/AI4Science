from ai4science.harness.adapters._argsafe import loads_lenient


def test_valid_json():
    assert loads_lenient('{"path": "a.py"}') == {"path": "a.py"}


def test_empty_returns_empty_dict():
    assert loads_lenient("") == {}
    assert loads_lenient("   ") == {}


def test_extra_data_salvages_first_object():
    # Gemini openai-compat sometimes doubles the arguments payload.
    assert loads_lenient('{"path": "a.py"}{"path": "a.py"}') == {"path": "a.py"}


def test_garbage_returns_empty_dict():
    assert loads_lenient("not json at all") == {}


def test_non_object_json_returns_empty_dict():
    assert loads_lenient("[1, 2, 3]") == {}
    assert loads_lenient('"a string"') == {}
