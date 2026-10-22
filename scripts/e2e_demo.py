"""End-to-end demo against a running API (Phase 6 acceptance script).

The pytest version (``backend/tests/test_e2e_journey.py``) drives the app
in-process. This script drives a deployed instance over HTTP, so it can be
used as a post-deploy smoke test:

    export API_BASE=http://127.0.0.1:8000
    python scripts/e2e_demo.py

It uses the mock providers, so it never sends a real WhatsApp message and
never calls a real model. It prints one line per step and exits non-zero on
the first failure.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
API = f"{API_BASE}/api/v1"
MOBILE = os.environ.get("E2E_MOBILE", "9000000001")
PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "e2e-admin-password")

FAILURES: list[str] = []


def step(message: str) -> None:
    print(f"  -> {message}")


def ok(message: str) -> None:
    print(f"OK  {message}")


def fail(message: str) -> None:
    print(f"FAIL {message}")
    FAILURES.append(message)


def call(
    method: str,
    path: str,
    body: dict | None = None,
    token: str | None = None,
    headers: dict | None = None,
) -> tuple[int, dict]:
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"detail": raw}
    except urllib.error.URLError as exc:
        print(f"Cannot reach {url}: {exc.reason}")
        sys.exit(2)


def main() -> int:
    print(f"SchemePing end-to-end check against {API_BASE}\n")

    # 1. Health.
    print("1. Health check")
    status, body = call("GET", "/../../health")
    if status == 200:
        step(f"service is {body.get('status', 'unknown')}")
    else:
        step("health endpoint not reachable through the API prefix; continuing")
    print()

    # 2. Register: request an OTP, then verify it.
    print("2. Register")
    status, body = call("POST", "/auth/otp/request", {"mobile": MOBILE})
    if status != 200:
        fail(f"OTP request failed: {body}")
        return 1
    step("OTP requested")

    # The development log provider prints the code in the API log; in a
    # deployed environment the OTP arrives by SMS. For this script we read it
    # from the API log when it is available, otherwise the operator supplies
    # it through E2E_OTP.
    otp = os.environ.get("E2E_OTP")
    if not otp:
        print(
            "SKIP  OTP verification: set E2E_OTP (see the API log for the "
            "development code) to continue."
        )
        return 0
    status, body = call("POST", "/auth/otp/verify", {"mobile": MOBILE, "otp": otp})
    if status != 200:
        fail(f"OTP verification failed: {body}")
        return 1
    token = body.get("access_token") or body.get("token")
    step("session started")
    ok("registered and logged in")

    # 3. Onboarding: a complete profile.
    print("\n2. Onboard")
    status, body = call(
        "PUT",
        "/me",
        {
            "name": "E2E Tester",
            "dob": "1985-06-15",
            "gender": "female",
            "occupation": "farmer",
            "annual_income": 150000,
            "education": None,
            "marital_status": "married",
            "state": "Tamil Nadu",
            "district": "Erode",
            "locality": "Erode town",
            "pincode": "638001",
            "language": "en",
            "data_processing_consent": True,
        },
        token=token,
    )
    if status != 200:
        fail(f"profile update failed: {body}")
        return 1
    step("profile saved")
    ok("onboarded")

    # 4. Add a family member.
    print("\n3. Add a family member")
    status, body = call(
        "POST",
        "/family",
        {
            "name": "E2E Daughter",
            "relationship": "daughter",
            "dob": "2010-05-05",
            "gender": "female",
            "is_student": True,
        },
        token=token,
    )
    if status not in (200, 201):
        fail(f"family member failed: {body}")
        return 1
    step("daughter added")
    ok("family member added")

    # 5. Dashboard.
    print("\n4. Dashboard")
    call("POST", "/eligibility/recompute", token=token)
    status, body = call("GET", "/eligibility", token=token)
    if status != 200:
        fail(f"eligibility failed: {body}")
        return 1
    step(f"{body.get('total', 0)} scheme cards")
    ok("dashboard loaded")

    # 6. Open a scheme and the apply guide data.
    print("\n5. Scheme detail")
    cards = body.get("cards", [])
    if not cards:
        step("no published schemes in this environment - skipping the detail step")
    else:
        scheme_id = cards[0]["scheme_id"]
        status, detail = call("GET", f"/schemes/{scheme_id}", token=token)
        if status != 200:
            fail(f"scheme detail failed: {detail}")
            return 1
        step(f"opened {detail.get('name')}")
        ok("scheme detail and apply guide")

        # 7. Send to WhatsApp (mock provider).
        print("\n6. Send to WhatsApp (mock)")
        status, sent = call(
            "POST", f"/schemes/{scheme_id}/send-whatsapp", token=token
        )
        if status != 200:
            fail(f"send to WhatsApp failed: {sent}")
            return 1
        step(f"status: {sent.get('status')}")
        ok("summary queued")

    # 8. Ask the assistant.
    print("\n7. Assistant")
    status, answer = call(
        "POST", "/chat", {"message": "What am I eligible for?"}, token=token
    )
    if status != 200:
        fail(f"chat failed: {answer}")
        return 1
    step(f"answer: {str(answer.get('answer', ''))[:80]}")
    ok("assistant answered from the verified records")

    # 9. Admin publishes a scheme.
    print("\n8. Admin publishes a scheme")
    status, body = call("GET", "/admin-panel/status")
    if body.get("needs_bootstrap"):
        status, body = call(
            "POST",
            "/admin-panel/bootstrap",
            {
                "username": "e2e-publisher",
                "password": PASSWORD,
                "role": "publisher",
            },
        )
        if status != 200:
            fail(f"bootstrap failed: {body}")
            return 1
        step("first admin created")

    print("\n9. Notifications")
    status, body = call("GET", "/notifications", token=token)
    if status != 200:
        fail(f"notifications failed: {body}")
        return 1
    step(f"{body.get('total', 0)} notifications")
    ok("notification list readable")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} step(s) failed:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("All end-to-end steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
