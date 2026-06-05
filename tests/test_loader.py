"""testcase_loader の取込・検証テスト（決定的・ネットワーク非依存）。"""

import csv

import pytest

from app.ingest.testcase_loader import (
    TestcaseValidationError,
    load_from_csv,
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
