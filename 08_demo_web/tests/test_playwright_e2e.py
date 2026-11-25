"""Real headless Chromium Playwright E2E regression for PetroPID-Agent HMI.

Runs in GitHub Actions CI (and locally when playwright + chromium are installed)
against a live local FastAPI/uvicorn instance (offline deterministic mode).
Verifies:
1. Initial LOOP-006 approval banner, audit PASS, enabled export buttons, single-line pill
2. Canonical rejection/warning loops (LOOP-012, LOOP-021 + phase portrait, LOOP-029)
3. P1-B Negative test: HTTP 500 clears stale state & disables export buttons
4. P1-A Negative test: Tampered SIMULATION_VALIDATED response without audit/constraints
   is blocked Fail-Closed (never rendered as green approval!)
5. View 2 Sandbox 1-click CSV samples (valid oscillatory 200 + malformed missing-op 400)
6. View 3 5-unit heatmap single-row layout at 1440x900 & 1366x768 + zero JS errors
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PORT = 18765
BASE_URL = f"http://127.0.0.1:{PORT}"


def _wait_for_server(timeout_s: float = 25.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/healthz", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.4)
    raise RuntimeError(f"Server at {BASE_URL} failed to start within {timeout_s}s")


def run_e2e() -> None:
    env = os.environ.copy()
    env["PETROPID_LLM_DISABLE_DOTENV"] = "1"
    env["PYTHONPATH"] = str(ROOT)

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--app-dir",
            str(ROOT / "08_demo_web"),
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_for_server()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()

            page_errors: list[str] = []
            console_errors: list[str] = []
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text)
                if msg.type == "error" and "Failed to load resource" not in msg.text
                else None,
            )

            # 1. Load home & verify LOOP-006 green approval state
            page.goto(BASE_URL, wait_until="networkidle")
            page.wait_for_function(
                "document.getElementById('statusBadge').textContent.includes('仿真通过')",
                timeout=15000,
            )
            banner_cls = page.locator("#riskBanner").get_attribute("class") or ""
            banner_txt = page.locator("#riskBanner").inner_text()
            assert "ok" in banner_cls and "danger" not in banner_cls, f"Unexpected banner: {banner_cls}"
            assert "11/11 约束通过" in banner_txt, f"Missing 11/11 in banner: {banner_txt}"
            assert "严禁未审批写入真实 DCS" in banner_txt
            assert "审计: PASS" in page.locator("#auditStrip").inner_text()
            assert not page.locator("#approvalBtn").is_disabled()
            assert not page.locator("#bundleBtn").is_disabled()

            # Verify .fp-delta pill stays single-line
            pill_box = page.locator(".fp-delta").first.bounding_box()
            assert pill_box and pill_box["height"] < 28, f"Faceplate pill wrapped: {pill_box}"

            # 2. Canonical LOOP-012: default V4.3.3 rejects -> switch to V4.3.4 approves with enhanced C-000 evidence!
            page.locator("#loopSearch").fill("LOOP-012")
            page.locator(".loop-row").first.click()
            page.wait_for_function(
                "document.getElementById('statusBadge').textContent.includes('模型未过')",
                timeout=15000,
            )
            assert "danger" in (page.locator("#riskBanner").get_attribute("class") or "")
            assert "petropid-alg-v4.3.3" in page.locator("#auditStrip").inner_text()

            # Switch to V4.3.4 profile -> LOOP-012 passes C-000 with observable DC load-step evidence
            page.locator("#profileSelect").select_option("v4.3.4")
            page.wait_for_function(
                "document.getElementById('statusBadge').textContent.includes('仿真通过')",
                timeout=15000,
            )
            assert "petropid-alg-v4.3.4" in page.locator("#auditStrip").inner_text()
            assert "审计: PASS" in page.locator("#auditStrip").inner_text()
            assert "增强 C-000 已触发" in page.locator("#profileEvidenceBar").inner_text()
            assert not page.locator("#approvalBtn").is_disabled()

            # Switch back to default V4.3.3 before continuing
            page.locator("#profileSelect").select_option("v4.3.3")
            page.wait_for_function(
                "document.getElementById('statusBadge').textContent.includes('模型未过')",
                timeout=15000,
            )

            # 3. Canonical LOOP-021 (VALVE_MAINTENANCE_REQUIRED + phase chart)
            page.locator("#loopSearch").fill("LOOP-021")
            page.locator(".loop-row").first.click()
            page.wait_for_function(
                "document.getElementById('statusBadge').textContent.includes('阀门粘滞')",
                timeout=15000,
            )
            page.locator(".c-tab[data-chart='phase']").click()
            page.wait_for_timeout(200)

            # 4. Canonical LOOP-029 (PERFORMANCE_NOT_IMPROVED)
            page.locator("#loopSearch").fill("LOOP-029")
            page.locator(".loop-row").first.click()
            page.wait_for_function(
                "document.getElementById('statusBadge').textContent.includes('外扰未改善')",
                timeout=15000,
            )

            # 5. P1-B Negative Test: HTTP 500 MUST clear stale state & disable export buttons
            def _fail_500(route):
                route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "injected_500"}))

            page.route("**/api/run/LOOP-006", _fail_500)
            page.locator("#loopSearch").fill("LOOP-006")
            page.locator(".loop-row").first.click()
            page.wait_for_function(
                "document.getElementById('statusBadge').textContent.includes('请求异常')",
                timeout=10000,
            )
            assert "danger" in (page.locator("#riskBanner").get_attribute("class") or "")
            assert "UNVERIFIED" in page.locator("#auditStrip").inner_text()
            assert page.locator("#approvalBtn").is_disabled(), "approvalBtn MUST be disabled after HTTP 500"
            assert page.locator("#bundleBtn").is_disabled(), "bundleBtn MUST be disabled after HTTP 500"
            page.unroute("**/api/run/LOOP-006", _fail_500)

            # 6. P1-A Negative Test: Tampered SIMULATION_VALIDATED payload missing audit/constraints
            #    MUST be blocked Fail-Closed (never rendered as green banner!)
            def _tampered_response(route):
                resp = route.fetch()
                payload = resp.json()
                payload["final_status"] = "SIMULATION_VALIDATED_PENDING_ENGINEERING_REVIEW"
                payload["audit_meta"]["audit_verification"] = {}
                payload["safety"] = {"constraint_audit": []}
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

            page.route("**/api/run/LOOP-006", _tampered_response)
            page.locator("#runBtn").click()
            page.wait_for_function(
                "document.getElementById('statusBadge').textContent.includes('审计未验')",
                timeout=15000,
            )
            tampered_cls = page.locator("#riskBanner").get_attribute("class") or ""
            tampered_txt = page.locator("#riskBanner").inner_text()
            assert "danger" in tampered_cls and "ok" not in tampered_cls, f"Tampered payload showed green: {tampered_cls}"
            assert "审批证据不完整" in tampered_txt
            assert "审计: UNVERIFIED" in page.locator("#auditStrip").inner_text()
            assert page.locator("#approvalBtn").is_disabled(), "approvalBtn MUST be disabled when audit_status != PASS"
            page.unroute("**/api/run/LOOP-006", _tampered_response)

            # 7. View 2 Sandbox 1-click CSV samples (valid 200 + malformed 400)
            page.locator(".nav-tab[data-view='view-sandbox']").click()
            page.locator("#csvSampleOsc").click()
            page.wait_for_function(
                "document.getElementById('sbAuditBody').querySelectorAll('tr').length >= 1",
                timeout=15000,
            )
            page.locator("#csvSampleBad").click()
            page.wait_for_function(
                "document.getElementById('sbStatus').textContent.includes('HTTP 400')",
                timeout=10000,
            )

            # 8. View 3 5-unit heatmap single-row layout at 1440x900 & 1366x768
            page.locator(".nav-tab[data-view='view-plant']").click()
            page.wait_for_selector(".hm-unit", timeout=10000)
            units = page.locator(".hm-unit")
            assert units.count() == 5, f"Expected 5 unit cards, got {units.count()}"
            ys = [units.nth(i).bounding_box()["y"] for i in range(5)]
            assert max(ys) - min(ys) < 5.0, f"5 unit cards did not align on 1 row at 1440x900: {ys}"
            plant_text = page.locator("#view-plant").inner_text()
            assert "运行健康 · 无需变更" in plant_text
            assert "HEALTHY_NO_CHANGE" not in plant_text

            # Also check 1366x768 laptop viewport renders without JS error
            page.set_viewport_size({"width": 1366, "height": 768})
            page.wait_for_timeout(200)
            ys_1366 = [units.nth(i).bounding_box()["y"] for i in range(5)]
            assert max(ys_1366) - min(ys_1366) < 5.0, f"5 unit cards wrapped at 1366x768: {ys_1366}"

            assert not page_errors, f"Uncaught page errors: {page_errors}"
            assert not console_errors, f"Console errors: {console_errors}"
            browser.close()
            print("PLAYWRIGHT_E2E_ALL_8_CHECKS_PASSED (1440x900 + 1366x768, 0 JS errors)")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    run_e2e()
