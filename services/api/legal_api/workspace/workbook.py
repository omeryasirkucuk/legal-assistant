"""Build the optional Excel view from a saved and verified calculation."""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from legal_api.workspace.engine import VERSION, Plan, evaluate

MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _formula(operation: str, args: list[str]) -> str:
    joined = ",".join(args)
    match operation:
        case "sum" | "minimum" | "maximum":
            name = {"sum": "SUM", "minimum": "MIN", "maximum": "MAX"}[operation]
            return f"={name}({joined})"
        case "subtract" | "days_between":
            return f"={args[-1]}-{args[0]}" if operation == "days_between" else f"={args[0]}-{args[1]}"
        case "multiply":
            return f"={args[0]}*{args[1]}"
        case "divide":
            return f"={args[0]}/{args[1]}"
        case "percent":
            return f"={args[0]}/100"
        case "round_money":
            return f"=ROUND({args[0]},2)"
        case "add_days":
            return f"={args[0]}+{args[1]}"
        case "if_ge":
            return f"=IF({args[0]}>={args[1]},{args[2]},{args[3]})"
    raise ValueError("Bu hesap işlemi Excel'e aktarılamıyor.")


def _set_text(cell, text: str) -> None:
    cell.value = text
    # A document label/quotation must never introduce spreadsheet formulas or links.
    cell.data_type = "s"


def _format(sheet, header: int, widths: tuple[int, ...]) -> None:
    sheet.freeze_panes = f"B{header + 1}"
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[sheet.cell(1, index).column_letter].width = width
    for cell in sheet[header]:
        cell.fill = PatternFill("solid", fgColor="243B52")
        cell.font = Font(color="FFFFFF", bold=True)
    for row in sheet.iter_rows(min_row=header + 1):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
        sheet.row_dimensions[row[0].row].height = 30 if sheet.title == "Hesap" else 55


def _number_format(value) -> str:
    if isinstance(value.data, date):
        return "dd.mm.yyyy"
    if value.unit not in ("number", "day"):
        return '#,##0.00'
    return "0.##########"


def workbook(snapshot: dict) -> bytes:
    if snapshot["engine"] != VERSION:
        raise ValueError("Bu hesap motoru sürümü Excel'e aktarılamıyor.")
    plan = Plan.model_validate(snapshot["plan"])
    values = evaluate(plan)
    book = Workbook()
    sheet = book.active
    sheet.title = "Hesap"
    refs = {}
    sheet.append(["Hesap", "", ""])
    _set_text(sheet["A1"], plan.title)
    _set_text(sheet["A2"], f"Sürüm {snapshot['revision']} · İlk kayda ait hukuki dayanaklar")
    if snapshot.get("pending"):
        _set_text(sheet["A3"], f"Doğrulama bekliyor: {snapshot['pending']}")
    sheet.cell(4, 1, "Kalem")
    sheet.cell(4, 2, "Sonuç")
    sheet.cell(4, 3, "Birim")
    labels = {step.key: step.label for step in plan.steps}
    for key in plan.outputs:
        row = sheet.max_row + 1
        _set_text(sheet.cell(row, 1), labels[key])
        sheet.cell(row, 3, values[key].unit)
        sheet.cell(row, 2).number_format = _number_format(values[key])
    steps = book.create_sheet("Girdiler ve işlemler")
    steps.append(["Kalem", "Değer", "Birim", "İşlem / dayanak", "Kaynak"])
    for item in plan.inputs:
        row = steps.max_row + 1
        refs[item.key] = f"B{row}"
        value = values[item.key]
        if isinstance(value.data, date) and value.data < date(1900, 3, 1):
            raise ValueError("Excel eski tarihlerin bu hesapta doğru temsilini desteklemiyor.")
        if isinstance(value.data, Decimal) and len(value.data.normalize().as_tuple().digits) > 15:
            raise ValueError("Excel bu girdinin ondalık hassasiyetini koruyamıyor.")
        steps.cell(row, 2, value.data).number_format = _number_format(value)
        _set_text(steps.cell(row, 1), item.label)
        steps.cell(row, 3, item.unit)
        proof = snapshot["grounding"]["inputs"][item.key]
        _set_text(steps.cell(row, 4), item.meaning)
        _set_text(steps.cell(row, 5), f"{proof['citation']}\n{proof['quote']}\n{proof['url']}")
    rules = {item.key: item for item in plan.rules}
    for step in plan.steps:
        row = steps.max_row + 1
        args = [refs[key] for key in step.args]
        value = values[step.key]
        _set_text(steps.cell(row, 1), step.label)
        steps.cell(row, 2, _formula(step.operation, args)).number_format = _number_format(value)
        steps.cell(row, 3, value.unit)
        rule = rules[step.rule]
        _set_text(steps.cell(row, 4), f"{rule.applies_on}\n{rule.reasoning}")
        _set_text(steps.cell(row, 5), "\n".join(
            f"{proof['citation']} · {proof['quote']}\n{proof['url']}"
            for proof in snapshot["grounding"]["rules"][rule.key]))
        refs[step.key] = f"B{row}"
    for row, key in enumerate(plan.outputs, 5):
        sheet.cell(row, 2, f"='{steps.title}'!{refs[key]}")
        sheet.cell(row, 2).font = Font(bold=True, color="243B52")
    _format(sheet, 4, (55, 23, 15))
    _format(steps, 1, (38, 22, 12, 56, 75))
    # Excel recalculates on open. The canonical result remains the saved Decimal calculation.
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()
