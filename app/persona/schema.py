"""BlueWing 語り層の出力JSONスキーマ（詳細設計§6.3）。

LLM出力の型定義と検証のみ。スコア計算・合否判定はここに書かない（P4）。
"""

from __future__ import annotations

from pydantic import BaseModel, model_validator


class RubricScore(BaseModel):
    item_key: str
    score: int
    max_score: int
    rationale: str
    findings: list[str] = []

    @model_validator(mode="after")
    def _check_score_range(self) -> "RubricScore":
        # score は 0 以上 max_score 以下。範囲外は検証エラー。
        if not (0 <= self.score <= self.max_score):
            raise ValueError(
                f"score は 0〜{self.max_score} の範囲である必要があります "
                f"(item_key={self.item_key}, score={self.score})"
            )
        return self


class TechniqueRecommendation(BaseModel):
    target: str
    recommended_technique: str
    reason: str


class ReviewLLMOutput(BaseModel):
    rubric_scores: list[RubricScore]
    technique_recommendations: list[TechniqueRecommendation] = []
    acknowledgement: str
    closing: str
    overall_findings: list[str] = []
