from __future__ import annotations


class dot:
    """Recursive attribute view over JSON (dict/list); missing attr -> None."""
    def __init__(self, data):
        self._d = data

    def __getattr__(self, name):
        if name == "_d":
            raise AttributeError(name)
        d = object.__getattribute__(self, "_d")
        if isinstance(d, dict):
            v = d.get(name)
            return dot(v) if isinstance(v, (dict, list)) else v
        return None

    def __getitem__(self, i):
        d = object.__getattribute__(self, "_d")
        v = d[i]
        return dot(v) if isinstance(v, (dict, list)) else v

    def __iter__(self):
        d = object.__getattribute__(self, "_d")
        if isinstance(d, list):
            for v in d:
                yield dot(v) if isinstance(v, (dict, list)) else v

    def __bool__(self):
        return bool(object.__getattribute__(self, "_d"))

    def unwrap(self):
        """The underlying raw JSON value (dict/list), for passthrough echoing."""
        return object.__getattribute__(self, "_d")
