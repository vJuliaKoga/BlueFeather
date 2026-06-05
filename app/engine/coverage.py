"""定量カバレッジ計算（関守エンジン・詳細設計§3）。

技法別の網羅率と coverage_score を決定的に算出する。LLM には一切触れない。
合否判定・総合点（total_score）はここでは扱わない（P4）。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from app.ingest.testcase_loader import Case, Target

# 技法重み（ドラフト・調整可能。将来 settings への外出しを検討）。
TECHNIQUE_WEIGHTS = {
    "境界値分析": 0.35,
    "デシジョンテーブル": 0.35,
    "状態遷移": 0.20,
    "同値分割": 0.10,
}


@dataclass
class TechniqueCoverage:
    technique: str
    total: int
    covered: int
    rate: float
    weight: float


@dataclass
class CoverageResult:
    by_technique: list[TechniqueCoverage]
    coverage_score: float


def compute_coverage(targets: list[Target], cases: list[Case]) -> CoverageResult:
    """技法別の total/covered/rate と coverage_score を算出する。"""
    # case が参照する target_id の集合（重複は無視）。
    covered_ids: set[str] = set()
    for c in cases:
        covered_ids.update(c.target_ids)

    by_technique: list[TechniqueCoverage] = []
    weighted_sum = 0.0
    weight_total = 0.0

    # 技法重みの定義順で安定して出力する（決定性）。
    for technique, weight in TECHNIQUE_WEIGHTS.items():
        # 対象は must_cover=True の target のみ。
        relevant = [t for t in targets if t.must_cover and t.technique == technique]
        total = len(relevant)
        if total == 0:
            # total==0 の技法は計算から除外。
            continue
        covered = sum(1 for t in relevant if t.target_id in covered_ids)
        rate = covered / total
        by_technique.append(
            TechniqueCoverage(technique, total, covered, rate, weight)
        )
        weighted_sum += weight * rate
        weight_total += weight

    coverage_score = 100 * weighted_sum / weight_total if weight_total > 0 else 0.0
    return CoverageResult(by_technique, coverage_score)


def _main() -> None:
    parser = argparse.ArgumentParser(description="定量カバレッジ計算（CSV）")
    parser.add_argument("--targets", required=True, help="targets CSV のパス")
    parser.add_argument("--cases", required=True, help="cases CSV のパス")
    args = parser.parse_args()

    # 表示のためだけに loader を内部利用する。
    from app.ingest.testcase_loader import load_from_csv

    targets, cases = load_from_csv(args.targets, args.cases)
    result = compute_coverage(targets, cases)

    # 表示は小数2桁。内部計算は丸めない。
    for tc in result.by_technique:
        print(f"{tc.technique}: covered {tc.covered} / total {tc.total}  rate {tc.rate:.2f}")
    print(f"coverage_score = {result.coverage_score:.2f}")


if __name__ == "__main__":
    _main()
