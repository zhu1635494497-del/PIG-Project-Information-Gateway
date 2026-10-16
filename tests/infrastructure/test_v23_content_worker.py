"""Parser boundary tests use only synthetic untrusted bytes."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from pig.infrastructure.content.worker import main


def _invoke(tmp_path: Path, name: str, payload: bytes, fmt: str,
            *, expected_hash: str | None = None) -> tuple[int, str]:
    source = tmp_path / name
    source.write_bytes(payload)
    output = tmp_path / "elements.jsonl"
    code = main(["content-worker", str(source), fmt, str(output),
                 expected_hash or hashlib.sha256(payload).hexdigest()])
    return code, output.read_text("utf-8") if output.exists() else ""


def test_worker_rejects_changed_input(tmp_path: Path, capsys) -> None:
    code, output = _invoke(tmp_path, "brief.txt", b"private body", "txt",
                           expected_hash="0" * 64)
    assert code == 4
    assert output == ""
    assert "private body" not in capsys.readouterr().out


def test_xlsx_rejects_xml_entity_declaration(tmp_path: Path, capsys) -> None:
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("xl/workbook.xml", b"<!DOCTYPE a [<!ENTITY x 'bad'>]><workbook/>")
        archive.writestr("xl/_rels/workbook.xml.rels", b"<Relationships/>")
    code, _ = _invoke(tmp_path, "bad.xlsx", stream.getvalue(), "xlsx")
    assert code == 4
    assert "CONTENT_XLSX_UNSAFE_XML" in capsys.readouterr().out


def test_unknown_format_is_not_a_success(tmp_path: Path, capsys) -> None:
    code, _ = _invoke(tmp_path, "brief.pdf", b"dummy", "pdf")
    assert code == 3
    assert "UNSUPPORTED" in capsys.readouterr().out


def test_eml_unreadable_body_is_partial_not_silent_success(tmp_path: Path, capsys) -> None:
    payload = (b"Subject: synthetic\nContent-Type: text/plain; charset=x-unknown\n"
               b"MIME-Version: 1.0\n\n\xff\xfe\n")
    code, output = _invoke(tmp_path, "mail.eml", payload, "eml")
    assert code == 0
    assert b"synthetic" in output.encode("utf-8")
    assert "PARTIAL" in capsys.readouterr().out
