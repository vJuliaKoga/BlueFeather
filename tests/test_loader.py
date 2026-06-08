"""testcase_loader の取込・検証テスト（決定的・ネットワーク非依存）。"""

import csv

import pytest

from app.ingest.testcase_loader import (
    TestcaseValidationError,
    extract_workbook_text,
    load_from_csv,
    load_from_xlsx,
)

# 検証用の列順。
TARGET_HEADER = ["target_id", "technique", "category", "target", "must_cover", "note"]
CASE_HEADER = ["test_id", "technique", "precondition", "input", "expected", "target_ids", "note"]


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def test_load_samples_ok():
    targets, cases = load_from_csv("samples/targets.csv", "samples/cases.csv")
    assert len(targets) == 8
    assert len(cases) == 6


def _arbitrary_workbook(path):
    # targets/cases テンプレに一致しない、工程ごとに異なる成果物Excelを模す。
    from openpyxl import Workbook

    wb = Workbook()
    ws1 = wb.active
    ws1.title = "機能一覧"
    ws1.append(["機能名", "説明"])
    ws1.append(["ログイン", "ID/PWで認証する"])
    ws2 = wb.create_sheet("テストスイート一覧")
    ws2.append(["#", "観点", "手順", "期待値"])
    ws2.append(["TC-001", "新規登録", "新規登録リンクを押す", "登録画面が出る"])
    wb.save(path)


def test_extract_workbook_text_arbitrary(tmp_path):
    p = tmp_path / "deliverable.xlsx"
    _arbitrary_workbook(str(p))
    text = extract_workbook_text(str(p))
    # 全シートが見出し付きでテキスト化され、内容が含まれる。
    assert "## シート: 機能一覧" in text
    assert "## シート: テストスイート一覧" in text
    assert "TC-001" in text and "ログイン" in text


def test_arbitrary_workbook_rejected_by_strict_loader(tmp_path):
    # 固定テンプレ（targets/cases）としては弾かれる＝パイプラインが汎用抽出へフォールバックする根拠。
    p = tmp_path / "deliverable.xlsx"
    _arbitrary_workbook(str(p))
    with pytest.raises(TestcaseValidationError):
        load_from_xlsx(str(p))


def test_undefined_reference(tmp_path):
    # 存在しない target_id を指す case。
    t = tmp_path / "t.csv"
    c = tmp_path / "c.csv"
    _write_csv(t, TARGET_HEADER, [["X1", "境界値分析", "age", "a", "Y", ""]])
    _write_csv(c, CASE_HEADER, [["T1", "境界値分析", "", "in", "exp", "NOPE", ""]])
    with pytest.raises(TestcaseValidationError) as ei:
        load_from_csv(str(t), str(c))
    assert any("NOPE" in m and "T1" in m for m in ei.value.messages)


def test_duplicate_target_id(tmp_path):
    t = tmp_path / "t.csv"
    c = tmp_path / "c.csv"
    _write_csv(
        t,
        TARGET_HEADER,
        [
            ["X1", "境界値分析", "age", "a", "Y", ""],
            ["X1", "境界値分析", "age", "b", "Y", ""],
        ],
    )
    _write_csv(c, CASE_HEADER, [["T1", "境界値分析", "", "in", "exp", "X1", ""]])
    with pytest.raises(TestcaseValidationError) as ei:
        load_from_csv(str(t), str(c))
    assert any("X1" in m and "重複" in m for m in ei.value.messages)


def test_missing_required_column(tmp_path):
    # targets から target_id 列を欠落させる。
    t = tmp_path / "t.csv"
    c = tmp_path / "c.csv"
    _write_csv(t, ["technique", "category", "target"], [["境界値分析", "age", "a"]])
    _write_csv(c, CASE_HEADER, [["T1", "境界値分析", "", "in", "exp", "", ""]])
    with pytest.raises(TestcaseValidationError) as ei:
        load_from_csv(str(t), str(c))
    assert any("target_id" in m for m in ei.value.messages)


def test_invalid_technique(tmp_path):
    t = tmp_path / "t.csv"
    c = tmp_path / "c.csv"
    _write_csv(t, TARGET_HEADER, [["X1", "謎技法", "age", "a", "Y", ""]])
    _write_csv(c, CASE_HEADER, [["T1", "境界値分析", "", "in", "exp", "X1", ""]])
    with pytest.raises(TestcaseValidationError) as ei:
        load_from_csv(str(t), str(c))
    assert any("謎技法" in m for m in ei.value.messages)
