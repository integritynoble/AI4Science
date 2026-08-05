"""The exchange node exchanges compute, not only credentials — and a machine
that offers compute has to say what kind of machine it is.

Registration today takes `--kind gpu` and believes it. That is enough while the
only providers are the founder's own two boxes, and wrong the moment anyone else
joins, for two reasons that are not the same:

  * **the OS is a routing constraint, not a label.** A solver built against
    CUDA on Linux does not run on Windows, and neither runs on Apple Silicon.
    Dispatching to a provider whose OS the job cannot use burns the user's PWM
    and the provider's wall-clock and produces nothing. The owner runs Windows
    *and* Linux, so this is not hypothetical here.
  * **the GPU is a fact about the machine, so the machine should answer.** A
    provider who types `--kind gpu` on a box with no GPU is not lying — they are
    guessing, and the first heavy job (a computational-imaging reconstruction,
    the kind that needs this at all) is where the guess is discovered.

So the host is **declared first, detected second**:

  * the OS is **declared** and validated against a closed set. It is not sniffed
    from the registering process, because `join` may be run from WSL, a
    container, or over SSH, and the machine that serves is the one that matters.
  * the GPU is **detected** on that declared OS, and detection that finds
    nothing says *unknown*, never *none* — the same rule the rest of this system
    follows about what was not observed.
"""
import pytest

from ai4science.compute import host


# ── the OS is declared, and only these three ──────────────────────────

def test_the_three_the_system_supports():
    assert set(host.SYSTEMS) == {"linux", "windows", "macos"}


def test_a_system_it_does_not_know_is_refused_by_name():
    with pytest.raises(ValueError, match="freebsd"):
        host.normalise_system("freebsd")


def test_the_common_spellings_resolve():
    """Providers type what their machine calls itself."""
    for said, meant in (("Linux", "linux"), ("win", "windows"),
                        ("Windows", "windows"), ("darwin", "macos"),
                        ("mac", "macos"), ("osx", "macos")):
        assert host.normalise_system(said) == meant


def test_it_is_not_sniffed_from_the_registering_process():
    """`join` may be run from WSL, a container, or over SSH. The machine that
    serves the job is the one that matters, and only the provider knows which
    that is."""
    with pytest.raises(ValueError, match="which system"):
        host.normalise_system("")


# ── the GPU is detected, on the OS that was declared ──────────────────

def _nvidia(out):
    return lambda cmd, **kw: out if cmd[0] == "nvidia-smi" else None


def test_a_declared_linux_box_is_asked_nvidia_smi():
    got = host.detect_gpu("linux", run=_nvidia("NVIDIA A100-SXM4-40GB, 40960 MiB, 12.7"))
    assert got.present is True
    assert "A100" in got.device
    assert got.memory_mb == 40960
    assert got.cuda == "12.7"


def test_windows_is_asked_the_same_way():
    """`nvidia-smi` ships with the Windows driver too, and is on PATH."""
    got = host.detect_gpu("windows", run=_nvidia("NVIDIA GeForce RTX 4090, 24564 MiB, 12.4"))
    assert got.present is True and "4090" in got.device


def test_a_mac_is_not_asked_about_cuda():
    """There is no CUDA on Apple Silicon. Asking and getting nothing back would
    record `unknown` on a machine whose accelerator we could have named."""
    got = host.detect_gpu("macos", run=lambda cmd, **kw: "Apple M3 Max")
    assert got.present is True
    assert got.backend == "metal" and got.cuda is None


def test_a_box_with_no_gpu_says_so():
    got = host.detect_gpu("linux", run=lambda cmd, **kw: None)
    assert got.present is False


def test_detection_that_could_not_run_is_unknown_not_none(monkeypatch):
    """Not-observed is not the same as not-there. A provider whose detection
    failed must not be advertised as a CPU-only box — the user picking a
    provider would read that as a checked fact."""
    def explode(cmd, **kw):
        raise OSError("nvidia-smi: permission denied")
    got = host.detect_gpu("linux", run=explode)
    assert got.present is None            # not False
    assert "could not" in got.note.lower()


# ── what registration records ─────────────────────────────────────────

def test_the_record_carries_both(monkeypatch):
    got = host.detect_gpu("linux", run=_nvidia("NVIDIA A100-SXM4-40GB, 40960 MiB, 12.7"))
    cap = host.capability("linux", got)
    assert cap["system"] == "linux"
    assert cap["device"] == "NVIDIA A100-SXM4-40GB"
    assert cap["detected"] is True


def test_an_undetected_gpu_is_recorded_as_undetected(monkeypatch):
    got = host.detect_gpu("linux", run=lambda cmd, **kw: None)
    cap = host.capability("linux", got)
    assert cap["detected"] is False
    assert cap["system"] == "linux"


def test_claiming_a_gpu_the_machine_does_not_have_is_caught():
    """The point of detecting at all: the mismatch is found at registration,
    not by the first heavy job."""
    absent = host.detect_gpu("linux", run=lambda cmd, **kw: None)
    with pytest.raises(host.NoSuchHardware, match="no GPU"):
        host.check_claim("gpu", absent)


def test_but_a_detection_that_failed_does_not_block_registration():
    """Refusing here would make an unreadable driver look like a missing card,
    and lock out a real provider on the strength of something never observed."""
    unknown = host.detect_gpu("linux", run=lambda cmd, **kw: (_ for _ in ()).throw(OSError("x")))
    host.check_claim("gpu", unknown)      # does not raise


def test_offering_cpu_is_never_blocked():
    absent = host.detect_gpu("linux", run=lambda cmd, **kw: None)
    host.check_claim("cpu", absent)
