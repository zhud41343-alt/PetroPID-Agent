"""Pytest root configuration: default to offline deterministic mode.

Prevents local `.env` API keys from triggering live external LLM calls during
automated `pytest` runs (matching `.github/workflows/ci.yml`). Override with
`PETROPID_LLM_DISABLE_DOTENV=0` if live LLM testing is explicitly desired.
"""

import os

os.environ.setdefault("PETROPID_LLM_DISABLE_DOTENV", "1")
