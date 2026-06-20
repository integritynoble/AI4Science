"""pwm_core namespace (vendored).

This vendored copy ships ``pwm_core.optics`` for the AI4Science harness. Extend
the package ``__path__`` via ``pkgutil`` so sibling ``pwm_core`` source trees on
``sys.path`` (e.g. the editable ``packages/pwm_core`` install that provides
``pwm_core.forward_compiler``, ``pwm_core.physics`` and ``pwm_core.core``) are
merged in rather than shadowed. Purely additive: optics resolution is unchanged.
"""
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
