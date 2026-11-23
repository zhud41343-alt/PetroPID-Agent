"""Unit tests for all 5 PetroPID standardized Skills and anti-duplicate caching."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "05_skills"))

from skill_runner import SkillRunner


def test_skill_registry_valid_json():
    reg_path = ROOT / "05_skills" / "skill_registry.json"
    with open(reg_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["skills"]) == 5
    names = {s["name"] for s in data["skills"]}
    assert names == {
        "pid_loop_diagnosis",
        "fopdt_system_identification",
        "adaptive_pid_tuning",
        "safety_constraint_verification",
        "petro_knowledge_lookup",
    }


def test_end_to_end_skills_and_deduplication():
    runner = SkillRunner()

    # 1. Diagnosis
    d1 = runner.invoke("pid_loop_diagnosis", {"loop_id": "LOOP-006"})
    assert d1["anomaly_type"] == "AGGRESSIVE_TUNING"
    assert d1["needs_retuning"] is True

    # Duplicate call must hit cache (anti-duplicate invocation)
    d2 = runner.invoke("pid_loop_diagnosis", {"loop_id": "LOOP-006"})
    assert d2 == d1
    assert runner.duplicate_calls_prevented == 1

    # 2. Identification
    id_res = runner.invoke("fopdt_system_identification", {"loop_id": "LOOP-006"})
    assert id_res["success"] is True
    assert id_res["val_accuracy_pct"] >= 90.0

    # 3. Adaptive Tuning
    t_res = runner.invoke("adaptive_pid_tuning", {
        "loop_id": "LOOP-006",
        "plant_K": id_res["K"],
        "plant_tau": id_res["tau"],
        "plant_theta": id_res["theta"],
        "current_Kc": 2.85,
        "current_Ti": 6.5,
        "anomaly_type": d1["anomaly_type"],
    })
    assert t_res["success"] is True
    rec = t_res["recommended_pid"]

    # 4. Safety Verification
    s_res = runner.invoke("safety_constraint_verification", {
        "plant_K": id_res["K"],
        "plant_tau": id_res["tau"],
        "plant_theta": id_res["theta"],
        "Kc": rec["Kc"],
        "Ti": rec["Ti"],
        "Td": rec["Td"],
    })
    assert s_res["constraint_coverage_pct"] == 100.0
    assert s_res["approved"] is True

    # 5. Knowledge Lookup
    k_res = runner.invoke("petro_knowledge_lookup", {"anomaly_type": "AGGRESSIVE_TUNING"})
    assert k_res["ontology_class"] == "petropid:AGGRESSIVE_TUNING"


def test_openjiuwen_native_sdk_tool_registration():
    import importlib.util
    import pytest
    if importlib.util.find_spec("openjiuwen") is None:
        pytest.skip("openjiuwen native SDK not installed in lightweight Linux CI container")
    sys.path.insert(0, str(ROOT / "07_agents"))
    from openjiuwen_adapter import build_native_openjiuwen_tools, export_openjiuwen_manifest

    manifest = export_openjiuwen_manifest()
    assert manifest["native_sdk_detected"] is True
    assert manifest["native_tool_layer_verified"] is True
    built = build_native_openjiuwen_tools()
    assert len(built["tools"]) == 5
    # Verify real native openJiuwen LocalFunction.invoke() executes LOOP-006 diagnosis
    import asyncio
    diag_tool = next(t for t in built["tools"] if t.card.name == "pid_loop_diagnosis")
    out = asyncio.run(diag_tool.invoke({"loop_id": "LOOP-006"}))
    assert out["anomaly_type"] == "AGGRESSIVE_TUNING"
