"""Read text at stable document locations and apply a checked Word edit to a copy."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from pydantic import Field
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from legal_api.db.file_models import StoredFile
from legal_api.files.extract import MAX_BYTES, text_of
from legal_api.files.store import read
from legal_api.workspace.engine import Key, Record

MAX_PAGES = 200
MAX_SHEET_ROWS = 3000
MAX_SHEET_COLS = 60
MAX_TEXT = 24000
WORD_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass(frozen=True)
class Excerpt:
    location: str
    text: str


def _read(file: StoredFile) -> bytes:
    if file.size > MAX_BYTES:
        raise ValueError("Belge okunabilir boyut sınırını aşıyor.")
    raw = read(file)
    if Path(file.name).suffix.lower() in {".docx", ".xlsx", ".udf", ".odt"}:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(entry.file_size for entry in archive.infolist()) > 70 * 1024 * 1024:
                raise ValueError("Belgenin açılmış boyutu fazla büyük.")
    return raw


def excerpt(file: StoredFile, start: int, sheet: str) -> Excerpt:
    raw = _read(file)
    suffix = Path(file.name).suffix.lower()
    if suffix == ".pdf":
        if not 1 <= start <= MAX_PAGES:
            raise ValueError("PDF sayfa numarası sınır dışında.")
        try:
            pdf = PdfReader(io.BytesIO(raw))
            if start > len(pdf.pages):
                raise ValueError("PDF sayfası bulunamadı.")
            return Excerpt(f"s. {start}/{len(pdf.pages)}",
                           (pdf.pages[start - 1].extract_text() or "")[:MAX_TEXT])
        except PyPdfError as exc:
            raise ValueError("PDF metni okunamadı.") from exc
    if suffix == ".xlsx":
        return _sheet(raw, sheet, start)
    if suffix == ".docx":
        doc = Document(io.BytesIO(raw))
        paragraphs = doc.paragraphs[start - 1:start + 19]
        text = "\n".join(f"[{n}] {p.text[:2500]}" for n, p in enumerate(paragraphs, start))
        return Excerpt(f"§ {start}–{start + len(paragraphs) - 1}/{len(doc.paragraphs)}", text)
    lines = text_of(file.name, raw).splitlines()
    selected = lines[start - 1:start + 59]
    return Excerpt(f"satır {start}–{start + len(selected) - 1}/{len(lines)}",
                   "\n".join(f"[{n}] {line[:1500]}" for n, line in enumerate(selected, start))
                   [:MAX_TEXT])


def _sheet(raw: bytes, name: str, start: int) -> Excerpt:
    if not 1 <= start <= MAX_SHEET_ROWS:
        raise ValueError("Excel satır numarası sınır dışında.")
    book = load_workbook(io.BytesIO(raw), read_only=True, data_only=False, keep_links=False)
    try:
        if not name:
            return Excerpt("sayfalar", "\n".join(book.sheetnames))
        if name not in book.sheetnames:
            raise ValueError("Excel sayfası bulunamadı.")
        sheet = book[name]
        end = min(start + 24, sheet.max_row or start)
        rows = []
        for row in sheet.iter_rows(min_row=start, max_row=end, max_col=MAX_SHEET_COLS):
            cells = []
            for cell in row:
                value = cell.value
                if value is None:
                    continue
                if cell.data_type == "f":
                    value = "[formül; girdi olarak kullanılamaz]"
                elif isinstance(value, datetime) and value.time() == datetime.min.time():
                    value = value.date().isoformat()
                elif isinstance(value, date):
                    value = value.isoformat()
                cells.append(f"{cell.coordinate}: {str(value)[:500]}")
            rows.append(" | ".join(cells))
        return Excerpt(f"{name}!A{start}:BH{end}", "\n".join(rows)[:MAX_TEXT])
    finally:
        book.close()


class Edit(Record):
    paragraph: int = Field(ge=1, le=5000)
    before: str = Field(min_length=1, max_length=160)
    result: Key


class EditSet(Record):
    file: str = Field(pattern=r"^F[1-9][0-9]{0,2}$")
    changes: list[Edit] = Field(min_length=1, max_length=30)


def word_copy(file: StoredFile, changes: list[dict]) -> bytes:
    if Path(file.name).suffix.lower() != ".docx":
        raise ValueError("Bu düzenleme bir Word belgesi gerektiriyor.")
    doc = Document(io.BytesIO(_read(file)))
    for change in changes:
        index, before, after = change["paragraph"], change["before"], change["after"]
        if index > len(doc.paragraphs):
            raise ValueError(f"Word paragrafı {index} bulunamadı.")
        paragraph = doc.paragraphs[index - 1]
        if paragraph.text.count(before) != 1:
            raise ValueError(f"Paragraf {index}: değişecek metin bir kez geçmeli.")
        runs = [run for run in paragraph.runs if before in run.text]
        if len(runs) != 1 or not re.fullmatch(r"[-+\d., A-Z]+", after):
            raise ValueError(f"Paragraf {index}: tutar tek bir metin parçasında olmalı.")
        runs[0].text = runs[0].text.replace(before, after, 1)
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()
