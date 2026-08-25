# AI HANDOFF — ZIPTERIOR BACKEND

## Current state
- Version: v1.0.0
- Progress: 100%
- Status: Production Ready
- Previous stable: v0.6.3 Production Hardening
- Production cutover: APP_ENV=production / APP_DEBUG=false
- Runtime rate limit: enabled, 300 requests/minute/IP
- Full Regression must have passed during v1.0.0 deployment.

## Operating rules
1. Every future release must use precheck -> prebackup -> deploy -> verify -> regression -> stable backup.
2. Never expose or upload `.env` / `.env.backup*`.
3. Each release updates PROJECT_STATUS, PROJECT_DASHBOARD, VERSION, RELEASE_NOTES, SESSION_END and this AI_HANDOFF.
4. Show overall progress/version at the start of every development session.
5. Use router-direct + real HTTPS calls for route/API verification; do not rely on app.routes inventory.
6. Preserve `/srv/zipterior/releases/vX.Y.Z/` release packages and `/srv/zipterior/backups/` recovery points.

## Next session
Backend v1.0.0 is complete. Continue with frontend integration, operations monitoring, or a separately approved v1.x backend roadmap.

<!-- FRONTEND_V110_START -->

## Frontend Integration

- 전체 ZIPTERIOR 진행률: 100%
- 남은 작업: 0%
- Backend Core: v1.0.0 Production Ready
- Frontend Production Integration: 완료
- v1.1.0: 지도/단지/평형/포트폴리오/업체 실데이터
- v1.2.0: 고객 인증/MY집테리어
- v1.3.0: 회원사 실연동
- v1.4.0: 관리자 실연동
- v1.5.0: 견적 전체 사이클
- v1.6.0: 업체 즐겨찾기/채팅/프로필
- v1.7.0: 채팅 이미지 첨부/Final Integration QA
- v1.8.0: Production 인증 우회 및 Demo Cleanup
- v1.9.0: Membership/Packet/Partner/BEST 단지 실제 운영 데이터 전환
- Residual Mock Inventory: 0
- Full E2E Regression: 22/22 PASS
- Production Health: PASS
- DB Health: PASS

## Current Production Status

ZIPTERIOR current defined development scope is Production Ready.

## Next Session

신규 기능, 실제 사용자 피드백, UI/UX 개선 및 별도 확장 기능은 새로운 v2.x 제품 로드맵으로 관리한다.

## v2.x Development History

### v2.0.0 - Role Entry Separation
- 일반 서비스에서 사용자 역할 전환 UI 제거
- 공개 메뉴에서 관리자 진입 제거
- 회원사 Partner Center 별도 진입 구조 적용
- 관리자 별도 로그인 진입 구조 적용
- 기존 회원사/관리자 Dashboard 유지
- Production HTTP PASS
- Backend Health PASS
- Deployment: V200_DEPLOY_SUCCESS
- Predeploy Backup:
  /srv/zipterior/backups/releases/pre_v2.0.0_20260811_114613

### v2.0.1 - Signup Validation & Estimate UI Fix
- 고객 이메일 중복확인 API/UI 추가
- 비밀번호 정책 강화
- 고객 이름/휴대폰 입력 validation 강화
- 업체회원 필수/선택 입력 기준 정리
- 견적문의 textarea UI 보완
- Full E2E Regression: 22/22 PASS
- Deployment: V201_DEPLOY_SUCCESS
- Predeploy Backup:
  /srv/zipterior/backups/releases/pre_v2.0.1_20260811_131637

### v2.0.2 - Frontend Cache Busting [PACKAGE PREPARED]
- 기존 브라우저의 구버전 CSS/JS 캐시 문제 대응
- 로컬 CSS/JS 버전 쿼리 적용
- HTML no-cache 처리
- 향후 Frontend 릴리스에서 Cache Busting 유지

### v2.0.3 - Sample Data Cleanup & UX Polish [PACKAGE PREPARED]
- 하드코딩 샘플 업체 제거
- 하드코딩/자동생성 포트폴리오 제거
- 샘플 즐겨찾기 캐시 정리
- 실제 API 데이터만 표시
- 업체 담당자 선택사항 UI 표시
- 견적 요청사항 textarea UI 개선
- Cache Busting v2.0.3 적용

### v2.1.0 - Map Provider Abstraction + Kakao Maps
- Kakao Maps 운영 지도 전환
- Map Provider Adapter 구조 적용 (향후 Naver 교체 대비)
- Leaflet/OSM/Overpass 지도 의존 제거
- 하드코딩 아파트 위치 제거
- 승인 포트폴리오가 있는 실데이터 단지만 마커 표시
- Deployment: V210_DEPLOY_SUCCESS
- Predeploy Backup: /srv/zipterior/backups/releases/pre_v2.1.0_20260811_144344
- Next: v2.1.1 Kakao 단지/주소 검색 기반 포트폴리오 등록

### v2.1.1 - Kakao Portfolio Location & Custom Zoom

- 배포: 2026-08-11 15:06
- 포트폴리오 등록 시 카카오 단지명/주소 검색 및 검색결과 선택 적용
- 선택한 단지명/도로명·지번주소/위도/경도를 apartment_complexes에 저장 또는 재사용
- 포트폴리오는 complex_id로 단지와 연결
- 기존 관리자 검수/승인 흐름 유지
- 승인된 포트폴리오가 있는 단지만 기존 public map API를 통해 지도 마커 생성
- 기존 평/㎡ 컨트롤 디자인 및 동작 유지
- 카카오 기본 확대/축소 컨트롤 제거
- 평/㎡ 아래 ZIPTERIOR 스타일 세로형 + / - 컨트롤 추가
- Full E2E 및 배포 검증 수행
- Predeploy backup: /srv/zipterior/backups/releases/pre_v2.1.1_20260811_150637
- Stable backup: /srv/zipterior/backups/releases/stable_v2.1.1_20260811_150637
- Database backup: /srv/zipterior/backups/releases/stable_v2.1.1_20260811_150637/database_v2.1.1.dump

### v2.1.2 - Company Signup Reliability Fix
- 업체회원 가입 무반응 문제 수정
- 비밀번호 정규식 오류 수정
- 가입 성공/실패/처리중 UI 추가
- Full E2E Regression PASS
- Predeploy Backup:
  /srv/zipterior/backups/releases/pre_v2.1.2_20260811_153303

### Maintenance - 2026-08-11 - Production Test Data Reset
- 실제 가입/승인/포트폴리오 QA 전 테스트 데이터 초기화 완료
- super_admin user_id=4만 유지
- users=1
- companies=0
- portfolios=0
- DB Transaction COMMIT 완료
- Pre-reset DB Backup:
  /srv/zipterior/backups/manual/pre_member_reset_20260811_161007
- Next: v2.1.3 Admin Real Data & Navigation Fix

### v2.1.3 - Admin Real Data & Navigation Fix
- 관리자 대시보드 실데이터 전환
- 관리자 처리업무 데모 숫자 제거
- 관리자 navigation 정리
- 업체가입 완료 후 화면전환 흐름 보완
- QA DB 초기화: super_admin id=4만 유지
- Deploy/Verify 완료
- Predeploy Backup:
  /srv/zipterior/backups/releases/pre_v2.1.3_20260811_163951
- Stable Backup:
  /srv/zipterior/backups/releases/stable_v2.1.3_20260811_163951
- Database Backup:
  /srv/zipterior/backups/releases/stable_v2.1.3_20260811_163951/database_v2.1.3.dump

### v2.1.4 - Admin KPI & Navigation Runtime Fix
- 전체 회원: customer + company
- 관리자 계정 KPI 제외
- customerData runtime binding 수정
- 관리자 메뉴/view 22/22 검증
- Predeploy: /srv/zipterior/backups/releases/pre_v2.1.4_20260811_170914
- Stable: /srv/zipterior/backups/releases/stable_v2.1.4_20260811_170914
- DB Backup: /srv/zipterior/backups/releases/stable_v2.1.4_20260811_170914/database_v2.1.4.dump

## v2.1.8 FINAL - 2026-08-14

### 최종 완료 사항
- 포트폴리오 `+같은 공간` 추가 기능 완료
- 동일 공간 추가 시 해당 공간 바로 아래 삽입 완료
- 공간 종류별 최소 1개 유지 및 마지막 공간 삭제 방지 완료
- 면적/공사기간/공사금액 입력 단위 정리 완료
- 관리자 단지 추가 + 아파트 타입 등록 완료
- 단지+타입 일괄 생성 트랜잭션 및 rollback 검증 완료
- 단지 상세 조회/수정 완료
- 주소 수정 시 카카오 Geocoder 좌표 재확보 완료
- 아파트 타입 추가/수정/삭제 완료
- 마지막 타입 삭제 방지 완료
- 포트폴리오/견적 사용 중 타입 삭제 409 보호 확인
- 업체 포트폴리오 단지 검색 완료
- 등록/미등록 단지 상태 표시 완료
- 미등록 단지 등록 요청 모달 완료
- 단지 등록 요청 처리 후 등록단지 목록 반영 흐름 완료
- 등록 단지 선택 후 `apartment_types` 타입 목록 정상 표시 완료
- 운영 CSS/JS 반영 완료
- 운영 백엔드 반영 및 재시작 완료

### 최종 운영 검증
- `zipterior-api.service`: active
- `/api/health`: HTTP 200
- `/api/v1/admin/complexes`: GET/POST 확인
- `/api/v1/admin/complexes/with-types`: POST 확인
- `/api/v1/company/portfolios/complex-search`: POST 확인
- `/api/v1/public/apartment-types`: 실제 타입 조회 확인
- 단지+타입 transaction commit 검증 PASS
- transaction rollback 검증 PASS
- 미등록 단지 요청 모달 PASS
- 등록 단지 타입 로딩 PASS
- 운영 CSS/JS 반영 확인 PASS

### 백업
- 기존 Stable:
  `/srv/zipterior/backups/releases/stable_v2.1.8_20260814_144409`
- 최종 Stable 백업은 아래 최종 기록 이후 생성 예정

### 상태
V2.1.8 기능 완료 / 최종 Stable 백업 대기
