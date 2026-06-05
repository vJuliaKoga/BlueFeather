"""ReviewLLMOutput のスキーマ検証テスト（ネットワーク・キー不要）。"""

import pytest
from pydantic import ValidationError

from app.persona.schema import ReviewLLMOutput


def _valid_dict():
    return {
        "rubric_scores": [
            {
                "item_key": "boundary_coverage",
                "score": 3,
                "max_score": 4,
                "rationale": "境界の押さえが丁寧です。",
                "findings": ["上限側の確認も添えてみませんか"],
            }
        ],
        "acknowledgement": "よくまとまっています。",
        "closing": "まずはここから、いってみませんか。",
    }


def test_valid_passes():
    out = ReviewLLMOutput.model_validate(_valid_dict())
    assert out.rubric_scores[0].item_key == "boundary_coverage"


def test_score_over_max_fails():
    d = _valid_dict()
    d["rubric_scores"][0]["score"] = 5  # max_score=4 を超える
    with pytest.raises(ValidationError):
        ReviewLLMOutput.model_validate(d)


def test_missing_required_field_fails():
    d = _valid_dict()
    del d["acknowledgement"]  # 必須フィールド欠落
    with pytest.raises(ValidationError):
        ReviewLLMOutput.model_validate(d)


def test_technique_recommendations_defaults_empty():
    out = ReviewLLMOutput.model_validate(_valid_dict())
    assert out.technique_recommendations == []
