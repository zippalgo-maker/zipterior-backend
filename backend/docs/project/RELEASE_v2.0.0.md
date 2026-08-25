# ZIPTERIOR v2.0.0

## Release
Role Entry Separation

## Summary
ZIPTERIOR 일반 사용자 서비스와 회원사/관리자 운영 서비스의
진입 경로를 분리한 첫 v2.x UI/UX 구조 개선 버전.

## Changes

### Public
- 일반고객 / 회원사 / 관리자 역할 전환 UI 제거
- 관리자 메뉴 공개 영역에서 제거
- 일반 사용자 중심 서비스 구조로 변경

### Partner
- 회원사 전용 Partner Center 진입 구조 추가
- 기존 회원사 Dashboard 유지

### Admin
- 관리자 별도 진입 구조 적용
- 일반 서비스에서 관리자 진입 제거
- 기존 Admin Dashboard 유지

## Verification

V200_MAIN_ROLE_SWITCH_REMOVED_OK
V200_ADMIN_PUBLIC_MENU_REMOVED_OK
V200_PARTNER_ENTRY_OK
V200_ADMIN_ENTRY_OK
V200_DASHBOARDS_PRESERVED_OK
V200_HTTP_OK
BACKEND_HEALTH_OK
V200_VERIFY_OK
V200_STABLE_BACKUP_OK
V200_DEPLOY_SUCCESS

## Predeploy Backup

/srv/zipterior/backups/releases/pre_v2.0.0_20260811_114613

## Status

DEPLOYED / VERIFIED
