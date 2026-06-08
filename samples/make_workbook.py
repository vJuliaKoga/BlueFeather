"""samples/targets.csv と samples/cases.csv を 1つの Excel（sample.xlsx）にまとめる小スクリプト。

シート名は targets / cases。内容は変えず Excel 化するだけ（取込の動作確認用 fixture）。
"""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook

_SAMPLES_DIR = Path(__file__).resolve().parent


def _fill_sheet(ws, csv_path: Path) -> None:
    # CSV の行をそのまま（ヘッダ含め）シートへ写す。
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            ws.append(row)


def main() -> None:
    wb = Workbook()
    targets_ws = wb.active
    targets_ws.title = "targets"
    _fill_sheet(targets_ws, _SAMPLES_DIR / "targets.csv")

    cases_ws = wb.create_sheet("cases")
    _fill_sheet(cases_ws, _SAMPLES_DIR / "cases.csv")

    out = _SAMPLES_DIR / "sample.xlsx"
    wb.save(out)
    print(f"書き出し: {out}")


if __name__ == "__main__":
    main()
