"""One-shot bounded extractor. Input is untrusted; stdout contains status only."""

from __future__ import annotations

import csv
import hashlib
from email import policy
from email.parser import BytesParser
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


MAX_INPUT = 64 * 1024 * 1024
MAX_OUTPUT = 32 * 1024 * 1024
MAX_ELEMENTS = 10_000
MAX_ELEMENT_CHARS = 4_000
MAX_PART = 8 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 2_000
MAX_EMAIL_PARTS = 5_000
MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class ExtractionFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Writer:
    def __init__(self, target: Path) -> None:
        self.stream = target.open("xb")
        self.elements = 0
        self.bytes = 0
        self.partial = False

    def add(self, text: str, kind: str, locator: str) -> None:
        value = text.strip()
        if not value:
            return
        if self.elements >= MAX_ELEMENTS or len(value) > MAX_ELEMENT_CHARS:
            raise ExtractionFailure("CONTENT_ELEMENT_LIMIT")
        raw = (json.dumps({"text": value, "locator_kind": kind,
                           "locator_value": locator}, ensure_ascii=False) + "\n").encode("utf-8")
        if self.bytes + len(raw) > MAX_OUTPUT:
            raise ExtractionFailure("CONTENT_OUTPUT_LIMIT")
        self.stream.write(raw)
        self.elements += 1
        self.bytes += len(raw)

    def close(self) -> None:
        self.stream.close()


def _read(path: Path, expected_sha256: str) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_INPUT + 1)
    if len(data) > MAX_INPUT:
        raise ExtractionFailure("CONTENT_INPUT_LIMIT")
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ExtractionFailure("CONTENT_INPUT_CHANGED")
    return data


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-16") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ExtractionFailure("CONTENT_ENCODING_UNSUPPORTED") from exc


def _txt(data: bytes, writer: Writer) -> None:
    for number, line in enumerate(_decode(data).splitlines(), 1):
        writer.add(line, "LINE", str(number))


def _csv(data: bytes, writer: Writer) -> None:
    try:
        reader = csv.reader(_decode(data).splitlines(), strict=True)
        for number, row in enumerate(reader, 1):
            writer.add(" | ".join(row), "CSV_ROW", str(number))
    except csv.Error as exc:
        raise ExtractionFailure("CONTENT_CSV_CORRUPT") from exc


def _eml(data: bytes, writer: Writer) -> None:
    message = BytesParser(policy=policy.default).parsebytes(data)
    for field in ("From", "To", "Cc", "Date", "Subject"):
        value = message.get(field)
        if value is not None:
            writer.add(str(value), "EMAIL_FIELD", field)
    for number, part in enumerate(message.walk(), 1):
        if number > MAX_EMAIL_PARTS:
            raise ExtractionFailure("CONTENT_EMAIL_PART_LIMIT")
        if part.get_content_maintype() == "multipart" or part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() != "text/plain":
            continue
        try:
            body = part.get_content()
        except (LookupError, UnicodeError, ValueError):
            writer.partial = True
            continue
        for line_number, line in enumerate(str(body).splitlines(), 1):
            writer.add(line, "EMAIL_FIELD", f"body:{number}:{line_number}")


def _xml_part(archive: ZipFile, name: str) -> ET.Element:
    try:
        with archive.open(name) as stream:
            data = stream.read(MAX_PART + 1)
    except KeyError as exc:
        raise ExtractionFailure("CONTENT_XLSX_CORRUPT") from exc
    if len(data) > MAX_PART:
        raise ExtractionFailure("CONTENT_XLSX_PART_LIMIT")
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ExtractionFailure("CONTENT_XLSX_UNSAFE_XML")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ExtractionFailure("CONTENT_XLSX_CORRUPT") from exc


def _xlsx(data: bytes, writer: Writer) -> None:
    from io import BytesIO
    try:
        with ZipFile(BytesIO(data)) as archive:
            names = set(archive.namelist())
            if len(names) > MAX_ARCHIVE_ENTRIES:
                raise ExtractionFailure("CONTENT_XLSX_ENTRY_LIMIT")
            workbook = _xml_part(archive, "xl/workbook.xml")
            relationships = _xml_part(archive, "xl/_rels/workbook.xml.rels")
            targets = {element.get("Id"): element.get("Target")
                       for element in relationships.findall(f"{PKG_NS}Relationship")}
            shared = []
            if "xl/sharedStrings.xml" in names:
                strings = _xml_part(archive, "xl/sharedStrings.xml")
                for item in strings.findall(f"{MAIN_NS}si"):
                    shared.append("".join(node.text or "" for node in item.iter(f"{MAIN_NS}t")))
            for sheet in workbook.findall(f"{MAIN_NS}sheets/{MAIN_NS}sheet"):
                title = sheet.get("name") or "Sheet"
                rid = sheet.get(f"{REL_NS}id")
                target = targets.get(rid)
                if not target:
                    raise ExtractionFailure("CONTENT_XLSX_CORRUPT")
                name = target.lstrip("/") if target.startswith("/") else "xl/" + target
                from posixpath import normpath
                name = normpath(name)
                if not name.startswith("xl/") or name not in names:
                    raise ExtractionFailure("CONTENT_XLSX_CORRUPT")
                root = _xml_part(archive, name)
                for cell in root.iter(f"{MAIN_NS}c"):
                    address = cell.get("r") or "?"
                    kind = cell.get("t")
                    raw = cell.findtext(f"{MAIN_NS}v")
                    if kind == "inlineStr":
                        value = "".join(node.text or "" for node in cell.iter(f"{MAIN_NS}t"))
                    elif kind == "s" and raw is not None:
                        try:
                            value = shared[int(raw)]
                        except (ValueError, IndexError) as exc:
                            raise ExtractionFailure("CONTENT_XLSX_CORRUPT") from exc
                    else:
                        value = raw or ""
                    writer.add(value, "SHEET_CELL", f"{title}!{address}")
    except (BadZipFile, OSError) as exc:
        raise ExtractionFailure("CONTENT_XLSX_CORRUPT") from exc


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        return 2
    source, format_name, target, expected_sha256 = Path(argv[1]), argv[2], Path(argv[3]), argv[4]
    writer = None
    try:
        data = _read(source, expected_sha256)
        writer = Writer(target)
        {"txt": _txt, "csv": _csv, "eml": _eml, "xlsx": _xlsx}[format_name](data, writer)
        print(json.dumps({"status": "PARTIAL" if writer.partial else "SUCCEEDED",
                          "elements": writer.elements}))
        return 0
    except KeyError:
        print(json.dumps({"status": "UNSUPPORTED", "code": "CONTENT_FORMAT_UNSUPPORTED"}))
        return 3
    except ExtractionFailure as exc:
        print(json.dumps({"status": "FAILED", "code": exc.code}))
        return 4
    except Exception:
        print(json.dumps({"status": "FAILED", "code": "CONTENT_EXTRACTOR_CRASH"}))
        return 5
    finally:
        if writer is not None:
            writer.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
