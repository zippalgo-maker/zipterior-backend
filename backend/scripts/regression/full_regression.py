#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BACKEND = Path(os.environ.get("ZIPTERIOR_BACKEND", "/srv/zipterior/backend")).resolve()
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import text
from app.core.database import SessionLocal
from app.core.security import hash_password

BASE_URL = os.environ.get("ZIPTERIOR_BASE_URL", "https://zipterior.kr").rstrip("/")
PASSWORD = "ZipteriorRegression123!"
RUN_TAG = f"reg{int(time.time())}"

class RegressionFailure(RuntimeError):
    pass

results: list[tuple[str, bool, str]] = []
created: dict[str, Any] = {}


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        raise RegressionFailure(f"{name}: {detail}")


def http(method: str, path: str, *, token: str | None = None, payload: Any = None, expected: tuple[int, ...] = (200,)) -> tuple[int, Any]:
    url = BASE_URL + path
    headers = {"Accept": "application/json", "User-Agent": "ZipteriorRegression/0.6.2"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8")
    except Exception as exc:
        raise RegressionFailure(f"HTTP {method} {path} 연결 실패: {exc}") from exc
    try:
        parsed = json.loads(body) if body else None
    except json.JSONDecodeError:
        parsed = body
    if status not in expected:
        raise RegressionFailure(f"HTTP {method} {path}: expected={expected}, actual={status}, body={parsed}")
    return status, parsed


def login(email: str) -> str:
    _, data = http("POST", "/api/v1/auth/login", payload={"email": email, "password": PASSWORD})
    token = (data or {}).get("access_token")
    if not token:
        raise RegressionFailure(f"로그인 토큰 없음: {email}")
    return token


def setup_test_identities() -> None:
    customer_email = f"{RUN_TAG}.customer@regression.zipterior.kr"
    company_email = f"{RUN_TAG}.company@regression.zipterior.kr"
    admin_email = f"{RUN_TAG}.admin@regression.zipterior.kr"
    password_hash = hash_password(PASSWORD)
    with SessionLocal() as s:
        try:
            ids = {}
            for role, email, name in [
                ("customer", customer_email, "회귀테스트고객"),
                ("company", company_email, "회귀테스트업체사용자"),
                ("super_admin", admin_email, "회귀테스트관리자"),
            ]:
                user_id = s.execute(text("""
                    INSERT INTO users (email,password_hash,name,role,status,marketing_agreed)
                    VALUES (:email,:password_hash,:name,:role,'active',FALSE)
                    RETURNING id
                """), {"email": email, "password_hash": password_hash, "name": name, "role": role}).scalar_one()
                ids[role] = int(user_id)

            company_id = s.execute(text("""
                INSERT INTO companies (
                    owner_user_id,name,slug,representative_name,phone,email,
                    sido,sigungu,eupmyeondong,latitude,longitude,status,
                    consultation_available,is_visible_on_map,approved_at
                ) VALUES (
                    :owner_user_id,:name,:slug,'회귀대표','010-0000-0620',:email,
                    '경기도','하남시','망월동',37.5665,127.1900,'active',TRUE,TRUE,NOW()
                ) RETURNING id
            """), {
                "owner_user_id": ids["company"],
                "name": f"회귀테스트인테리어-{RUN_TAG}",
                "slug": f"regression-{RUN_TAG}",
                "email": company_email,
            }).scalar_one()
            s.execute(text("""
                INSERT INTO company_members (company_id,user_id,member_role,status)
                VALUES (:company_id,:user_id,'owner','active')
            """), {"company_id": company_id, "user_id": ids["company"]})
            s.commit()
        except Exception:
            s.rollback()
            raise
    created.update({
        "customer_email": customer_email,
        "company_email": company_email,
        "admin_email": admin_email,
        "customer_id": ids["customer"],
        "company_user_id": ids["company"],
        "admin_id": ids["super_admin"],
        "company_id": int(company_id),
    })


def cleanup() -> None:
    if not created:
        return
    with SessionLocal() as s:
        try:
            estimate_id = created.get("estimate_id")
            admin_id = created.get("admin_id")
            company_id = created.get("company_id")
            emails = [created.get("customer_email"), created.get("company_email"), created.get("admin_email")]
            user_ids = [created.get("customer_id"), created.get("company_user_id"), created.get("admin_id")]
            if estimate_id:
                s.execute(text("DELETE FROM event_outbox WHERE aggregate_id=:aggregate_id AND aggregate_type='estimate_request'"), {"aggregate_id": str(estimate_id)})
                s.execute(text("DELETE FROM estimate_requests WHERE id=:id"), {"id": estimate_id})
            if admin_id:
                s.execute(text("DELETE FROM admin_action_logs WHERE admin_user_id=:id"), {"id": admin_id})
            if company_id:
                s.execute(text("DELETE FROM companies WHERE id=:id"), {"id": company_id})
            valid_emails = [x for x in emails if x]
            if valid_emails:
                s.execute(text("DELETE FROM auth_login_attempts WHERE email = ANY(:emails)"), {"emails": valid_emails})
            valid_ids = [int(x) for x in user_ids if x]
            if valid_ids:
                s.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": valid_ids})
            s.commit()
        except Exception as exc:
            s.rollback()
            print(f"WARN  TEST_DATA_CLEANUP_FAILED  {exc}", file=sys.stderr)


def route_inventory_check() -> None:
    # app.routes와 /openapi.json은 이 프로젝트의 실제 include_router 등록을
    # 신뢰성 있게 표현하지 않는 경우가 있어 route inventory 판정에 사용하지 않는다.
    # 필요한 각 APIRouter 자체의 routes를 직접 합산해 검증한다.
    from app.modules.auth.router import router as auth_router
    from app.modules.portfolios.public_router import router as public_portfolios_router
    from app.modules.public_map.router import router as public_map_router
    from app.modules.estimates.router import router as estimates_router
    from app.modules.notifications.router import router as notifications_router

    routers = [
        auth_router,
        public_portfolios_router,
        public_map_router,
        estimates_router,
        notifications_router,
    ]

    routes: set[tuple[str, str]] = set()
    for router in routers:
        for route in router.routes:
            path = getattr(route, "path", "")
            methods = getattr(route, "methods", set()) or set()
            for method in methods:
                routes.add((method.upper(), path))

    required = {
        ("POST", "/api/v1/auth/login"),
        ("GET", "/api/v1/portfolios"),
        ("GET", "/api/v1/public/map/viewport"),
        ("POST", "/api/v1/estimates"),
        ("POST", "/api/v1/admin/estimates/{estimate_id}/assign"),
        ("POST", "/api/v1/company/estimates/{estimate_id}/respond"),
        ("GET", "/api/v1/notifications"),
    }
    missing = sorted(required - routes)
    record(
        "ROUTE_INVENTORY",
        not missing,
        f"missing={missing}" if missing else f"required={len(required)}",
    )


def smoke_checks() -> None:
    _, h = http("GET", "/api/health")
    record("HEALTH", isinstance(h, dict) and h.get("status") == "ok")
    _, p = http("GET", "/api/v1/portfolios?limit=1&offset=0")
    record("PUBLIC_PORTFOLIOS", isinstance(p, dict) and "items" in p and "total" in p)
    _, m = http("GET", "/api/v1/public/map/viewport?zoom=15&north=38&south=37&east=128&west=126")
    record("PUBLIC_MAP", isinstance(m, dict))
    status, _ = http("GET", "/api/v1/estimates", expected=(401,))
    record("AUTH_GUARD_ESTIMATE", status == 401)
    status, _ = http("GET", "/api/v1/notifications", expected=(401,))
    record("AUTH_GUARD_NOTIFICATION", status == 401)


def upload_test_image(estimate_id: int, token: str) -> int:
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "regression.png"
        path.write_bytes(png)
        proc = subprocess.run([
            "curl", "-sS", "-w", "\n%{http_code}", "-X", "POST",
            f"{BASE_URL}/api/v1/estimates/{estimate_id}/images",
            "-H", f"Authorization: Bearer {token}",
            "-F", f"upload=@{path};type=image/png",
        ], capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            raise RegressionFailure(f"이미지 업로드 curl 실패: {proc.stderr}")
        body, status_text = proc.stdout.rsplit("\n", 1)
        if int(status_text) != 201:
            raise RegressionFailure(f"이미지 업로드 HTTP {status_text}: {body}")
        data = json.loads(body)
        return int(data["image"]["id"])


def e2e_estimate_flow() -> None:
    setup_test_identities()
    customer_token = login(created["customer_email"])
    company_token = login(created["company_email"])
    admin_token = login(created["admin_email"])

    for label, token, expected_role in [
        ("CUSTOMER_LOGIN", customer_token, "customer"),
        ("COMPANY_LOGIN", company_token, "company"),
        ("ADMIN_LOGIN", admin_token, "super_admin"),
    ]:
        _, me = http("GET", "/api/v1/auth/me", token=token)
        record(label, me.get("role") == expected_role, f"role={me.get('role')}")

    _, estimate = http("POST", "/api/v1/estimates", token=customer_token, payload={
        "title": f"회귀테스트 견적 {RUN_TAG}",
        "description": "v0.6.2 자동 Full Regression 테스트 데이터",
        "desired_budget_min": 30000000,
        "desired_budget_max": 50000000,
        "contact_method": "either",
        "allow_recommendations": True,
    }, expected=(201,))
    estimate_id = int(estimate["id"])
    created["estimate_id"] = estimate_id
    record("ESTIMATE_CREATE", estimate.get("status") == "submitted", f"id={estimate_id}")

    image_id = upload_test_image(estimate_id, customer_token)
    record("ESTIMATE_IMAGE_UPLOAD", image_id > 0, f"image_id={image_id}")
    _, deleted = http("DELETE", f"/api/v1/estimates/{estimate_id}/images/{image_id}", token=customer_token)
    record("ESTIMATE_IMAGE_DELETE", int(deleted.get("image_id", 0)) == image_id)

    _, assigned = http("POST", f"/api/v1/admin/estimates/{estimate_id}/assign", token=admin_token, payload={"company_ids": [created["company_id"]]})
    record("ESTIMATE_ADMIN_ASSIGN", created["company_id"] in assigned.get("assigned_company_ids", []))

    _, company_detail = http("GET", f"/api/v1/company/estimates/{estimate_id}", token=company_token)
    record("ESTIMATE_COMPANY_READ", int(company_detail.get("id", 0)) == estimate_id)

    _, viewed = http("POST", f"/api/v1/company/estimates/{estimate_id}/view", token=company_token)
    record("ESTIMATE_COMPANY_VIEW", viewed.get("assignment_status") == "viewed")
    _, responded = http("POST", f"/api/v1/company/estimates/{estimate_id}/respond", token=company_token)
    record("ESTIMATE_COMPANY_RESPOND", responded.get("assignment_status") == "responded")
    _, contracted = http("POST", f"/api/v1/company/estimates/{estimate_id}/contract", token=company_token)
    record("ESTIMATE_COMPANY_CONTRACT", contracted.get("estimate_status") == "contracted")

    _, admin_detail = http("GET", f"/api/v1/admin/estimates/{estimate_id}", token=admin_token)
    record("ESTIMATE_ADMIN_FINAL", admin_detail.get("status") == "contracted")

    _, notifications = http("GET", "/api/v1/notifications?limit=100&offset=0", token=customer_token)
    record("CUSTOMER_NOTIFICATIONS", int(notifications.get("total", 0)) >= 1, f"total={notifications.get('total')}")
    _, read_all = http("POST", "/api/v1/notifications/read-all", token=customer_token)
    record("NOTIFICATION_READ_ALL", isinstance(read_all, dict))

    with SessionLocal() as s:
        audit_count = int(s.execute(text("SELECT COUNT(*) FROM admin_action_logs WHERE admin_user_id=:id"), {"id": created["admin_id"]}).scalar_one())
        outbox_count = int(s.execute(text("SELECT COUNT(*) FROM event_outbox WHERE aggregate_id=:id"), {"id": str(estimate_id)}).scalar_one())
    record("AUDIT_LOG", audit_count >= 1, f"count={audit_count}")
    record("EVENT_OUTBOX", outbox_count >= 1, f"count={outbox_count}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="비파괴 Smoke Regression만 수행")
    args = parser.parse_args()
    print("=" * 64)
    print("ZIPTERIOR v0.6.2 FULL REGRESSION")
    print(f"BASE_URL={BASE_URL}")
    print(f"BACKEND={BACKEND}")
    print("MODE=" + ("SMOKE" if args.smoke else "FULL_E2E"))
    print("=" * 64)
    try:
        route_inventory_check()
        smoke_checks()
        if not args.smoke:
            e2e_estimate_flow()
    except Exception as exc:
        print(f"REGRESSION_ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if not args.smoke:
            cleanup()
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print("=" * 64)
    print(f"TOTAL: {len(results)}")
    print(f"PASS: {passed}")
    print(f"FAIL: {failed}")
    if failed == 0:
        print("FULL_REGRESSION_OK" if not args.smoke else "SMOKE_REGRESSION_OK")
        return 0
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
