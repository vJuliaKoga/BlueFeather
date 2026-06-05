"""合否判定と所見合成（関守エンジン・詳細設計§5.2／ペルソナ定義書§5）。

純粋関数のみ。DB・LLM には触れない。
合否判定は丸めない total_score で行い、文面のスコアは表示用に整数へ丸める。
"""

from __future__ import annotations

from app.persona.schema import TechniqueRecommendation

# スコア行テンプレート（調整可能な定数）。
OPEN_GATE_TEMPLATE = "{score}点。ここで関門は開きますよ。よくやりましたね。"
ALMOST_TEMPLATE = "いま{score}点。合格ラインの{threshold}点まで、あと一歩というところです。"

# 横断的な指摘は2〜3点に絞る。
MAX_FINDINGS = 3


def judge(total_score: float, threshold: float) -> tuple[bool, str]:
    """合否とスコア行を返す。判定は丸めない値で、表示は整数へ四捨五入。"""
    passed = total_score >= threshold
    score_disp = round(total_score)
    if passed:
        line = OPEN_GATE_TEMPLATE.format(score=score_disp)
    else:
        line = ALMOST_TEMPLATE.format(score=score_disp, threshold=round(threshold))
    return passed, line


def compose_review(
    acknowledgement: str,
    score_line: str,
    overall_findings: list[str],
    technique_recommendations: list[TechniqueRecommendation],
    closing: str,
) -> str:
    """ペルソナ定義書§5の順で1本の所見に組む。スコア行以外に点数は足さない。"""
    parts: list[str] = []

    # 1. 承認
    if acknowledgement:
        parts.append(acknowledgement)

    # 2. スコア行
    if score_line:
        parts.append(score_line)

    # 3. 横断的な指摘（・の箇条書き、先頭から絞る）
    findings = [f for f in overall_findings if f][:MAX_FINDINGS]
    if findings:
        parts.append("\n".join(f"・{f}" for f in findings))

    # 4. 技法レコメンド（あれば簡潔に）
    if technique_recommendations:
        lines = [
            f"・この観点なら、{r.target}には{r.recommended_technique}が合うのではないかな（{r.reason}）。"
            for r in technique_recommendations
        ]
        parts.append("\n".join(lines))

    # 5. 委ねる結び
    if closing:
        parts.append(closing)

    return "\n\n".join(parts)
