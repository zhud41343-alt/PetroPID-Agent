"""PetroPID-Agent V2.0 Industrial HMI Workbench Backend (FastAPI).

Endpoints:
- GET  /                        ISA-101 High-Performance Industrial HMI Workbench
- GET  /api/loops               30 Petrochemical control loops catalog
- POST /api/run/{loop_id}       Run 5-Agent workflow (with optional dynamic safety constraints & strategy)
- POST /api/sandbox             Live Stress-Test Sandbox on arbitrary unseen plant/valve parameters
- POST /api/copilot             Natural-language AI Control Engineer Copilot
- GET  /api/benchmark           Full 30-loop KPI benchmark results
- GET  /api/approval/{loop_id}  Printable official DCS PID Parameter Change Safety Approval Sheet (HTML/PDF)
- GET  /api/openjiuwen          openJiuwen Swarm manifest
- POST /mcp/rpc                 Live HTTP JSON-RPC 2.0 MCP Server
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "05_skills"))
sys.path.insert(0, str(ROOT / "06_mcp"))
sys.path.insert(0, str(ROOT / "07_agents"))

from orchestrator import PetroPIDOrchestrator, CODE_COMMIT
from decision_engine import ALGORITHM_VERSION, DATASET_VERSION, verify_audit_record
from openjiuwen_adapter import export_openjiuwen_manifest
from mcp_server import PetroPIDMCPServer

app = FastAPI(title="PetroPID-Agent V4.2 | 石化复杂过程多智能体自适应 PID 工程工作站", version="4.2.0")
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

orchestrator = PetroPIDOrchestrator()
mcp_server = PetroPIDMCPServer()

# Single-Source-of-Truth Immutable Run Registry (V4.2 P0-02 Strict Binding + Ephemeral SQLite)
_STORE_LOCK = threading.Lock()
RUN_STORE: Dict[str, Dict[str, Any]] = {}
LATEST_LOOP_RUN: Dict[str, str] = {}
EVICTED_RUN_IDS: set[str] = set()
MAX_RUN_STORE = 200
AUDIT_DB_PATH = Path(__file__).resolve().parent / "run_audit_cache.sqlite"


def _init_audit_db() -> None:
    try:
        with sqlite3.connect(str(AUDIT_DB_PATH)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS audit_runs ("
                "run_id TEXT PRIMARY KEY, loop_id TEXT NOT NULL, created_at TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            conn.commit()
    except Exception:
        pass


_init_audit_db()


def _store_run(res: Dict[str, Any]) -> Dict[str, Any]:
    rid = res["audit_meta"]["run_id"]
    lid = res["loop_meta"]["loop_id"]
    ts = res["audit_meta"].get("timestamp", datetime.now(timezone.utc).isoformat())
    with _STORE_LOCK:
        RUN_STORE[rid] = res
        LATEST_LOOP_RUN[lid] = rid
        if len(RUN_STORE) > MAX_RUN_STORE:
            oldest = next(iter(RUN_STORE))
            RUN_STORE.pop(oldest, None)
            EVICTED_RUN_IDS.add(oldest)
    try:
        with sqlite3.connect(str(AUDIT_DB_PATH)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO audit_runs (run_id, loop_id, created_at, payload_json) VALUES (?, ?, ?, ?)",
                (rid, lid, ts, json.dumps(res, ensure_ascii=False)),
            )
            conn.commit()
    except Exception:
        pass
    return res


def _load_from_sqlite(run_id: str) -> Optional[Dict[str, Any]]:
    try:
        with sqlite3.connect(str(AUDIT_DB_PATH)) as conn:
            row = conn.execute("SELECT payload_json FROM audit_runs WHERE run_id = ?", (run_id,)).fetchone()
            if row:
                return json.loads(row[0])
    except Exception:
        pass
    return None


def _resolve_run_strict(loop_id: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """P0-02 Strict audit record resolution: NEVER cross-bind, NEVER silently fallback, NEVER auto-rerun."""
    with _STORE_LOCK:
        if run_id is not None:
            if run_id in EVICTED_RUN_IDS:
                raise HTTPException(
                    status_code=410,
                    detail=f"run_id `{run_id}` 已因内存容量上限淘汰，禁止使用其他运行结果替代或伪造历史审批单。",
                )
            rec = RUN_STORE.get(run_id)
        else:
            latest_rid = LATEST_LOOP_RUN.get(loop_id)
            rec = RUN_STORE.get(latest_rid) if latest_rid else None

    if rec is None and run_id is not None:
        rec = _load_from_sqlite(run_id)

    if rec is None:
        if run_id is not None:
            raise HTTPException(
                status_code=404,
                detail=f"指定的 run_id `{run_id}` 不存在或已随容器重启失效，禁止静默回退或自动重跑。",
            )
        raise HTTPException(
            status_code=404,
            detail=f"回路 `{loop_id}` 尚无已执行的审计记录，请先运行分析；禁止为生成审批单自动重跑。",
        )

    actual_loop_id = rec.get("loop_meta", {}).get("loop_id")
    if actual_loop_id != loop_id:
        raise HTTPException(
            status_code=409,
            detail=f"跨回路绑定冲突：run_id `{rec.get('audit_meta', {}).get('run_id')}` 归属 `{actual_loop_id}`，与请求的 `{loop_id}` 不匹配。",
        )

    chk = verify_audit_record(rec)
    if chk["audit_status"] != "PASS":
        raise HTTPException(
            status_code=422,
            detail=f"审计记录完整性校验失败（{', '.join(chk['errors'])}），拒绝输出不可信审批单或审计包。",
        )
    return rec


def _resolve_for_copilot(loop_id: str) -> Dict[str, Any]:
    with _STORE_LOCK:
        latest_rid = LATEST_LOOP_RUN.get(loop_id)
        if latest_rid and latest_rid in RUN_STORE:
            return RUN_STORE[latest_rid]
    return _store_run(orchestrator.run_loop_workflow(loop_id))


class RunOptions(BaseModel):
    max_overshoot_pct: float = 18.0
    max_ms: float = 2.2
    min_gm: float = 1.8
    min_pm_deg: float = 35.0
    preferred_strategy: Optional[str] = None


class SandboxRequest(BaseModel):
    K: float = 1.6
    tau: float = 16.0
    theta: float = 5.5
    init_Kc: float = 2.1
    init_Ti: float = 8.0
    stiction_S: float = 0.0
    stiction_J: float = 0.0
    disturbance_amp: float = 0.0
    max_overshoot_pct: float = 18.0
    max_ms: float = 2.2
    preferred_strategy: Optional[str] = None


class CSVUploadRequest(BaseModel):
    filename: str = "custom_loop.csv"
    csv_text: str
    init_Kc: float = 1.5
    init_Ti: float = 10.0
    dt: float = 1.0


class CopilotRequest(BaseModel):
    message: str
    current_loop_id: str = "LOOP-006"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/api/loops")
def list_loops() -> JSONResponse:
    p = ROOT / "02_datasets" / "labels" / "loop_labels.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    return JSONResponse(content={"count": len(data), "loops": data})


@app.post("/api/run/{loop_id}")
def run_workflow(loop_id: str, opts: Optional[RunOptions] = None) -> JSONResponse:
    opts = opts or RunOptions()
    try:
        result = _store_run(orchestrator.run_loop_workflow(
            loop_id,
            max_overshoot_pct=opts.max_overshoot_pct,
            max_ms=opts.max_ms,
            min_gm=opts.min_gm,
            min_pm_deg=opts.min_pm_deg,
            preferred_strategy=opts.preferred_strategy,
        ))
        return JSONResponse(content=result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/sandbox")
def run_sandbox(req: SandboxRequest) -> JSONResponse:
    result = _store_run(orchestrator.run_sandbox_workflow(**req.model_dump()))
    return JSONResponse(content=result)


@app.post("/api/upload_csv")
def run_uploaded_csv(req: CSVUploadRequest) -> JSONResponse:
    import io
    import numpy as np
    import pandas as pd
    if len(req.csv_text.encode("utf-8")) > 512 * 1024:
        raise HTTPException(status_code=413, detail="CSV 文件过大（上限 512 KB）")
    try:
        df = pd.read_csv(io.StringIO(req.csv_text))
        cols = {c.strip().lower(): c for c in df.columns}
        for need in ("sp", "pv", "op"):
            if need not in cols:
                raise HTTPException(status_code=400, detail=f"CSV 缺少必需列: {need} (需包含 sp, pv, op)")
        sp = pd.to_numeric(df[cols["sp"]], errors="coerce").to_numpy(dtype=float)
        pv = pd.to_numeric(df[cols["pv"]], errors="coerce").to_numpy(dtype=float)
        op = pd.to_numeric(df[cols["op"]], errors="coerce").to_numpy(dtype=float)
        t = (
            pd.to_numeric(df[cols["timestamp_s"]], errors="coerce").to_numpy(dtype=float)
            if "timestamp_s" in cols
            else np.arange(len(pv), dtype=float) * req.dt
        )
        safe_pv_bias = float(np.nanmean(pv[:15])) if np.any(np.isfinite(pv[:15])) else 50.0
        safe_op_bias = float(np.nanmean(op[:15])) if np.any(np.isfinite(op[:15])) else 50.0
        meta = {
            "loop_id": "CSV-UPLOAD",
            "tag_name": req.filename.replace(".csv", "")[:12].upper(),
            "unit_name": "用户上传历史数据(CSV)",
            "loop_type": "Temperature",
            "description": f"上传文件：{req.filename} ({len(pv)} 点，无独立物理真值)",
            "pv_unit": "",
            "anomaly_type": "CUSTOM_CSV",
            "data_source_type": "UPLOADED_HISTORICAL_CSV",
            "has_known_plant_truth": False,
            "true_K": None, "true_tau": None, "true_theta": None,
            "pv_bias": safe_pv_bias, "op_bias": safe_op_bias,
            "init_Kc": req.init_Kc, "init_Ti": req.init_Ti, "init_Td": 0.0,
            "disturbance_amp": 0.0, "disturbance_period": 0.0, "dt": req.dt, "seed": 42,
        }
        res = _store_run(orchestrator._execute_pipeline(
            meta=meta, t=t, sp=sp, pv=pv, op=op,
            max_overshoot_pct=18.0, max_ms=2.2, min_gm=1.8, min_pm_deg=35.0,
            preferred_strategy=None, is_sandbox=True,
        ))
        return JSONResponse(content=res)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"CSV 解析失败: {exc}")


@app.post("/api/copilot")
def copilot_chat(req: CopilotRequest) -> JSONResponse:
    msg = req.message.strip()
    bench_p = ROOT / "07_agents" / "benchmark_results.json"
    bench = json.loads(bench_p.read_text(encoding="utf-8")) if bench_p.exists() else {}

    # Intent 1: Plant-wide Top-N risk scan
    if any(k in msg for k in ("全厂", "巡检", "危险", "风险", "Top", "top", "最严重")):
        rows = bench.get("per_loop_results", [])
        ranked = sorted(rows, key=lambda r: (r["oi_before"] * 2.0 + r["iae_before"] * 0.25), reverse=True)[:5]
        lines = ["已完成全厂 5 大装置 30 个控制回路批量风险扫描，当前风险 Top 5 如下："]
        for i, r in enumerate(ranked, 1):
            lines.append(f"{i}. **{r['loop_id']} ({r['tag_name']})** [{r['unit_name']}] — 诊断：`{r['pred_anomaly']}`，OI={r['oi_before']:.2f}，IAE={r['iae_before']:.2f}")
        lines.append("建议优先处理上述高振荡与粘滞回路（点击任意回路即可进入详细整定与校验）。")
        return JSONResponse(content={
            "reply": "\n".join(lines),
            "action": {"type": "HIGHLIGHT_LOOP", "loop_id": ranked[0]["loop_id"] if ranked else req.current_loop_id},
        })

    # Intent 2: Tighten overshoot or Ms safety constraints dynamically (Unified Fail-Closed Gate!)
    m_os = re.search(r"超调.*?(\d+(?:\.\d+)?)", msg)
    m_ms = re.search(r"[Mm]s.*?(\d+(?:\.\d+)?)", msg)
    if m_os or m_ms or "收紧" in msg or "严苛" in msg:
        new_os = float(m_os.group(1)) if m_os else 8.0
        new_ms = float(m_ms.group(1)) if m_ms else 1.6
        res = orchestrator.run_loop_workflow(
            req.current_loop_id,
            max_overshoot_pct=new_os,
            max_ms=new_ms,
            preferred_strategy="performance" if "高性能" in msg else None,
        )
        fb = any(t.get("fallback_triggered") for t in res["trace"])
        st = res["final_status"]
        if st == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW":
            gate_line = f"- 门控结论：**通过 11 项硬约束与性能门控（待人工复核）**；回退状态：{'已拦截并自动回退保守策略通过' if fb else '一次通过'}"
            pid_line = f"- 推荐待复核参数：Kc={res['final_pid']['Kc']}, Ti={res['final_pid']['Ti']}s（原参数 Kc={res['initial_pid']['Kc']}, Ti={res['initial_pid']['Ti']}s）"
        else:
            gate_line = f"- 门控结论：**已阻断参数变更（{st}）**；原因：{res['decision_reason']}"
            pid_line = f"- 参数动作：**保持原参数不变**（Kc={res['initial_pid']['Kc']}, Ti={res['initial_pid']['Ti']}s，禁止推荐新参数）"
        reply = (
            f"已将安全红线动态收紧为：标称超调 ≤ {new_os}%、最大灵敏度 Ms ≤ {new_ms}，并对 `{req.current_loop_id}` 执行统一 Fail-Closed 闭环门控（RunID: `{res['audit_meta']['run_id']}`）。\n"
            f"{gate_line}\n"
            f"{pid_line}"
        )
        return JSONResponse(content={"reply": reply, "action": {"type": "UPDATE_RESULT", "data": res}})

    # Intent 3: Switch strategy (conservative / balanced / performance)
    if any(k in msg for k in ("保守", "均衡", "高性能")):
        strat = "conservative" if "保守" in msg else ("performance" if "高性能" in msg else "balanced")
        res = orchestrator.run_loop_workflow(req.current_loop_id, preferred_strategy=strat)
        _store_run(res)
        st = res["final_status"]
        reply = (
            f"已切换为 **{strat}** 策略并完成 11 项安全硬约束（含 C-000）与 5 工况验证（RunID: `{res['audit_meta']['run_id']}`）：\n"
            f"- 最终状态：`{st}`（`deployment_authorized=false`）\n"
            f"- 参数动作：Kc={res['final_pid']['Kc']}, Ti={res['final_pid']['Ti']}s\n"
            f"- 门控依据：{res['decision_reason']}"
        )
        return JSONResponse(content={"reply": reply, "action": {"type": "UPDATE_RESULT", "data": res}})

    # Intent 4: Valve stiction explanation / ontology lookup
    if any(k in msg for k in ("粘滞", "阀门", "PIC-304", "LOOP-021", "LOOP-020", "本体")):
        kg = orchestrator.runner.invoke("petro_knowledge_lookup", {"anomaly_type": "VALVE_STICTION"})
        target_loop = "LOOP-020" if "LOOP-020" in msg else "LOOP-021"
        reply = (
            f"依据化工自控本体规则（`{kg['ontology_class']}`）：\n"
            f"{kg['engineering_guidance']}\n"
            f"已为您定位典型阀门粘滞回路 `{target_loop}`，可切换至 **「PV-OP 相图」** 查看滞回环与加速度峰度证据。"
        )
        return JSONResponse(content={"reply": reply, "action": {"type": "SELECT_LOOP", "loop_id": target_loop}})

    # Default: Grounded Engineering Q&A via live DeepSeek LLM (resolves explicit LOOP-xxx mention in question)
    m_lid = re.search(r"LOOP-\d{3}", msg.upper())
    target_lid = m_lid.group(0) if m_lid else req.current_loop_id
    res = _resolve_for_copilot(target_lid)
    d0 = res["diagnosis"]
    ident = res.get("identification") or {}
    safety = res.get("safety") or {}
    failed_rules = [
        f"{c['constraint_id']}({c['rule_name']}: {c['measured_value']} vs {c['threshold']})"
        for c in safety.get("constraint_audit", [])
        if not c.get("passed")
    ]
    grounded_context = {
        "user_question": msg,
        "loop_id": res["loop_meta"]["loop_id"],
        "tag_name": res["loop_meta"]["tag_name"],
        "unit_name": res["loop_meta"]["unit_name"],
        "run_id": res["audit_meta"]["run_id"],
        "final_status": res["final_status"],
        "decision_reason": res["decision_reason"],
        "deployment_authorized": False,
        "anomaly_type": d0.get("anomaly_type"),
        "harris_index": d0.get("harris_index"),
        "oscillation_index": d0.get("oscillation_index"),
        "stiction_index": d0.get("stiction_index"),
        "initial_pid": res["initial_pid"],
        "final_pid": res["final_pid"],
        "fopdt_val_fit_pct": ident.get("val_fit_pct"),
        "fopdt_val_r2": ident.get("val_r2"),
        "failed_constraints": failed_rules,
    }
    fallback_reply = (
        f"基于当前回路 `{res['loop_meta']['loop_id']} ({res['loop_meta']['tag_name']})` 的实测审计结果"
        f"（RunID: `{res['audit_meta']['run_id']}`）：\n"
        f"- 诊断类别：`{d0.get('anomaly_type')}`（OI={d0.get('oscillation_index')}, SI={d0.get('stiction_index')}）\n"
        f"- 最终状态：`{res['final_status']}`（`deployment_authorized=false`）\n"
        f"- 门控结论：{res['decision_reason']}"
    )
    llm_ans = orchestrator.llm.synthesize_decision(
        agent_role="PetroPID-Copilot",
        system_prompt=(
            "你是 PetroPID-Agent 资深石油化工过程控制专家副驾驶。请严格基于提供的结构化实测数据回答用户问题，"
            "绝不编造未出现的数值，绝不宣称可自动下发真实 DCS（deployment_authorized 恒为 false），回答简洁专业。"
        ),
        structured_state=grounded_context,
        fallback_text=fallback_reply,
    )
    badge = ""
    if llm_ans.get("mode") == "live_llm_api":
        tok = (llm_ans.get("usage") or {}).get("total_tokens", "-")
        badge = f"\n\n`[{llm_ans.get('model')} · {llm_ans.get('latency_ms')}ms · {tok} tokens · RunID {res['audit_meta']['run_id']}]`"
    return JSONResponse(content={
        "reply": f"{llm_ans['reasoning']}{badge}",
        "llm_telemetry": {
            "mode": llm_ans.get("mode"),
            "model": llm_ans.get("model"),
            "latency_ms": llm_ans.get("latency_ms"),
            "request_id": llm_ans.get("request_id"),
            "usage": llm_ans.get("usage"),
        },
        "action": {"type": "NONE"},
    })


@app.get("/api/approval/{loop_id}", response_class=HTMLResponse)
def export_approval_sheet(loop_id: str, run_id: Optional[str] = None) -> HTMLResponse:
    """Generate official printable DCS PID Parameter Change Safety Approval Form bound strictly to run_id."""
    res = _resolve_run_strict(loop_id, run_id)
    meta = res["loop_meta"]
    am = res["audit_meta"]
    d0 = res["diagnosis"]
    d1 = res["after_diagnosis"] or d0
    s = res["safety"]
    audit_rows = ""
    regime_rows = ""
    if s:
        for c in s["constraint_audit"]:
            audit_rows += f"<tr><td>{c['constraint_id']}</td><td>{c['category']}</td><td>{c['rule_name']}</td><td>{c['measured_value']}</td><td>{c['threshold']}</td><td style='color:{'#047857' if c['passed'] else '#b91c1c'};font-weight:700'>{'通过' if c['passed'] else '拦截'}</td></tr>"
        for r in s.get("operating_point_checks", []):
            regime_rows += f"<tr><td><b>{r['regime_name']}</b></td><td>K={r['plant_K']} / τ={r['plant_tau']}s / θ={r['plant_theta']}s</td><td>{r['overshoot_pct']}% / ≤{r['overshoot_limit_pct']}%</td><td>{r['oscillation_index']} / ≤{r['oi_limit']}</td><td>{r['iae']}</td><td style='color:{'#047857' if r['passed'] else '#b91c1c'};font-weight:700'>{'通过' if r['passed'] else '拦截'}</td></tr>"
    st = res["final_status"]
    is_valid_rec = st == "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"
    banner_bg = "#ecfdf5" if is_valid_rec else "#fef2f2"
    banner_fg = "#047857" if is_valid_rec else "#b91c1c"
    banner_title = "【仿真校验通过 · 待自控工程师人工复核】" if is_valid_rec else f"【系统拦截 / 不建议变更：{st}】"
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>DCS PID 参数变更安全复核单 - {meta['tag_name']}</title>
    <style>body{{font-family:'Microsoft YaHei',sans-serif;max-width:860px;margin:24px auto;color:#111827;line-height:1.6}}
    h1{{text-align:center;font-size:20px;border-bottom:2px solid #0f172a;padding-bottom:10px}}
    .banner{{padding:10px 14px;border:1px solid {banner_fg};background:{banner_bg};color:{banner_fg};font-weight:700;margin:10px 0;border-radius:4px}}
    table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}}
    th,td{{border:1px solid #cbd5e1;padding:7px 10px;text-align:left}} th{{background:#f1f5f9}}
    .sig{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:28px;border-top:1px solid #94a3b8;padding-top:14px;font-size:13px}}
    @media print{{.no-print{{display:none}}}}</style></head><body>
    <button class="no-print" onclick="window.print()" style="float:right;padding:6px 14px;cursor:pointer">打印 / 另存为 PDF</button>
    <h1>石油化工装置 DCS PID 控制参数变更安全复核单（仿真评估）</h1>
    <div class="banner">{banner_title} — {res['decision_reason']}</div>
    <p style="font-size:12px;color:#475569">RunID: <b>{am['run_id']}</b> | InputHash: <code>{am['input_sha256']}</code> | OutputHash: <code>{am['output_sha256']}</code> | Code: <code>{am['code_commit']}</code> | deployment_authorized=<b>false</b></p>
    <p style="font-size:12px;color:#475569">安全声明：{res['simulation_disclaimer']}</p>
    <table><tr><th>装置名称</th><td>{meta['unit_name']}</td><th>仪表位号</th><td><b>{meta['tag_name']} ({meta['loop_id']})</b></td></tr>
    <tr><th>回路说明</th><td>{meta['description']}</td><th>诊断根因</th><td><b>{d0['anomaly_type']}</b> ({d0['severity']})</td></tr>
    <tr><th>原 PID 参数</th><td>Kc={res['initial_pid']['Kc']}, Ti={res['initial_pid']['Ti']}s, Td={res['initial_pid']['Td']}s</td>
        <th>最终建议参数</th><td><b>Kc={res['final_pid']['Kc']}, Ti={res['final_pid']['Ti']}s, Td={res['final_pid']['Td']}s</b></td></tr>
    <tr><th>仿真性能对比</th><td colspan="3">振荡指数 OI: {d0['oscillation_index']:.2f} → <b>{d1['oscillation_index']:.2f}</b> &nbsp;|&nbsp; IAE: {d0['iae']:.2f} → <b>{d1['iae']:.2f}</b> &nbsp;|&nbsp; 阀位磨损: {d0['op_travel']:.2f} → <b>{d1['op_travel']:.2f}%/s</b></td></tr>
    <tr><th>审批状态</th><td colspan="3"><b>{st}</b> | engineering_approval_status=<code>{res['engineering_approval_status']}</code> | deployment_authorized=<code>false</code></td></tr></table>
    <h3 style="font-size:15px">11 项确定性安全约束审计明细（含 C-000 模型可信度门控）</h3>
    <table><thead><tr><th>编号</th><th>类别</th><th>规则项</th><th>实测值</th><th>安全阈值</th><th>结果</th></tr></thead><tbody>{audit_rows or '<tr><td colspan=6>健康回路，无需参数变更</td></tr>'}</tbody></table>
    <h3 style="font-size:15px">5 工况鲁棒性跨工况验证明细（标称超调 ≤18%，扰动工况 ≤25%）</h3>
    <table><thead><tr><th>扰动工况</th><th>机理模型 (K / τ / θ)</th><th>超调 / 阈值</th><th>振荡 OI / 阈值</th><th>IAE</th><th>结果</th></tr></thead><tbody>{regime_rows or '<tr><td colspan=6>未进入跨工况验证阶段</td></tr>'}</tbody></table>
    <div class="sig"><div>自控工程师复核签字：______________</div><div>工艺主任审批签字：______________</div><div>人工现场投运日期：____年__月__日</div></div>
    </body></html>"""
    return HTMLResponse(content=html)


@app.get("/api/export_bundle/{loop_id}")
def export_auditable_bundle(loop_id: str, run_id: Optional[str] = None) -> JSONResponse:
    """Export self-contained auditable JSON test bundle bound strictly to run_id."""
    res = _resolve_run_strict(loop_id, run_id)
    bundle = {
        "bundle_schema": "petropid.audit_bundle.v4.0",
        "audit_meta": res["audit_meta"],
        "final_decision": res["final_decision"],
        "candidate_eligible_for_review": res["candidate_eligible_for_review"],
        "engineering_approval_status": res["engineering_approval_status"],
        "deployment_authorized": False,
        "simulation_disclaimer": res["simulation_disclaimer"],
        "loop_meta": res["loop_meta"],
        "final_status": res["final_status"],
        "decision_reason": res["decision_reason"],
        "initial_pid": res["initial_pid"],
        "final_pid": res["final_pid"],
        "diagnosis": res["diagnosis"],
        "identification": res["identification"],
        "safety": res["safety"],
        "baseline_comparison": res["baseline_comparison"],
        "trace": res["trace"],
    }
    return JSONResponse(
        content=bundle,
        headers={"Content-Disposition": f'attachment; filename="audit_bundle_{loop_id}_{res["audit_meta"]["run_id"]}.json"'},
    )


@app.get("/healthz")
def healthz(probe_llm: bool = False) -> JSONResponse:
    """Honest runtime health check: separates LLM config vs actual live connectivity probe."""
    configured_mode = orchestrator.llm.mode
    llm_probe: Dict[str, Any] = {
        "configured_mode": configured_mode,
        "connectivity_status": "OFFLINE_DETERMINISTIC" if configured_mode != "live_llm_api" else "CONFIGURED_UNPROBED",
    }
    if probe_llm and configured_mode == "live_llm_api":
        ans = orchestrator.llm.synthesize_decision(
            agent_role="HealthProbe",
            system_prompt="Reply OK.",
            structured_state={"ping": True},
            fallback_text="fallback",
        )
        if ans.get("mode") == "live_llm_api":
            llm_probe.update({
                "connectivity_status": "VERIFIED_LIVE",
                "model": ans.get("model"),
                "latency_ms": ans.get("latency_ms"),
                "request_id": ans.get("request_id"),
            })
        else:
            llm_probe.update({
                "connectivity_status": "DEGRADED_FALLBACK",
                "fallback_reason": ans.get("fallback_reason", "unknown"),
            })
    return JSONResponse(content={
        "status": "ok",
        "version": "4.2.0",
        "algorithm_version": ALGORITHM_VERSION,
        "dataset_version": DATASET_VERSION,
        "code_commit": CODE_COMMIT,
        "llm_mode": configured_mode,
        "llm_health": llm_probe,
        "deployment_authorized": False,
        "run_store": {
            "stored_runs": len(RUN_STORE),
            "max_capacity": MAX_RUN_STORE,
            "evicted_count": len(EVICTED_RUN_IDS),
            "persistence_policy": "in_memory_plus_local_sqlite_ephemeral_on_free_tier",
        },
    })


@app.get("/api/benchmark")
def get_benchmark() -> JSONResponse:
    p = ROOT / "07_agents" / "benchmark_results.json"
    return JSONResponse(content=json.loads(p.read_text(encoding="utf-8")))


@app.get("/api/openjiuwen")
def get_openjiuwen_manifest() -> JSONResponse:
    return JSONResponse(content=export_openjiuwen_manifest())


@app.post("/mcp/rpc")
async def mcp_rpc(request: Request) -> JSONResponse:
    payload: Dict[str, Any] = await request.json()
    return JSONResponse(content=mcp_server.handle_request(payload))


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
