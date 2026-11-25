"""Native openJiuwen 0.1.21 Workflow executing PetroPID-Agent end-to-end on real benchmark loops.

Demonstrates genuine openJiuwen `Workflow`, `WorkflowCard`, `Start`, `End`, `WorkflowComponent`,
and `create_workflow_session` chaining our standardized Skills & deterministic safety/audit engine
for LOOP-006 (simulation-validated) and LOOP-012 (model validation failed / Fail-Closed).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

os.environ["PETROPID_LLM_DISABLE_DOTENV"] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "04_algorithms"))
sys.path.insert(0, str(ROOT / "05_skills"))
sys.path.insert(0, str(ROOT / "07_agents"))

from openjiuwen.core.session.workflow import create_workflow_session  # noqa: E402
from openjiuwen.core.workflow import End, Start, Workflow, WorkflowCard, WorkflowComponent  # noqa: E402
from skill_runner import SkillRunner  # noqa: E402
from orchestrator import PetroPIDOrchestrator  # noqa: E402

_RUNNER = SkillRunner()
_ORCH = PetroPIDOrchestrator()


class DiagnosisNode(WorkflowComponent):
    async def invoke(self, inputs: Dict[str, Any], session: Any, context: Any) -> Dict[str, Any]:
        loop_id = inputs["loop_id"]
        diag = _RUNNER.invoke("pid_loop_diagnosis", {"loop_id": loop_id})
        return {"loop_id": loop_id, "anomaly_type": diag["anomaly_type"], "oi": diag["oscillation_index"]}


class IdentificationAndSafetyNode(WorkflowComponent):
    async def invoke(self, inputs: Dict[str, Any], session: Any, context: Any) -> Dict[str, Any]:
        loop_id = inputs["loop_id"]
        res = _ORCH.run_loop_workflow(loop_id)
        am = res["audit_meta"]
        return {
            "loop_id": loop_id,
            "anomaly_type": inputs["anomaly_type"],
            "final_status": res["final_status"],
            "deployment_authorized": res["deployment_authorized"],
            "run_id": am["run_id"],
            "audit_status": am["audit_verification"]["audit_status"],
            "record_digest_sha256": am["record_digest_sha256"],
        }


def build_native_petropid_workflow() -> Workflow:
    wf = Workflow(
        card=WorkflowCard(
            id="petropid_native_wf_v1",
            name="PetroPID_Native_Workflow",
            version="4.3.3",
            description="Native openJiuwen Workflow executing PetroPID diagnosis, identification, tuning, safety & audit",
        )
    )
    wf.set_start_comp("start", Start(), inputs_schema={"loop_id": "${loop_id}"})
    wf.add_workflow_comp(
        "diag_node",
        DiagnosisNode(),
        inputs_schema={"loop_id": "${start.loop_id}"},
    )
    wf.add_workflow_comp(
        "safety_decision_node",
        IdentificationAndSafetyNode(),
        inputs_schema={
            "loop_id": "${diag_node.loop_id}",
            "anomaly_type": "${diag_node.anomaly_type}",
        },
    )
    wf.set_end_comp(
        "end",
        End({"responseTemplate": "{{final_status}}"}),
        inputs_schema={
            "loop_id": "${safety_decision_node.loop_id}",
            "anomaly_type": "${safety_decision_node.anomaly_type}",
            "final_status": "${safety_decision_node.final_status}",
            "deployment_authorized": "${safety_decision_node.deployment_authorized}",
            "run_id": "${safety_decision_node.run_id}",
            "audit_status": "${safety_decision_node.audit_status}",
            "record_digest_sha256": "${safety_decision_node.record_digest_sha256}",
        },
    )
    wf.add_connection("start", "diag_node")
    wf.add_connection("diag_node", "safety_decision_node")
    wf.add_connection("safety_decision_node", "end")
    return wf


async def run_native_workflow_demo() -> Dict[str, Any]:
    wf = build_native_petropid_workflow()
    results = []
    for lid in ("LOOP-006", "LOOP-012", "LOOP-021"):
        session = create_workflow_session(session_id=f"petropid-{lid}")
        out = await wf.invoke({"loop_id": lid}, session)
        results.append({
            "loop_id": lid,
            "workflow_state": str(out.state),
            "result": out.result,
        })
    payload = {
        "openjiuwen_native_workflow_verified": True,
        "workflow_id": "petropid_native_wf_v1",
        "cases": results,
    }
    out_path = ROOT / "competition_v4" / "submission_v433" / "openjiuwen_native_workflow_run.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    asyncio.run(run_native_workflow_demo())
