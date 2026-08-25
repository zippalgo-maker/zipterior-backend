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

## v2.1.8 현재 운영 상태 및 작업 종료 기준 - 2026-08-14

### 현재 운영 버전
- v2.1.8
- 운영 Backend: /srv/zipterior/backend
- 운영 Frontend: /var/www/zipterior
- 운영 DB: zipterior_db
- 운영 API: 127.0.0.1:8000
- DB timezone: Asia/Seoul

### 이번 작업에서 완료 및 검증된 기능
- 업체의 미등록 단지 등록 요청 기능
- 관리자 단지 등록 요청 목록 조회
- 관리자에서 기존 단지를 선택하여 등록 요청 완료 처리
- complex_registration_requests 상태 및 completed_complex_id DB 반영 검증
- 테스트 DB(zipterior_test) API 검증
- 운영 Backend 배포 및 API health 정상 확인
- 관리자 단지 등록 관련 프론트 기능 운영 반영
- 관리자 Toast가 모달 뒤에 표시되는 문제 수정
- .toast-ui z-index 100 -> 1100 수정
- Toast 수정 후 실제 브라우저에서 모달 위 정상 표시 확인

### 주요 검증
- 테스트 API health PASS
- 운영 API health PASS
- 단지 등록 요청 API 인증 조회 PASS
- 단지 등록 요청 완료 API PASS
- complex_registration_requests DB 완료 상태 PASS
- Python compileall PASS
- 운영 브라우저 Toast 표시 PASS

### Stable 백업
- /srv/zipterior/backups/releases/stable_v2.1.8_20260814_144409
- backend 포함
- frontend 포함
- database/zipterior_db.dump 포함
- nginx.conf 포함
- DB dump pg_restore 목록 검증 PASS

### 작업 상태 관리 원칙
- 이 문서를 이후 ZIPTERIOR 새 채팅 작업의 현재 상태 기준점으로 사용한다.
- 이미 완료 및 검증된 작업은 다시 작업 대상으로 잡지 않는다.
- 이전 작업 목록을 현재 미완료 목록으로 임의 재사용하지 않는다.
- 상태가 기록으로 확인되지 않는 항목은 실제 서버 상태를 확인한 후 판단한다.
- 다음 작업은 별도의 현재 상태 확인 후 확정한다.

## [중요 상태 정정] v2.1.8 개발 계속 진행 - 2026-08-14

### 이전 기록 정정
- 앞서 기록된 "v2.1.8 현재 운영 상태 및 작업 종료 기준"은 v2.1.8 전체 기능의 최종 완료를 의미하는 것으로 해석해서는 안 된다.
- 해당 기록 이후 실제 운영 사이트를 이용한 E2E 검증에서 단지 → 타입 → 포트폴리오 → 승인 → 일반 공개 → 지도까지의 전체 업무 흐름이 아직 완전히 연결되지 않은 것이 확인되었다.
- 따라서 현재 버전은 **v2.1.8 개발 진행 중**으로 유지한다.
- **v2.1.9 개발은 v2.1.8 전체 업무 흐름의 구현 및 E2E 검증 완료 후에 시작한다.**

### 현재 v2.1.8 완료 상태
- 관리자 단지 기본정보 등록 기능: 구현 및 동작 확인
- 업체 미등록 단지 등록 요청 API: 구현 및 테스트 완료
- 관리자 단지 등록 요청 목록 조회: 구현 및 테스트 완료
- 관리자 기존 단지 연결을 통한 등록 요청 완료 처리: 구현 및 DB 검증 완료
- 관리자 단지 상세/타입 관련 기능: 구현 상태 확인 필요
- 포트폴리오 등록 화면의 단지 검색: 동작하나 집테리어 관리 단지와의 연결/상태 표시 확인 필요
- Toast z-index 수정: 운영 반영 및 브라우저 검증 완료
- 운영 API health: PASS
- 테스트 DB API 검증: PASS
- Python compileall: PASS

### 현재 확인된 미완료/검증 필요 연결
1. 업체 포트폴리오 등록의 아파트 검색 결과를 집테리어의 apartment_complexes와 정확하게 연결
2. 검색 결과에서 집테리어 단지 기본정보 등록 여부를 명확하게 표시
3. 미등록 단지 선택 시 단지 등록 요청 기능을 업체 UI에서 실제 검색 흐름에 연결
4. 등록된 집테리어 단지 선택 시 관리자 등록 apartment_types를 업체 포트폴리오 등록 화면에 표시
5. 업체 포트폴리오 저장 시 실제 complex_id 및 apartment_type_id 연결 검증
6. 관리자 포트폴리오 승인 후 approved 데이터가 public API에 정상 반영되는지 검증
7. 일반 사용자 화면에서 승인된 포트폴리오가 해당 단지/타입과 함께 노출되는지 검증
8. 지도에서 집테리어 등록 단지 및 타입/포트폴리오가 정상 노출되는지 검증
9. 관리자 → 업체 → 관리자 승인 → 일반 사용자 전체 E2E 검증

### 버전 운영 원칙
- 위 항목들은 모두 **v2.1.8 작업 범위**로 취급한다.
- 위 항목이 완료되고 실제 운영 E2E 검증까지 PASS한 후에만 v2.1.8을 최종 완료 처리한다.
- 그 전에는 v2.1.9 작업을 시작하지 않는다.
- `/srv/zipterior/backups/releases/stable_v2.1.8_20260814_144409`는 현재까지의 복구용 Stable 스냅샷으로 보존한다.
- Stable 백업 존재 여부와 개발 버전 완료 여부를 동일한 의미로 해석하지 않는다.
- 다음 작업 시작 시 반드시 이 상태 정정 섹션을 우선 기준으로 확인한다.

## v2.1.9 FINAL

v2.1.9은 FINAL / STABLE / VERIFIED 상태로 마감.

주요 완료:
1. apartment_types.floor_plan_path 기반 실제 평면도 사용
2. 관리자 단지 타입 생성/수정에서 평면도 업로드 가능
3. 사용자 타입 상세에서 등록 평면도 노출
4. 공개 포트폴리오 노출 문제 수정
5. 공개 포트폴리오에 supply_area_m2 / exclusive_area_m2 제공
6. 지도 부채살 ㎡/평 단위 표시
7. portfolio_spaces.description 사용자 상세 노출
8. portfolio_images.portfolio_space_id 기준으로 공간과 이미지 연결
9. 방1/방2/+같은 공간 등 동일 room_code 공간도 개별 구분 가능

운영 Frontend:
/var/www/zipterior

운영 Backend:
/srv/zipterior/backend

환경파일:
/srv/zipterior/backend/.env

v2.1.9 Release:
/srv/zipterior/releases/v2.1.9/zipterior_release_v2.1.9

v2.1.8 Stable은 이전 복구지점으로 보존.



## v2.2.0 FINAL - 2026-08-18

v2.2.0 기능 구현 및 운영 브라우저 검증 완료.

주요 완료:
1. 관리자 단지등록 주소검색 UI/UX 개선
2. Kakao 주소/좌표 자동입력
3. 단지등록 요청 기존 단지 자동연결
4. 미등록 요청 신규 단지 생성 + 요청완료 일괄 처리
5. 등록요청 신규 모달 주소 상세정보 자동확정
6. + 타입 추가 버튼 단독 sticky 및 sticky 상태 CI Red 표시
7. 일반/업체/관리자 로그인 세션 분리 및 동시 유지
8. 포트폴리오 0건 등록 단지 지도 마커 노출

Release:
/srv/zipterior/releases/v2.2.0/zipterior_release_v2.2.0

Pre Rollback:
/srv/zipterior/backups/releases/pre_v2.2.0_20260818_092045

Stable 백업 생성 및 검증 후 FINAL / STABLE / VERIFIED 확정.


## v2.2.0 FINAL / STABLE / VERIFIED - 2026-08-18

v2.2.0 최종 마감 완료.

최종 Stable:
/srv/zipterior/backups/releases/stable_v2.2.0_final_20260818_133641

Release:
/srv/zipterior/releases/v2.2.0/zipterior_release_v2.2.0

완료 기능:
- 관리자 단지 추가 주소검색 UX 개선
- Kakao 기반 주소/행정구역/지번/위경도 자동입력
- 업체 단지등록 요청 기존 단지 자동 연결
- 미등록 단지 신규등록 후 요청 자동 완료
- 등록요청 신규등록 시 추가 주소선택 단계 제거
- + 타입 추가 버튼 단독 sticky
- sticky 상태 연한 CI Red 표시
- 일반/업체/관리자 로그인 동시 유지
- 포트폴리오 0건 등록 단지 지도 마커 노출

Stable 검증:
- PostgreSQL dump PASS
- pg_restore 목록 검증 PASS
- Frontend PASS
- Backend PASS
- nginx.conf PASS

현재 개발 작업 없음.
다음 개발은 v2.2.0을 완료 기준으로 새 버전에서 시작한다.


## v2.2.1 FINAL / STABLE / VERIFIED - 2026-08-18

v2.2.1 버전 메타데이터 정합성 유지보수 Release 완료.

변경:
- 운영 Backend `.env`의 `APP_VERSION`을 1.0.0에서 2.2.1로 변경
- Backend 설정 fallback 버전을 0.1.0에서 2.2.1로 변경
- `/api/health`와 OpenAPI가 동일하게 2.2.1을 표시하도록 통일

변경하지 않은 범위:
- Frontend 및 정적 자산 캐시 버전
- PostgreSQL DB 구조와 데이터
- 기존 API 기능 및 v2.2.0 완료 기능

검증:
- Backend Python compile PASS
- Release 설정 로딩 및 DB 연결 PASS
- 운영 `/api/health` HTTP 200, version 2.2.1 PASS
- 운영 OpenAPI version 2.2.1 PASS
- PostgreSQL `zipterior_db`, Asia/Seoul PASS
- Clean URL 10개 HTTP 200 + text/html PASS
- Release/운영 Backend 일치 PASS
- Frontend 무변경 PASS
- 서비스 재시작 이후 기동 오류 없음
- PostgreSQL dump 생성 및 `pg_restore -l` PASS

Release:
/srv/zipterior/releases/v2.2.1/zipterior_release_v2.2.1

Pre Rollback:
/srv/zipterior/backups/releases/pre_v2.2.1_20260818_135238

최종 Stable:
/srv/zipterior/backups/releases/stable_v2.2.1_final_20260818_140104

현재 개발 작업 없음.
다음 개발은 v2.2.1을 완료 기준으로 새 버전에서 시작한다.


## v2.3.0 FINAL / STABLE / VERIFIED - 2026-08-18

관리자 단지 추가 네이버 자동수집 기능 완료.

주요 완료:
1. 카카오에서 선택한 단지명·좌표로 네이버 단지를 이름/거리 교차검증
2. 네이버 공개 지도 세션 쿠키 자동 발급, 수동·개인 쿠키 저장 없음
3. 준공년도, 세대수, 동수, 주차대수, 난방방식, 시공사 자동입력
4. 타입명, 평형, 공급/전용면적, 방/욕실 수 자동입력
5. 타입별 기본형·확장형 존재 여부 DB/API/관리자 UI 연결
6. 평면도 이미지와 URL은 수집·저장하지 않음
7. 네이버 조회 실패 시 기존 알림 API로 관리자 미확인 알림 1건 유지
8. 관리자 우측 상단 종 아이콘, 빨간 숫자 배지, 알림 목록/읽음 처리
9. 타입정보가 없을 때 기본정보 유지 및 수기 타입 입력 가능
10. 데스크톱·모바일 단지 추가 모달 레이아웃 검증

DB 변경:
- `apartment_types.has_basic_layout BOOLEAN NULL`
- `apartment_types.has_expanded_layout BOOLEAN NULL`
- NULL은 기존 데이터의 미확인 상태를 의미

Release:
`/srv/zipterior/releases/v2.3.0/zipterior_release_v2.3.0`

Pre Rollback:
`/srv/zipterior/backups/releases/pre_v2.3.0_20260818_154122`

최종 Stable:
`/srv/zipterior/backups/releases/stable_v2.3.0_final_20260818_154825`

운영 검증:
- `/api/health` version 2.3.0
- 실제 네이버 단지 2곳 자동수집
- 기본형·확장형 응답 및 평면도 비저장
- 공개 단지 서비스
- 알림 중복 방지
- 운영 HTTPS 정적 자산
- Release/운영 파일 일치
- PostgreSQL dump 및 `pg_restore -l`

현재 개발 작업 없음.
다음 개발은 v2.3.0을 완료 기준으로 새 버전에서 시작한다.


## v2.3.1 FINAL / STABLE / VERIFIED - 2026-08-18

v2.3.0 FINAL/STABLE을 기준으로 별도 Release 작업본을 생성했다.

작업 범위:
- 공개 단지 상세 평/㎡ 단위 가독성
- 중복 단지 등록 차단
- 단지 다중 이미지와 대표 이미지·공개 슬라이더
- 기존 단지의 경고 확인 후 네이버 정보 재수집

사전 조사:
- #3 미사역 호반 써밋은 등록요청·포트폴리오 연결이 있는 정상 단지다.
- #5는 연결 데이터가 없는 테스트 중복본이며 타입 6개의 기본형·확장형 값만 #3보다 최신이다.
- 배포 migration에서 타입 값을 #3으로 병합한 뒤 #5를 정리하고 중복 고유 제약을 추가한다.
- 운영 코드는 아직 변경하지 않았다.

완료 내용:
- 공개 단지 상세 평/㎡ 주·보조단위와 모바일 가독성 개선
- 서비스/DB 양쪽 중복 등록 차단 및 연결 없는 중복 #5 정리
- 관리자 다중 이미지·대표 이미지 관리와 공개 슬라이더
- 기존 단지의 경고 확인 후 네이버 정보 원자적 재수집

Release:
`/srv/zipterior/releases/v2.3.1/zipterior_release_v2.3.1`

Pre Rollback:
`/srv/zipterior/backups/releases/pre_v2.3.1_20260818_163338`

최종 Stable:
`/srv/zipterior/backups/releases/stable_v2.3.1_final_20260818_164443`

운영 검증:
- `/api/health` version 2.3.1
- migration 반복·rollback, 중복 차단, 네이버 재수집
- 실제 이미지 업로드·대표 지정·공개 2장 슬라이드·정리
- PC·390px 모바일 평/㎡ UI와 browser console
- Release/운영 파일 일치, PostgreSQL dump와 SHA256

현재 개발 작업 없음.
다음 개발은 v2.3.1을 완료 기준으로 새 버전에서 시작한다.

## v2.3.2 FINAL / STABLE / VERIFIED - 2026-08-18

v2.3.1 FINAL/STABLE을 기준으로 별도 Release 작업본을 생성했다.

완료 범위:
- 메인 검색 결과 전체 클릭과 이동 멈춤 수정
- 관리자·업체 헤더 이동과 인증 유지
- 공개 지도 로컬 이용 현황 제거
- 업체·관리자 서버 통계 수집 및 조회

Release 작업본:
`/srv/zipterior/releases/v2.3.2/zipterior_release_v2.3.2`

Pre Rollback:
`/srv/zipterior/backups/releases/pre_v2.3.2_20260818_173250`

최종 Stable:
`/srv/zipterior/backups/releases/stable_v2.3.2_final_20260818_174509`

운영 검증:
- `/api/health`와 OpenAPI version 2.3.2
- migration 반복·rollback, 이벤트 dedupe, 좋아요 추가·삭제 이력
- 실제 수집·관리자/업체 통계와 역할 교차 접근 차단
- PC 검색 결과 전체 클릭과 실제 단지 이동
- 390px 모바일 검색 레이아웃과 공개 이용현황 제거
- Release/운영 일치, PostgreSQL dump·`pg_restore -l`·SHA256

현재 개발 작업 없음.
다음 개발은 v2.3.2를 완료 기준으로 새 버전에서 시작한다.

## v2.4.0 FINAL / STABLE / VERIFIED - 2026-08-19

v2.3.2 FINAL/STABLE을 기준으로 별도 Release 작업본을 생성했다.

작업 범위:
- 이미지 없는 단지 상세의 하드코딩 이미지 제거
- Excel 단지 일괄등록과 네이버 실패 목록 알림
- 업체·전문가 포트폴리오 JSON 일괄등록
- 외부 이미지 URL 다운로드·검증·로컬 저장
- 대용량 조각 업로드와 재시작 가능한 작업 진행률
- JSON 주소 기반 미등록 단지 선등록 후 포트폴리오 연결
- 첫 운영 검증은 주소 보유 전문가 30건·포트폴리오당 이미지 10장으로 제한

운영 검증 결과:
- 전체 원본은 등록하지 않고 주소가 있는 `agent=전문가` 30건만 등록
- 최종 작업 `id=3`: 포트폴리오 30/30 성공, 이미지 300/300 성공, 실패·중복 0
- 신규 업체 26개, 단지 29개, 포트폴리오 30개 생성
- 포트폴리오 30개 모두 단지·대표 이미지 연결 및 승인 상태
- 신규 단지의 단지 이미지는 0장이고 공개 API `images=[]` 확인
- AVIF 9장은 실제 본문 검증 후 WEBP 변환, 파생파일 900개 누락 없음
- 네이버 1차 실패 단지는 주소 기본정보로 등록하고 관리자 알림에 기록
- 짧은 확정명 실패 시 원본 동 포함 이름 재시도로 같은 단지 조회 성공 확인
- 활성 업체 상세 조회와 지도 노출 플래그를 분리해 포트폴리오→업체 상세 연결 보강
- 지도 비노출 업체도 포트폴리오의 실제 `company_id`로 상세 조회해 등록 포트폴리오가 표시되도록 수정
- 단지 분석 이벤트의 잘못된 `deleted_at` 조회를 실제 `is_active` 스키마 기준으로 수정하고 재시작 후 저장·로그 검증
- 사전 검증 실패 작업 `id=1`, `id=2`는 원인 추적 이력으로 보존

Release 작업본:
`/srv/zipterior/releases/v2.4.0/zipterior_release_v2.4.0`

Pre Rollback:
`/srv/zipterior/backups/releases/pre_v2.4.0_20260818_224142`

최종 Stable:
`/srv/zipterior/backups/releases/stable_v2.4.0_final_20260819_074245`

상태: FINAL / STABLE / VERIFIED

현재 개발 작업 없음.
다음 개발은 v2.4.0을 완료 기준으로 새 버전에서 시작한다.

## v2.4.1 IN PROGRESS - 2026-08-19

v2.4.0 FINAL/STABLE을 기준으로 별도 Release 작업본을 생성했다.

작업 목적:
- v2.4.0에서 등록한 전문가 포트폴리오 샘플 30건의 전체 설명·공간별 설명·사진 연결 교정
- 원본 복합 공간 식별자와 문서 순서를 사용한 정확한 매핑
- 이후 대량 데이터 삽입 전 정합성 검사와 미리보기 절차 강화

확인된 근본 원인:
- 원본 이미지 1,239장 중 포트폴리오별 앞 10장, 총 300장만 등록되어 30건 중 28건의 공간 구성이 누락됨
- 여러 침실·서재·자녀방과 여러 욕실을 표시용 공통 코드로 합친 뒤 첫 공간 ID에 연결해 사진과 공간 설명이 뒤섞일 수 있었음
- 포트폴리오 전체 설명에 모든 공간 설명을 단순 합산해 전체 소개와 공간별 설명이 중복·혼합됨

원본 정합성:
- `(space_code, sub_space_code, sub_space_name)` 복합 식별자로 원본 이미지 1,239장을 모호성 없이 공간에 연결할 수 있음
- 설명은 있지만 사진이 없는 36개 공간은 다른 공간 사진을 임의 연결하지 않음
- 기존 30건 외 데이터는 이번 작업에서 추가 등록하지 않음

대량 데이터 삽입 필수 순서:
원본 분석 → 필드 매핑표 → 필수값·중복·누락·참조·이미지 관계 검사 → 미리보기 → 이상 없는 데이터만 등록 → DB·API·파일·화면 검증.

Release 작업본:
`/srv/zipterior/releases/v2.4.1/zipterior_release_v2.4.1`

현재 운영은 v2.4.0 FINAL/STABLE/VERIFIED이며 v2.4.1은 아직 배포하지 않았다.
