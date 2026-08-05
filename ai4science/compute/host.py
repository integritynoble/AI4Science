"""What kind of machine is offering compute — declared first, detected second.

The exchange node exchanges GPU compute as well as credentials, and a job sent
to the wrong machine costs the user PWM and the provider wall-clock and returns
nothing. Two facts decide whether a job can land, and they are known in
different ways:

  * **the operating system is DECLARED.** It is a routing constraint — a solver
    built against CUDA on Linux does not run on Windows, and neither runs on
    Apple Silicon. It is not sniffed from the registering process, because
    `join` is run from WSL, from a container, and over SSH, and the machine that
    serves the job is the one that matters. Only the provider knows which that
    is, so the provider says.

  * **the GPU is DETECTED**, on the OS that was declared, because it is a fact
    about the machine and the machine can answer. A provider typing `--kind gpu`
    on a box with no card is not lying, they are guessing — and the first heavy
    job is a bad place to discover it. Research agents that need this at all
    (computational imaging, above everything) are exactly the ones whose jobs
    are expensive to lose.

The one rule that shapes the rest: **detection that could not run reports
`unknown`, never `none`.** A provider whose driver was unreadable must not be
advertised as a CPU-only box, because a user choosing a provider reads that as a
checked fact. Not-observed is not not-there.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

#: The three the system supports. A closed set, because each one implies a
#: different way of asking the machine what it has, and a different set of
#: solvers that will run on it.
SYSTEMS = ("linux", "windows", "macos")

#: What providers actually type. Their machine calls itself one of these.
_SPELLINGS = {
    "linux": "linux", "ubuntu": "linux", "debian": "linux", "wsl": "linux",
    "windows": "windows", "win": "windows", "win32": "windows", "win64": "windows",
    "macos": "macos", "mac": "macos", "osx": "macos", "darwin": "macos",
    "apple": "macos",
}


class NoSuchHardware(Exception):
    """The machine was asked, and does not have what was claimed."""


@dataclass
class Gpu:
    #: True observed present · False observed absent · None NOT OBSERVED.
    #: The third is why this is not a bool.
    present: Optional[bool] = None
    device: str = ""
    memory_mb: Optional[int] = None
    cuda: Optional[str] = None
    #: `cuda` on Linux/Windows, `metal` on macOS. Named because a job's
    #: requirements are written against a backend, not against a card.
    backend: Optional[str] = None
    note: str = ""

    @property
    def summary(self) -> str:
        if self.present is None:
            return self.note or "not observed"
        if not self.present:
            return "no GPU detected"
        parts = [self.device or "GPU"]
        if self.memory_mb:
            parts.append(f"{self.memory_mb} MiB")
        if self.cuda:
            parts.append(f"CUDA {self.cuda}")
        return ", ".join(parts)


def normalise_system(said: str) -> str:
    """The declared OS, or a refusal that names what was said.

    Empty is refused rather than defaulted to this process's platform: a
    default here is a silent guess about a machine we are not running on.
    """
    text = (said or "").strip().lower()
    if not text:
        raise ValueError(
            "say which system the machine that will serve runs — "
            f"one of {', '.join(SYSTEMS)}. It is not read from here, because "
            "this command is run from WSL, from containers and over SSH, and "
            "the box that serves the job is the one a solver has to match")
    got = _SPELLINGS.get(text)
    if got is None:
        raise ValueError(f"unknown system {said!r} — expected one of "
                         f"{', '.join(SYSTEMS)}")
    return got


def _run(cmd, **kw) -> Optional[str]:
    """The real prober. Returns stdout, or None when the tool is absent or
    answered nothing. Raises only for reasons that are NOT "no GPU"."""
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=20, **kw)
    if out.returncode != 0:
        return None
    text = (out.stdout or "").strip()
    return text or None


#: `nvidia-smi` ships with the driver on Linux AND on Windows, and is on PATH
#: on both — one query serves both.
_SMI = ["nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader"]

#: macOS has no CUDA. Asking anyway and getting nothing would record `unknown`
#: about a machine whose accelerator we could have named.
_MAC = ["sysctl", "-n", "machdep.cpu.brand_string"]

_MEM = re.compile(r"(\d+)\s*MiB", re.I)
_CUDA = re.compile(r"(\d+\.\d+)")


def detect_gpu(system: str, *,
               run: Optional[Callable[..., Optional[str]]] = None) -> Gpu:
    """Ask the declared machine what accelerator it has.

    `FileNotFoundError` means the tool is not installed, which on these hosts
    means no NVIDIA driver — that IS an observation of absence. Any other
    failure is not: it is the probe failing, and reports `unknown`.
    """
    probe = run or _run
    system = normalise_system(system)

    if system == "macos":
        try:
            text = probe(_MAC)
        except FileNotFoundError:
            return Gpu(present=None, backend="metal",
                       note="could not ask this machine what it has")
        except Exception as e:
            return Gpu(present=None, backend="metal",
                       note=f"could not read the accelerator: {e}")
        if not text:
            return Gpu(present=False, backend="metal")
        return Gpu(present=True, device=text.strip(), backend="metal")

    try:
        text = probe(_SMI)
    except FileNotFoundError:
        # No driver installed. Absence observed, not merely unseen.
        return Gpu(present=False, backend="cuda",
                   note="nvidia-smi is not installed")
    except Exception as e:
        return Gpu(present=None, backend="cuda",
                   note=f"could not read the GPU: {e}")

    if not text:
        return Gpu(present=False, backend="cuda")

    first = text.strip().splitlines()[0]
    fields = [f.strip() for f in first.split(",")]
    memory = None
    cuda = None
    for f in fields[1:]:
        if memory is None and _MEM.search(f):
            memory = int(_MEM.search(f).group(1))
            continue
        if memory is None and f.isdigit():
            memory = int(f)
            continue
        if cuda is None and _CUDA.search(f):
            cuda = _CUDA.search(f).group(1)
    return Gpu(present=True, device=fields[0], memory_mb=memory, cuda=cuda,
               backend="cuda")


def capability(system: str, gpu: Gpu) -> Dict[str, Any]:
    """What goes into the registry's `gpu_capability`.

    `detected` is recorded separately from `device`: a reader has to be able to
    tell a card the machine reported from one a provider typed in.
    """
    return {
        "system": normalise_system(system),
        "detected": bool(gpu.present),
        "observed": gpu.present is not None,
        "device": gpu.device,
        "memory_mb": gpu.memory_mb,
        "cuda": gpu.cuda,
        "backend": gpu.backend,
        "note": gpu.note,
    }


def check_claim(kind: str, gpu: Gpu) -> None:
    """Refuse `--kind gpu` on a machine that answered "no GPU".

    Only on an OBSERVED absence. A probe that could not run must not lock out a
    real provider on the strength of something never seen — that would make an
    unreadable driver look like a missing card.
    """
    if kind != "gpu":
        return
    if gpu.present is False:
        raise NoSuchHardware(
            f"this machine reports no GPU — {gpu.summary}. Register it with "
            f"`--kind cpu`, or install the driver and join again. Offering GPU "
            f"here would take a user's PWM for a job that cannot run")
