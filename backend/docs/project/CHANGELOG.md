# ZIPTERIOR CHANGELOG

## v2.0.0 - Role Entry Separation

### 목적
ZIPTERIOR 운영 서비스의 사용자 유형별 진입 구조를 분리하여
일반고객, 회원사, 관리자가 하나의 햄버거 메뉴에서 전환되는 기존 구조를 제거한다.

### 변경 전
- zipterior.kr 메인 햄버거 메뉴에서 일반고객 / 회원사 / 관리자 모드 선택 가능
- 일반 서비스 화면에서 관리자 진입 가능
- 회원사 역시 일반 사용자 서비스 내부에서 진입
- 사용자 역할 전환 방식이 실제 운영 서비스의 UI/UX와 맞지 않음

### 변경 후
- zipterior.kr 메인 서비스는 일반 사용자 중심으로 구성
- 공개 햄버거 메뉴의 일반고객 / 회원사 / 관리자 역할 전환 UI 제거
- 관리자 진입 메뉴를 일반 사용자 화면에서 제거
- 관리자 로그인은 별도 진입 페이지로 분리
- 회원사는 별도의 파트너센터 진입 페이지로 분리
- 기존 회원사/관리자 Dashboard 기능은 유지

### 배포 검증
- Main menu role switch 제거: PASS
- Public menu 관리자 제거: PASS
- Partner entry: PASS
- Admin separate entry: PASS
- Existing dashboards preserved: PASS
- Frontend HTTP: PASS
- Backend Health: PASS

### 배포 결과
V200_DEPLOY_SUCCESS

### 배포 전 백업
/srv/zipterior/backups/releases/pre_v2.0.0_20260811_114613

### 설계 원칙
일반고객 서비스와 운영자용 서비스를 명확하게 분리한다.

Public Service
    └── 일반고객

Partner Center
    └── 회원사

Admin
    └── 관리자

## v2.0.1 - Signup Validation & Estimate UI Fix

### 목적
고객/회원사 회원가입 입력 검증과 실제 DB 중복확인,
견적문의 입력 UI를 운영 서비스 수준으로 보완한다.

### 변경 사항

#### 고객 로그인/회원가입
- 화면에서 "일반고객" 명칭 제거
- 이메일 중복확인 기능 추가
- 기존 DB 사용자 이메일 중복검사 로직 재사용
- 이메일 중복확인 성공 후 이메일을 수정하면 재확인 필요
- 비밀번호 정책 강화
  - 8자 이상
  - 영문 포함
  - 숫자 포함
  - 특수문자 포함
- 이름 입력 검증 강화
  - 한글/영문만 허용
  - 숫자/특수문자 차단
- 휴대폰 번호 입력 정규화
  - 사용자 입력값에서 숫자만 저장
  - 예: 010-3030-0809 → 01030300809

#### 업체회원 가입
- 업체명 필수
- 사업자등록번호 필수
- 이메일 필수
- 비밀번호/비밀번호 확인 필수
- 약관 동의 필수
- 담당자 이름 선택사항
- 담당자 연락처 선택사항
- Frontend/Backend validation 일치

#### 견적문의
- 요청사항 textarea 크기 조정
- 사용자 임의 resize 비활성화

### Backend
- 이메일 중복확인 API 추가
- 고객 회원가입 validation 강화
- 업체회원 가입 schema/service validation 수정

### 검증

V201_CHECK_EMAIL_ROUTE_OK
BACKEND_HEALTH_OK
V201_EMAIL_CHECK_API_OK
V201_CUSTOMER_UI_OK
V201_COMPANY_SIGNUP_OK
V201_HTTP_OK

Full E2E Regression
- TOTAL: 22
- PASS: 22
- FAIL: 0

CORE_FULL_REGRESSION_OK
V201_VERIFY_OK
V201_STABLE_BACKUP_OK
V201_DEPLOY_SUCCESS

### 배포 전 백업

/srv/zipterior/backups/releases/pre_v2.0.1_20260811_131637

## v2.0.2 - Frontend Cache Busting [PACKAGE PREPARED]

### 목적
기존 브라우저에서 이전 CSS/JS 캐시가 남아
최신 배포 내용이 즉시 반영되지 않는 문제를 방지한다.

### 변경 사항
- 로컬 CSS/JS 참조에 버전 쿼리스트링 적용
  - 예: app.js?v=2.0.2
  - 예: style.css?v=2.0.2
- HTML no-cache 메타 처리
- 기존 크롬 브라우저에서도 신규 배포 파일을 다시 요청하도록 개선
- Nginx 설정은 변경하지 않음

### 설계 원칙
향후 릴리스에서도 CSS/JS 변경 시
버전 기반 Cache Busting을 유지한다.

### Status
DEPLOYED / VERIFIED

## v2.0.3 - Sample Data Cleanup & UX Polish [PACKAGE PREPARED]

### 목적
운영 화면에 남아 있던 하드코딩 샘플 업체/포트폴리오 데이터를 제거하고
회원가입/견적 UI를 실제 사용환경에 맞게 보완한다.

### 변경 사항

#### Sample Data
- 하드코딩 샘플 업체 제거
- 자동 생성 샘플 포트폴리오 제거
- 가짜 시공건수 제거
- 기본 BEST 단지 샘플값 제거
- 문자열 ID 기반 기존 샘플 즐겨찾기 캐시 정리
- 실제 API에서 반환되는 업체/포트폴리오만 표시

#### 업체회원 가입 UI
- 담당자 이름 (선택) 표시
- 담당자 연락처 (선택) 표시
- 선택 문구는 작고 회색 보조 텍스트로 표현

#### 견적문의 UI
- 요청사항 textarea 가로폭 100%
- 고정 높이 적용
- resize 비활성화
- 기존 폼과 border/radius/spacing 통일

#### Cache
- v2.0.3 Cache Busting 적용

### 설계 원칙
운영 화면에 테스트용 업체/포트폴리오를 하드코딩하지 않는다.
실제 등록 데이터가 없으면 0건으로 표시한다.

### Status
DEPLOYED / VERIFIED

## v2.1.0 - Map Provider Abstraction + Kakao Maps

### 목적
Leaflet/OpenStreetMap 의존을 제거하고 Kakao Maps로 전환하면서, 향후 Naver Maps로 교체 가능한 Provider Adapter 구조를 도입한다.

### 변경 사항
- Leaflet JavaScript/CSS 제거
- OpenStreetMap/Overpass 단지 fallback 제거
- 프론트 하드코딩 아파트 단지 좌표 제거
- Kakao Maps JavaScript SDK 적용
- ZipteriorMapProvider Adapter 도입
- 지도/마커/HTML 마커/레이어/클러스터 기능을 Provider 인터페이스 뒤로 분리
- 일반/위성 지도 전환을 Kakao ROADMAP/HYBRID로 연결
- 단지 마커는 `/api/v1/public/map/markers?marker_type=complex&has_portfolio=true` 실데이터만 사용
- 승인된 포트폴리오가 없는 단지는 지도 마커 미노출
- 향후 NaverMapProvider 구현 시 DB 및 포트폴리오 데이터 구조를 그대로 유지할 수 있도록 지도 공급자 종속 코드를 분리

### 데이터 원칙
ZIPTERIOR DB의 단지 기준 데이터는 provider 고유 ID가 아니라 단지명/주소/latitude/longitude를 공통 기준으로 사용한다.

### 다음 단계
v2.1.1 - 포트폴리오 등록 시 Kakao 장소/주소 검색 → 단지 선택 → 좌표/주소 저장 → 관리자 승인 → 지도 마커 자동 생성

### 검증
- Kakao SDK: PASS
- Leaflet public dependency: REMOVED
- Hardcoded apartment fallback: 0
- Public Map API: PASS
- Backend Health: PASS
- Full E2E Regression: PASS
- Deployment: V210_DEPLOY_SUCCESS

### Predeploy Backup
/srv/zipterior/backups/releases/pre_v2.1.0_20260811_144344

## v2.1.1 - Kakao Portfolio Location & Custom Zoom

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

## v2.1.2 - Company Signup Reliability Fix

### 목적
업체회원 가입 버튼 클릭 후 아무 안내 없이 진행되지 않는 문제를 수정한다.

### 변경 사항
- 업체회원 비밀번호 특수문자 검증 정규식 오류 수정
- 가입 처리 중 버튼 상태 추가
- 가입 처리 중 안내 추가
- 성공 메시지 초록색 표시
- 실패 메시지 빨간색 표시
- 이메일 중복 오류 안내
- 입력값 검증 오류 안내
- 사업자등록번호 10자리 Frontend 검증
- 담당자 이름/연락처 Frontend 검증
- 예기치 않은 오류도 무반응으로 종료되지 않도록 처리
- signup 관련 JS cache version v2.1.2 적용

### 검증
- Company register API route PASS
- Signup status UI PASS
- Password validation PASS
- Frontend HTTP PASS
- Backend Health PASS
- Full E2E Regression PASS

### 배포 전 백업
/srv/zipterior/backups/releases/pre_v2.1.2_20260811_153303

### 상태
DEPLOYED / VERIFIED

## Maintenance - 2026-08-11 - Production Test Data Reset

### 목적
ZIPTERIOR 실제 회원가입 → 업체가입 → 관리자 승인 → 포트폴리오 등록 →
관리자 검수 → 지도 마커 노출 전체 흐름을 처음부터 검증하기 위해
기존 개발/테스트 사용자 및 업체 데이터를 초기화한다.

### 유지 계정
- user_id: 4
- email: zippalgo@naver.com
- role: super_admin
- status: active

### 삭제 범위
- 기존 테스트 일반회원
- 기존 테스트 업체회원
- 신규 QA 과정에서 생성했던 일반회원/업체회원
- 테스트 업체
- 업체 연결 포트폴리오
- 테스트 견적
- 테스트 채팅/알림/즐겨찾기 등 연관 사용자 데이터

### 초기화 결과
- users: 1
- companies: 0
- portfolios: 0
- super_admin id=4 유지
- Transaction COMMIT 완료
- FK 오류 없음

### 사전 DB 백업
/srv/zipterior/backups/manual/pre_member_reset_20260811_161007

### 다음 단계
v2.1.3 Admin Real Data & Navigation Fix

- 관리자 메뉴 클릭 동작 복구
- 관리자 대시보드 하드코딩 데이터 제거
- 승인대기 업체 실제 건수 연동
- 포트폴리오 검수 실제 건수 연동
- 견적 실제 건수 연동
- 업체가입 완료 후 화면 전환/상태 처리 보완

## v2.1.3 - Admin Real Data & Navigation Fix

### 목적
관리자 화면의 데모 잔재를 제거하고 실제 운영 데이터 및
관리자 메뉴 동작을 정상화한다.

### 변경 사항
- 관리자 대시보드 데모 안내 제거
- 전체 회원 실제 DB/API 연동
- 등록 업체 실제 DB/API 연동
- 포트폴리오 검수대기 실제 데이터 연동
- 진행중 견적 실제 데이터 연동
- 처리할 업무의 하드코딩 3건/4건/3건 제거
- 신규 업체 승인 실제 pending_companies 연동
- 관리자 메뉴 화면전환 로직 정리
- 업체목록 tbody 실제 API 전용으로 정리
- 업체가입 성공 후 버튼 상태를 '가입 완료'로 전환
- 자동로그인 실패 시 로그인 화면으로 명확히 이동
- Frontend cache version v2.1.3

### QA용 DB 초기화
- super_admin user_id=4 유지
- 기존 테스트 회원/업체/연관 데이터 초기화
- 초기 상태 users=1 / companies=0 / portfolios=0
- 실제 회원가입 흐름을 처음부터 재검증하기 위한 초기화

### 검증
- Production Health PASS
- Admin Real Data Wiring PASS
- Admin Demo Inventory PASS
- Admin Navigation Static Validation PASS
- Company Signup Flow PASS
- Frontend HTTP PASS
- Non-destructive SMOKE Regression PASS
- Clean DB State Preserved PASS

### Predeploy Backup
/srv/zipterior/backups/releases/pre_v2.1.3_20260811_163951

### Stable Backup
/srv/zipterior/backups/releases/stable_v2.1.3_20260811_163951

### Stable Database Backup
/srv/zipterior/backups/releases/stable_v2.1.3_20260811_163951/database_v2.1.3.dump

### 상태
DEPLOYED / VERIFIED

## v2.1.4 - Admin KPI & Navigation Runtime Fix

### 변경 사항
- 전체 회원 KPI = customer + company
- admin / super_admin 계정 KPI 제외
- portal.js customerData와 window.ZipteriorData 연결
- 관리자 메뉴/view 22개 연결 검증
- 관리자 frontend cache v2.1.4 적용

### 검증
- Backend Health PASS
- Member KPI PASS
- Customer Data Binding PASS
- Admin Navigation Integrity PASS
- DB Role Count PASS
- Frontend HTTP PASS
- Full Regression PASS

### Predeploy Backup
/srv/zipterior/backups/releases/pre_v2.1.4_20260811_170914

### Stable Backup
/srv/zipterior/backups/releases/stable_v2.1.4_20260811_170914

### Database Backup
/srv/zipterior/backups/releases/stable_v2.1.4_20260811_170914/database_v2.1.4.dump

### 상태
DEPLOYED / VERIFIED

## v2.1.8 - Portfolio Space & Complex/Apartment Type Management

### 변경 사항
- 포트폴리오 공간 `+같은 공간` 추가 및 동일 공간 바로 아래 삽입
- 공간 종류별 최소 1개 유지 및 마지막 공간 삭제 방지
- 면적/공사기간/공사금액 입력 단위 명확화
- 관리자 단지 추가 시 아파트 타입 동시 등록
- 단지+타입 일괄 생성 트랜잭션 및 rollback 검증
- 단지 상세 조회/수정 및 주소·좌표 재확보
- 아파트 타입 추가/수정/삭제
- 마지막 타입 삭제 방지 및 사용 중 타입 삭제 409 보호
- 업체 포트폴리오 단지 검색 및 등록/미등록 상태 표시
- 미등록 단지 등록 요청 모달 및 요청 처리 연동
- 등록 단지 선택 시 `apartment_types` 타입 목록 정상 연동
- 운영 CSS/JS 반영
- 운영 백엔드 반영

### 검증
- Production Health PASS
- Admin Complex API PASS
- Admin Complex With Types API PASS
- Company Portfolio Complex Search API PASS
- Apartment Type Loading PASS
- Transaction Commit/Rollback PASS
- 미등록 단지 요청 모달 PASS
- 운영 서비스 ACTIVE
- 운영 CSS/JS 반영 확인 PASS

### 상태
DEPLOYED / VERIFIED
