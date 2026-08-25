# ZIPTERIOR PROJECT HISTORY

## v2.1.5 - 2026-08-12 13:58:57

- Clean URL 체계 정리
  - /login
  - /signup
  - /my
  - /my/profile
  - /partner
  - /partner/signup
  - /partner/dashboard
  - /admin
  - /admin/dashboard
- 기존 .html URL 301 리다이렉트 처리
- auth.html, mobileindex.html, partner/index.html, partner/signup.html, admin/index.html 제거
- mobileindex.html은 410 Gone 처리
- HTML 캐시 비활성화 및 정적 자산 버전 v2.1.5 통일
- 업체회원 가입 이메일 중복확인 기능 추가
- 담당자 이름/연락처 선택 입력 유지
- 기존 비밀번호 검증 및 가입 흐름 유지
- Nginx 문법검사 통과
- Full Regression 22/22 통과

## v2.1.5 최종 배포 완료 - 2026-08-12 14:26:10

### 배포 결과
- v2.1.5 운영 배포 완료
- 배포 완료 시각: 2026-08-12 14:10:41 +0900
- Full Regression: 22/22 PASS
- V215_VERIFY_OK 확인
- 운영 Clean URL 최종 HTTP 검증 완료

### URL 구조 정리
- /login
- /signup
- /my
- /my/profile
- /partner
- /partner/signup
- /partner/dashboard
- /admin
- /admin/dashboard
- 위 Clean URL 모두 HTTP 200 확인
- 기존 .html 주소는 Clean URL로 301 Redirect 확인
- /mobileindex.html은 410 Gone 처리 확인

### 캐시 정책
- HTML no-cache 적용
- Cache-Control: no-cache, no-store, must-revalidate 확인
- 프런트 정적 자산 버전 v2.1.5 통일

### 업체회원 가입
- 이메일 중복확인 UI/API 연결
- 중복확인 완료 전 회원가입 방지
- 이메일 변경 시 중복확인 상태 초기화
- 담당자 이름/연락처 선택 입력 유지
- 비밀번호 영문/숫자/특수문자 검증 유지

### DB 백업 개선
- 기존 pg_dump가 Linux 사용자 zipterior로 접속하여 실패하는 문제 확인
- 실제 PostgreSQL ROLE zipterior_app 사용
- backend/.env의 DATABASE_* 설정을 이용하도록 배포 스크립트 수정
- .env 직접 source 방식은 쉘 비호환 값 때문에 제거
- Python 기반 안전한 DATABASE_* 파서 적용
- pg_dump 실제 생성 테스트 PASS
- pg_restore -l dump 유효성 검사 PASS

### 배포 백업
- 배포 전 백업:
  /srv/zipterior/backups/releases/v2.1.5_before_20260812_141038
- 첫 실패 배포 백업 보존:
  /srv/zipterior/backups/releases/failed_v2.1.5_before_20260812_140009
- v2.1.5 Stable 기준 백업:
  /srv/zipterior/backups/releases/stable_v2.1.5_20260812_142245
- Stable 백업 구성:
  frontend + nginx.conf + PostgreSQL dump
- Stable DB dump pg_restore 검증 PASS

### 현재 운영 기준
- 현재 정상 운영 기준 버전: v2.1.5
- 향후 수정 작업의 복구 기준:
  stable_v2.1.5_20260812_142245

## v2.1.5 Clean URL MIME Hotfix - 2026-08-12 14:51:36

### 장애
- /partner 등 Clean URL 접속 시 브라우저에서 HTML 화면 대신 파일 다운로드 발생
- 원인: Nginx alias로 확장자 없는 Clean URL에 HTML 파일을 연결하면서
  Content-Type이 application/octet-stream으로 응답됨
- 초기 검증이 HTTP 200만 확인하여 MIME 오류를 잡지 못함

### 수정
- Clean URL 9개 location에 default_type text/html 추가
- 적용 대상:
  /login
  /signup
  /my
  /my/profile
  /partner
  /partner/signup
  /partner/dashboard
  /admin
  /admin/dashboard
- Nginx syntax 검사 PASS
- Nginx reload PASS

### 검증 강화
- Clean URL 9개 모두 HTTP 200 + Content-Type text/html 확인
- 실제 브라우저에서 파트너 로그인 화면 정상 표시 확인
- verify.sh의 Clean URL 검증을 HTTP 상태 + HTML MIME 검증으로 강화
- Full Regression 22/22 PASS
- COMPANY_LOGIN role=company PASS

### 백업
- MIME 수정 전 Stable:
  /srv/zipterior/backups/releases/superseded_v2.1.5_20260812_142245_mime_issue
- MIME Hotfix 전 Nginx 백업:
  /srv/zipterior/backups/releases/nginx_before_v215_mime_hotfix_20260812_143627.conf
- 최종 정상 Stable:
  /srv/zipterior/backups/releases/stable_v2.1.5_20260812_145044
- 최종 Stable DB dump pg_restore 검증 PASS

### 현재 기준
- 현재 운영 기준 버전: v2.1.5
- 향후 복구 기준:
  stable_v2.1.5_20260812_145044

## v2.1.6 관리자 회원관리 개선 완료 - 2026-08-12 16:20:41

### 목적
- 관리자 회원관리 메뉴 진입 시 해당 회원유형 목록이 즉시 보이도록 개선
- 기존 '초기화' 중심 필터를 '조회' 방식으로 변경
- 업체회원의 실제 멤버십 등급을 관리자 회원목록에 표시
- 회원 수 100명 초과 시에도 전체 회원을 불러올 수 있도록 개선

### 기존 문제
- 일반회원/업체회원/관리자 메뉴 클릭 시 회원유형 필터는 한글값으로 설정됐으나
  회원 목록에는 DB role(customer/company/super_admin)이 그대로 표시되어 필터가 일치하지 않음
- 필터 input/change 이벤트가 즉시 실행되어 메뉴 진입 직후 회원 목록이 숨겨지는 문제 발생
- '초기화' 버튼을 눌러야 회원이 다시 보이는 비정상 UX
- 회원 검색창이 상단 필터와 회원목록 헤더에 중복 존재
- 업체회원 세부등급이 실제 DB 멤버십 데이터와 연결되지 않음
- 관리자 회원 API가 한 번에 최대 100명만 반환

### 프론트 수정
- 일반회원 관리 클릭:
  일반회원 전체 즉시 표시
- 업체회원 관리 클릭:
  업체회원 전체 즉시 표시
- 관리자 관리 클릭:
  관리자 전체 즉시 표시
- 회원 메뉴 이동 시 검색어/세부등급/상태 필터 초기화 후 해당 회원유형 자동 적용
- 회원관리 필터는 input/change 즉시 적용하지 않고 '조회' 버튼 클릭 시 적용
- 회원관리의 '초기화' 버튼을 '조회'로 변경
- 중복 adminMemberSearch 제거
- role 표시 변환:
  customer -> 일반회원
  company -> 업체회원
  admin/super_admin -> 관리자
- 관리자 화면 JS cache version 2.1.6 적용
- 전체 회원을 100명 단위 offset pagination으로 끝까지 불러오도록 loadAllAdminUsers 추가

### 실제 업체 멤버십 연동
- /admin/users 응답에 아래 필드 추가:
  membership_plan
  membership_display_name
  membership_status
- 업체회원은 다음 실제 DB 관계를 사용:
  users
  -> company_members
  -> company_memberships
  -> membership_plans
- 일반회원/관리자는 membership 필드 null
- 업체 멤버십이 없으면 관리자 화면에서 '미설정'
- 세부등급 필터는 실제 membership_display_name 데이터 기준으로 동적 생성

### 실제 DB 검증
- 업체회원 user_id=66
- 업체명: 집팔고디자인
- user role: company
- user status: pending
- membership_plan: launch_partner
- membership_display_name: 런칭 파트너
- membership_status: active
- 패치 repository 직접 DB 조회 PASS
- 운영 backend 배포 후 동일 데이터 조회 PASS

### 검증
- v2.1.6 precheck 8/8 PASS
- Backend Python syntax PASS
- 실제 Membership DB query PASS
- 운영 backend health PASS
- 배포 파일 patch/live 일치 확인 PASS
- Full Regression:
  TOTAL 22
  PASS 22
  FAIL 0
- 브라우저 실제 관리자 화면 확인:
  일반회원 메뉴 자동조회 정상
  업체회원 메뉴 자동조회 정상
  관리자 메뉴 자동조회 정상
  업체회원 '런칭 파트너' 표시 정상

### 변경 파일
Backend:
- app/modules/admin/overview_schemas.py
- app/modules/admin/overview_repository.py

Frontend:
- admin-dashboard.html
- js/admin-api.js
- js/portal.js

### 배포 전 백업
/srv/zipterior/backups/releases/v2.1.6_before_20260812_160506

### 최종 Stable
/srv/zipterior/backups/releases/stable_v2.1.6_20260812_161827

### 다음 작업 v2.1.7
1. 관리자 좌측 세부메뉴 현재 선택 항목 active 색상 표시
2. 신규 업체회원 관리자 승인 절차 제거
3. 업체회원 가입 즉시 활동 가능하도록 권한/상태 로직 수정
4. 업체회원 또는 관리자가 실제 포트폴리오 등록
5. 일반회원에서 등록 포트폴리오 확인
6. 지도 화면에서 해당 단지/포트폴리오 검색 및 상세 노출 E2E 테스트
