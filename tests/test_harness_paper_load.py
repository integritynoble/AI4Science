import subprocess
import pytest
from ai4science.harness import paper_load
from ai4science.harness.paper_load import load_paper, PaperDoc, PaperLoadError, MAX_PAPER_CHARS


def test_markdown_title_from_heading(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# Great Title\n\nAbstract here.\n")
    doc = load_paper(p)
    assert isinstance(doc, PaperDoc)
    assert doc.title == "Great Title"
    assert "Abstract here." in doc.text
    assert doc.fmt == "md"


def test_latex_title(tmp_path):
    p = tmp_path / "a.tex"
    p.write_text(r"\documentclass{article}\title{My Paper}\begin{document}body\end{document}")
    doc = load_paper(p)
    assert doc.title == "My Paper"


def test_txt_title_falls_back_to_first_line(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("First line is the title\nmore text\n")
    doc = load_paper(p)
    assert doc.title == "First line is the title"


def test_missing_file_raises(tmp_path):
    with pytest.raises(PaperLoadError):
        load_paper(tmp_path / "nope.md")


def test_unknown_extension_treated_as_text(tmp_path):
    p = tmp_path / "a.rst"
    p.write_text("Some content\n")
    doc = load_paper(p)
    assert "Some content" in doc.text


def test_truncation_flag(tmp_path):
    p = tmp_path / "big.md"
    p.write_text("# T\n" + ("x" * (MAX_PAPER_CHARS + 100)))
    doc = load_paper(p)
    assert doc.truncated is True
    assert len(doc.text) <= MAX_PAPER_CHARS + 200


def test_pdf_uses_pdftotext(tmp_path, monkeypatch):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    def fake_run(cmd, **kw):
        class R: returncode = 0; stdout = "# PDF Title\nextracted body"
        return R()
    monkeypatch.setattr(paper_load.subprocess, "run", fake_run)
    monkeypatch.setattr(paper_load.shutil, "which", lambda n: "/usr/bin/pdftotext")
    doc = load_paper(p)
    assert doc.title == "PDF Title" and "extracted body" in doc.text


def test_pdf_without_extractor_raises(tmp_path, monkeypatch):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(paper_load.shutil, "which", lambda n: None)
    monkeypatch.setattr(paper_load, "_pypdf_text", lambda path: None)
    with pytest.raises(PaperLoadError) as e:
        load_paper(p)
    assert "pdftotext" in str(e.value).lower() or "pdf" in str(e.value).lower()
