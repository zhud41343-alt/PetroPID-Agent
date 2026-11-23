"""Unified LLM Gateway for PetroPID-Agent.

Supports:
1. OpenAI-compatible remote/local inference endpoints (DeepSeek, Qwen, Huawei Ascend MindIE / vLLM)
   configured via environment variables or project-root `.env` (gitignored):
   - PETROPID_LLM_BASE_URL
   - PETROPID_LLM_API_KEY
   - PETROPID_LLM_MODEL (default: Qwen2.5-7B-Instruct / deepseek-chat)
2. Zero-dependency deterministic industrial reasoning fallback when no API key is set,
   ensuring 100% reproducible offline execution and instant Demo response.

Note: LLM prose is strictly advisory; all safety gates and final statuses are computed
deterministically by `decision_engine.py` and can never be overridden by LLM output.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Dict, Any
import httpx


def _load_dotenv_if_allowed() -> None:
    """Load key=value pairs from project-root .env without overriding explicit env vars."""
    if os.getenv("PETROPID_LLM_DISABLE_DOTENV") == "1":
        return
    if ("pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST")) and os.getenv("PETROPID_LLM_ALLOW_IN_TESTS") != "1":
        return
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


class LLMGateway:
    def __init__(self) -> None:
        _load_dotenv_if_allowed()
        self.base_url = os.getenv("PETROPID_LLM_BASE_URL", "").strip()
        self.api_key = os.getenv("PETROPID_LLM_API_KEY", "").strip()
        self.model = os.getenv("PETROPID_LLM_MODEL", "Qwen2.5-7B-Instruct").strip()

    @property
    def mode(self) -> str:
        return "live_llm_api" if (self.base_url and self.api_key) else "deterministic_local_engine"

    def synthesize_decision(
        self,
        agent_role: str,
        system_prompt: str,
        structured_state: Dict[str, Any],
        fallback_text: str,
    ) -> Dict[str, Any]:
        """Generate natural-language engineering reasoning grounded in verified tool output."""
        if self.mode == "live_llm_api":
            t0 = time.perf_counter()
            try:
                url = self.base_url.rstrip("/") + "/chat/completions"
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": self.model,
                    "temperature": 0.1,
                    "max_tokens": 260,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": f"角色：{agent_role}\n请基于以下结构化工具计算结果给出简洁专业的工程决策结论（不超过120字）：\n{structured_state}",
                        },
                    ],
                }
                with httpx.Client(timeout=15.0) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                    return {
                        "mode": "live_llm_api",
                        "model": data.get("model") or self.model,
                        "request_id": data.get("id", ""),
                        "latency_ms": latency_ms,
                        "usage": data.get("usage", {}),
                        "reasoning": content,
                    }
            except Exception as exc:
                return {
                    "mode": "deterministic_local_engine",
                    "model": f"{self.model} (fallback-on-api-error)",
                    "fallback_reason": f"{type(exc).__name__}: {str(exc)[:120]}",
                    "reasoning": fallback_text,
                }

        return {
            "mode": "deterministic_local_engine",
            "model": f"{self.model} (offline-verified)",
            "reasoning": fallback_text,
        }
