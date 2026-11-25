"""Unified Skill Runner with Idempotent Call-Hash Caching (Anti-Duplicate Invocation).

Loads processed benchmark datasets & knowledge triples, executes the 5 standardized
PetroPID skills, validates inputs, tracks latency, and prevents redundant tool calls
within the same multi-agent session.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "04_algorithms"))

from petro_pid import (
    PlantParams,
    PIDParams,
    diagnose_loop,
    identify_fopdt,
    identify_fopdt_with_observable_load_step_check,
    tune_pid,
    verify_pid_safety,
)


def _load_loop_metadata(loop_id: str) -> Dict[str, Any]:
    labels_path = ROOT / "02_datasets" / "labels" / "loop_labels.json"
    with open(labels_path, "r", encoding="utf-8") as f:
        labels = json.load(f)
    for item in labels:
        if item["loop_id"] == loop_id:
            return item
    raise ValueError(f"Unknown loop_id: {loop_id}")


def _load_loop_dataframe(meta: Dict[str, Any]) -> pd.DataFrame:
    csv_path = ROOT / "02_datasets" / "processed" / meta["split"] / meta["raw_file"]
    if not csv_path.exists():
        csv_path = ROOT / "02_datasets" / "raw" / meta["raw_file"]
    return pd.read_csv(csv_path)


class SkillRunner:
    """Executes PetroPID skills with deduplication cache and structured telemetry."""

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.call_history: list[Dict[str, Any]] = []
        self.duplicate_calls_prevented: int = 0

    def reset_session(self) -> None:
        self._cache.clear()
        self.call_history.clear()
        self.duplicate_calls_prevented = 0

    def _call_key(self, skill_name: str, params: Dict[str, Any]) -> str:
        payload = json.dumps({"skill": skill_name, "params": params}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def invoke(self, skill_name: str, params: Dict[str, Any], allow_cache: bool = True) -> Dict[str, Any]:
        key = self._call_key(skill_name, params)
        if allow_cache and key in self._cache:
            self.duplicate_calls_prevented += 1
            self.call_history.append({
                "skill": skill_name,
                "cache_hit": True,
                "latency_ms": 0.0,
                "params": params,
            })
            return self._cache[key]

        t0 = time.perf_counter()
        if skill_name == "pid_loop_diagnosis":
            result = self._run_diagnosis(params)
        elif skill_name == "fopdt_system_identification":
            result = self._run_identification(params)
        elif skill_name == "adaptive_pid_tuning":
            result = self._run_tuning(params)
        elif skill_name == "safety_constraint_verification":
            result = self._run_safety(params)
        elif skill_name == "petro_knowledge_lookup":
            result = self._run_knowledge_lookup(params)
        else:
            raise ValueError(f"Unsupported skill: {skill_name}")

        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        self._cache[key] = result
        self.call_history.append({
            "skill": skill_name,
            "cache_hit": False,
            "latency_ms": latency_ms,
            "params": params,
        })
        return result

    def _run_diagnosis(self, params: Dict[str, Any]) -> Dict[str, Any]:
        meta = _load_loop_metadata(params["loop_id"])
        df = _load_loop_dataframe(meta)
        res = diagnose_loop(
            sp=df["sp"].to_numpy(),
            pv=df["pv"].to_numpy(),
            op=df["op"].to_numpy(),
            dt=float(params.get("dt", meta.get("dt", 1.0))),
            estimated_delay_s=float(meta.get("true_theta", 4.0)),
            pid_kc=float(meta.get("init_Kc", 1.0)),
            pid_ti=float(meta.get("init_Ti", 10.0)),
        )
        out = res.to_dict()
        out["loop_id"] = meta["loop_id"]
        out["tag_name"] = meta["tag_name"]
        out["unit_name"] = meta["unit_name"]
        return out

    def _run_identification(self, params: Dict[str, Any]) -> Dict[str, Any]:
        meta = _load_loop_metadata(params["loop_id"])
        df = _load_loop_dataframe(meta)
        identify_fn = (
            identify_fopdt_with_observable_load_step_check
            if params.get("validation_profile") == "v4.3.4"
            else identify_fopdt
        )
        res = identify_fn(
            pv=df["pv"].to_numpy(),
            op=df["op"].to_numpy(),
            dt=float(params.get("dt", meta.get("dt", 1.0))),
            train_ratio=float(params.get("train_ratio", 0.65)),
        )
        out = res.to_dict()
        out["loop_id"] = meta["loop_id"]
        return out

    def _run_tuning(self, params: Dict[str, Any]) -> Dict[str, Any]:
        meta = _load_loop_metadata(params["loop_id"]) if "loop_id" in params else {}
        plant = PlantParams(
            K=float(params["plant_K"]),
            tau=float(params["plant_tau"]),
            theta=float(params["plant_theta"]),
            pv_bias=float(params.get("pv_bias", meta.get("pv_bias", 50.0))),
            op_bias=float(params.get("op_bias", meta.get("op_bias", 50.0))),
        )
        current_pid = PIDParams(
            Kc=float(params["current_Kc"]),
            Ti=float(params["current_Ti"]),
            Td=float(params.get("current_Td", 0.0)),
        )
        res = tune_pid(
            plant=plant,
            current_pid=current_pid,
            anomaly_type=str(params.get("anomaly_type", "AGGRESSIVE_TUNING")),
            dt=float(params.get("dt", 1.0)),
        )
        return res.to_dict()

    def _run_safety(self, params: Dict[str, Any]) -> Dict[str, Any]:
        plant = PlantParams(
            K=float(params["plant_K"]),
            tau=float(params["plant_tau"]),
            theta=float(params["plant_theta"]),
            pv_bias=float(params.get("pv_bias", 50.0)),
            op_bias=float(params.get("op_bias", 50.0)),
        )
        cand_pid = PIDParams(
            Kc=float(params["Kc"]),
            Ti=float(params["Ti"]),
            Td=float(params.get("Td", 0.0)),
        )
        res = verify_pid_safety(plant=plant, candidate_pid=cand_pid, dt=float(params.get("dt", 1.0)))
        return res.to_dict()

    def _run_knowledge_lookup(self, params: Dict[str, Any]) -> Dict[str, Any]:
        anomaly = str(params["anomaly_type"])
        loop_type = str(params.get("loop_type", "Temperature"))
        kg_path = ROOT / "03_models" / "knowledge_model" / "knowledge_triples.json"
        triples = []
        if kg_path.exists():
            with open(kg_path, "r", encoding="utf-8") as f:
                all_triples = json.load(f)
            triples = [
                t for t in all_triples
                if t.get("subject_code") == anomaly or t.get("subject_code") == loop_type
            ]
        guidance_map = {
            "VALVE_STICTION": "根据化工自控本体规则 R-01：阀门粘滞属于执行器机械非线性故障，严禁盲目增大比例增益；应优先派发仪表检修工单，过渡期采用保守降增益(conservative)缓冲参数。",
            "AGGRESSIVE_TUNING": "根据本体规则 R-02：激进整定导致相位裕度不足，应依据 FOPDT 辨识模型采用 SIMC 均衡策略降低 Kc 并适当增大 Ti，确保 Ms <= 2.0。",
            "SLUGGISH_TUNING": "根据本体规则 R-03：保守整定导致高 IAE 与慢恢复，应在满足稳定裕度前提下提升 Kc 并缩短 Ti。",
            "MODEL_MISMATCH": "根据本体规则 R-04：原油换炼或负荷切换引发增益/滞后漂移，需重辨识当前工况 FOPDT 模型并通过 ±20% 多工况鲁棒性校验。",
            "EXTERNAL_DISTURBANCE": "根据本体规则 R-05：周期性外部扰动需排查上游压机/泵组脉动源并增加前馈补偿，同时优化反馈抗扰动裕度。",
            "NORMAL": "根据本体规则 R-06：回路健康，保持原参数并归档例行巡检记录。",
        }
        return {
            "anomaly_type": anomaly,
            "ontology_class": f"petropid:{anomaly}",
            "matched_triples": triples[:6],
            "engineering_guidance": guidance_map.get(anomaly, "按标准化工 DCS 控制规范执行评估与校验。"),
        }
