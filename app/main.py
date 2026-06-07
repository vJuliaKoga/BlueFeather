"""FastAPI エントリ・ルーティング（詳細設計§8）。

画面と処理をつなぐだけ。スコア計算・判定・LLM 呼び出しは pipeline / engine 経由で、
ここには再実装しない。キーは画面・ログに出さない。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import repository
from app.db.repository import get_connection
from app.engine.gate import compose_review, judge
from app.engine.pipeline import run_phase_review
from app.ingest.testcase_loader import TestcaseValidationError
from app.persona.schema import TechniqueRecommendation

_BASE_DIR = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_BASE_DIR / "ui" / "templates"))
_UPLOAD_DIR = Path("uploads")

app = FastAPI(title="BlueFeather")
app.mount("/static", StaticFiles(directory=str(_BASE_DIR / "ui" / "static")), name="static")


@app.on_event("startup")
def _ensure_uploads() -> None:
    # アップロード保存先が無ければ作成する。
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# --- 表示用ヘルパ --------------------------------------------------------------

def _phase_status(gate: dict | None, latest: dict | None) -> tuple[str, str]:
    """ダッシュボード/履歴の状態（CSSクラス, ラベル）を決める。"""
    if gate and gate["closed"]:
        return "status-open", "開門済み"
    if latest is None:
        return "status-todo", "未着手"
    if latest["status"] == "manual_check":
        return "status-todo", "要手動確認"
    if latest["passed"]:
        return "status-open", "開門済み"
    return "status-near", "あと一歩"


def _score_disp(total_score: float | None) -> str:
    return f"{round(total_score)}点" if total_score is not None else "—"


def _build_phase_context(conn, phase: dict) -> dict:
    """phase 画面に渡すコンテキスト（履歴付き）。テンプレートは表示に専念。"""
    history_rows = repository.get_round_history(conn, phase["id"])
    history = []
    for h in history_rows:
        if h["status"] == "manual_check":
            cls, label, disp = "status-todo", "要手動確認", "—"
        elif h["passed"]:
            cls, label, disp = "status-open", "開門", _score_disp(h["total_score"])
        else:
            cls, label, disp = "status-near", "あと一歩", _score_disp(h["total_score"])
        history.append({
            "round_no": h["round_no"], "review_id": h["review_id"],
            "score_disp": disp, "status_class": cls, "status_label": label,
        })
    return {
        "phase": phase,
        "rubric_items": repository.get_rubric_items_full(conn, phase["id"]),
        "coverage_target": phase["coverage_weight"] > 0,
        "history": history,
    }


# --- ルート --------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    conn = get_connection()
    try:
        phases = repository.get_all_phases(conn)
        view = []
        for p in phases:
            gate = repository.get_gate_status(conn, p["id"])
            latest = repository.get_latest_review_for_phase(conn, p["id"])
            cls, label = _phase_status(gate, latest)
            view.append({
                **p,
                "status_class": cls,
                "status_label": label,
                "latest_score": _score_disp(latest["total_score"]) if latest else "—",
            })
    finally:
        conn.close()
    return _TEMPLATES.TemplateResponse(request, "dashboard.html", {"phases": view})


@app.get("/phases/{key}", response_class=HTMLResponse)
def phase_detail(request: Request, key: str):
    conn = get_connection()
    try:
        phase = repository.get_phase(conn, key)
        if phase is None:
            return HTMLResponse(f"未知のフェーズです: {key}", status_code=404)
        ctx = _build_phase_context(conn, phase)
    finally:
        conn.close()
    return _TEMPLATES.TemplateResponse(request, "phase.html", ctx)


async def _save_upload(upload: UploadFile | None) -> str | None:
    """アップロードを uploads/ に保存しパスを返す。空なら None。"""
    if upload is None or not upload.filename:
        return None
    # 衝突回避のため接頭辞に短いランダム値を付ける。
    dest = _UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{Path(upload.filename).name}"
    dest.write_bytes(await upload.read())
    return str(dest)


@app.post("/phases/{key}/submit")
async def submit_phase(
    request: Request,
    key: str,
    body: str = Form(...),
    submitted_by: str = Form(...),
    targets: UploadFile | None = File(None),
    cases: UploadFile | None = File(None),
):
    conn = get_connection()
    try:
        phase = repository.get_phase(conn, key)
        if phase is None:
            return HTMLResponse(f"未知のフェーズです: {key}", status_code=404)

        targets_path = await _save_upload(targets)
        cases_path = await _save_upload(cases)

        try:
            result = run_phase_review(key, body, submitted_by, targets_path, cases_path)
        except TestcaseValidationError as e:
            # 検証エラーは 500 で落とさず、画面にメッセージを出して差し戻す。
            ctx = _build_phase_context(conn, phase)
            ctx.update({"errors": e.messages, "submitted_body": body, "submitted_by": submitted_by})
            return _TEMPLATES.TemplateResponse(request, "phase.html", ctx, status_code=400)
    finally:
        conn.close()

    # manual_check でも review 画面へ正常遷移する。
    return RedirectResponse(url=f"/reviews/{result['review_id']}", status_code=303)


@app.get("/reviews/{review_id}", response_class=HTMLResponse)
def review_detail(request: Request, review_id: int):
    conn = get_connection()
    try:
        review = repository.get_review(conn, review_id)
        if review is None:
            return HTMLResponse(f"レビューが見つかりません: {review_id}", status_code=404)
        phase = repository.get_phase_by_id(conn, review["phase_id"])
        coverage_metrics = repository.get_coverage_metrics(conn, review_id)
    finally:
        conn.close()

    ctx = {
        "phase": phase,
        "round_no": review["round_no"],
        "status": review["status"],
        "coverage_target": phase["coverage_weight"] > 0,
        "coverage_metrics": coverage_metrics,
    }

    if review["status"] == "ok":
        # 保存済みの語り部品から所見を再合成する（スコア計算はしない＝judgeは閾値比較のみ）。
        overall_findings = json.loads(review["findings"] or "[]")
        recos = [TechniqueRecommendation(**r) for r in json.loads(review["recommendations"] or "[]")]
        passed, score_line = judge(review["total_score"], phase["pass_threshold"])
        review_text = compose_review(
            review["acknowledgement"] or "", score_line, overall_findings, recos, review["closing"] or ""
        )
        ctx.update({
            "score_line": score_line,
            "status_class": "status-open" if passed else "status-near",
            "review_text": review_text,
            "recommendations": [r.model_dump() for r in recos],
            "rubric_breakdown": json.loads(review["rubric_breakdown"] or "[]"),
        })

    return _TEMPLATES.TemplateResponse(request, "review.html", ctx)


@app.get("/rubrics/{key}", response_class=HTMLResponse)
def rubrics_detail(request: Request, key: str):
    # ルーブリック配点の確認は phase 画面を流用する。
    return phase_detail(request, key)
