# ZIPTERIOR v2.0.1

## Release
Signup Validation & Estimate UI Fix

## Summary
고객/회원사 가입 검증과 이메일 중복확인,
견적문의 입력 UI를 운영 환경에 맞게 보완한 버전.

## Major Changes
- 고객 이메일 중복확인
- 비밀번호 정책 강화
- 이름/휴대폰 validation
- 업체회원 필수/선택 항목 정리
- 견적 요청사항 textarea UI 보완

## Verification

V201_CHECK_EMAIL_ROUTE_OK
BACKEND_HEALTH_OK
V201_EMAIL_CHECK_API_OK
V201_CUSTOMER_UI_OK
V201_COMPANY_SIGNUP_OK
V201_HTTP_OK
FULL_REGRESSION_OK
TOTAL 22 / PASS 22 / FAIL 0
V201_VERIFY_OK
V201_STABLE_BACKUP_OK
V201_DEPLOY_SUCCESS

## Predeploy Backup

/srv/zipterior/backups/releases/pre_v2.0.1_20260811_131637

## Status

DEPLOYED / VERIFIED
