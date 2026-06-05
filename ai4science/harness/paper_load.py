from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_PAPER_CHARS = 120_000


class PaperLoadError(Exception):
    pass


@dataclass
class PaperDoc:
    title: str
    text: str
    source_path: str
    fmt: str
    truncated: bool = False


def _pypdf_text(path: Path):
    """Optional fallback if pypdf is installed; returns text or None."""
    try:
        import pypdf
    except Exception:
        return None
    try:
        reader = pypdf.PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return None


def _pdf_text(path: Path) -> str:
    exe = shutil.which("pdftotext")
    if exe:
        try:
            r = subprocess.run([exe, str(path), "-"], capture_output=True,
                               text=True, timeout=120)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout
        except Exception:
            pass
    alt = _pypdf_text(path)
    if alt and alt.strip():
        return alt
    raise PaperLoadError(
        "PDF text extraction unavailable: install poppler (pdftotext) or pypdf, "
        "or provide the paper as Markdown/LaTeX.")


def _guess_title(text: str, fmt: str, fallback: str) -> str:
    if fmt == "tex":
        m = re.search(r"\\title\{([^}]*)\}", text)
        if m and m.group(1).strip():
            return m.group(1).strip()
    for line in text.splitlines():
        s = line.strip()
        if fmt in ("md", "pdf") and s.startswith("# "):
            return s[2:].strip()
        if s:
            return s
    return fallback


def load_paper(path: Path) -> PaperDoc:
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise PaperLoadError(f"paper file not found: {path}")
    ext = path.suffix.lower()
    if ext == ".pdf":
        fmt, text = "pdf", _pdf_text(path)
    else:
        fmt = {".md": "md", ".markdown": "md", ".tex": "tex"}.get(ext, "txt")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            raise PaperLoadError(f"could not read {path}: {exc}")
    truncated = False
    if len(text) > MAX_PAPER_CHARS:
        text = text[:MAX_PAPER_CHARS] + "\n\n[...truncated...]"
        truncated = True
    title = _guess_title(text, fmt, path.stem)
    return PaperDoc(title=title, text=text, source_path=str(path), fmt=fmt,
                    truncated=truncated)
