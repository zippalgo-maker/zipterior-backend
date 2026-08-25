# ZIPTERIOR SERVER CONTEXT

최종 갱신: 2026-08-23 (construction_scope 값 체계 통일, 관리자
포트폴리오/단지 화면 서버 페이지네이션 전환, hidden 속성이 CSS에
밀려 안 먹히던 버그 다수 발견·수정 요약 추가, 아래 5번·7번 절 참고
-- **추가**: nginx sites-available/sites-enabled가 심볼릭 링크가
아니라 서로 어긋난 별개 파일이라는 것 실측 확인, 2번 절 참고. nginx
설정 바꿀 땐 반드시 먼저 읽고 시작할 것 -- **추가 2**: 모바일 앱 셸
`m.html`/`js/mobile-app.js`/`css/mobile.css` 신규 착수(UX 도면 B안),
상세는 V2.5.0_PLAN.md 맨 아래 "세션 마무리" 절 참고)

이 문서는 ZIPTERIOR 개발 작업을 새 채팅에서 이어갈 때
가장 먼저 확인해야 하는 서버 기준정보다.

중요:
비밀번호, JWT Secret 등 실제 비밀값은 이 문서에 기록하지 않는다.

---

## 1. 프로젝트 기본 경로

PROJECT_ROOT=/srv/zipterior

운영 Backend:
/srv/zipterior/backend

운영 Frontend:
/var/www/zipterior

Python Virtualenv:
/srv/zipterior/venv

환경설정:
/srv/zipterior/backend/.env

Kakao Maps 환경설정:
/srv/zipterior/config/kakao_maps.env

---

## 2. 운영 웹서버

Web Server:
nginx

Domain:
zipterior.kr
www.zipterior.kr

Nginx Frontend Root:
/var/www/zipterior

중요:
현재 /srv/zipterior/frontend 디렉터리는 실제 운영 프론트가 아니다.

운영 프론트 수정/검증 시:
/var/www/zipterior

을 기준으로 확인한다.

nginx 사이트 설정 파일:
/etc/nginx/sites-available/zipterior
/etc/nginx/sites-enabled/zipterior

**중요(2026-08-23 실측 확인, 반드시 읽을 것)**: 이 두 파일이
**심볼릭 링크로 안 묶여 있다 -- 완전히 별개의 실파일(각각
root:root 644)이다.** 보통 배포 관행상 `sites-enabled`가
`sites-available`을 가리키는 심볼릭 링크일 거라고 가정하기 쉬운데
여기는 아니다. **실제로 nginx가 로드해서 서비스하는 건
`sites-enabled/zipterior` 쪽이다.** 실측 시점 기준으로 두 파일이
이미 어긋나 있었음(`client_max_body_size`가
`sites-available`엔 20m, `sites-enabled`엔 500m로 서로 다른 값 --
어느 게 "의도된 최신값"인지 이 문서만으로는 알 수 없어 손 안 대고
그대로 둠).

**nginx 설정을 바꿀 때 반드시 지킬 것**:
1. `sites-available/zipterior`만 고치고 reload하면 **아무 효과가
   없다**(2026-08-23 실제로 이렇게 사고 -- `/m` 라우팅 블록을
   `sites-available`에만 추가하고 `nginx -t`/`reload`까지 했는데
   실제 서비스는 계속 예전 동작이었음, 원인 파악에 세션 하나를
   더 씀).
2. **`sites-enabled/zipterior`를 반드시 같이(또는 그것만이라도)
   고쳐야 실제로 반영된다.**
3. 두 파일이 이미 어긋나 있으므로, 새 설정을 준비할 때는 반드시
   `sites-enabled/zipterior`의 **현재 실제 내용**을 다시 읽어서
   그걸 기준으로 수정본을 만들 것 -- `sites-available`을 기준으로
   만들면 이미 있는 어긋남(예: client_max_body_size)을 실수로
   되돌려버릴 수 있다.
4. Claude는 이 파일들에 쓰기 권한이 없다(root 소유, 644) --
   수정본을 스크래치 경로에 만들어 두고 사용자가
   `sudo cp`+`sudo nginx -t`+`sudo systemctl reload nginx`로
   반영해야 한다.
5. **`sites-enabled/` 안에는 백업 파일(`*.bak_...`)을 만들지 말 것.**
   nginx의 `include /etc/nginx/sites-enabled/*;`는 확장자를 안
   가리고 그 디렉터리 안의 파일을 전부 설정으로 읽는다(심볼릭 링크만
   있을 거라는 관례를 기대하면 안 됨 -- 애초에 1번 항목처럼 이
   서버는 그 관례 자체가 깨져 있다). 2026-08-23에 `sites-enabled/`
   안에 `zipterior.bak_...`을 만들었다가 `server{listen 443 ssl...}`
   블록이 원본과 중복돼 `nginx -t`가 "duplicate listen options"로
   실패한 적 있음(다행히 `-t` 실패 덕에 reload는 안 됐고 서비스
   영향 없었음). `sites-enabled`를 백업할 땐 `sites-available/`
   디렉터리(여긴 include 안 됨, 안전)나 다른 경로에 저장할 것.

---

## 3. Database

DBMS:
PostgreSQL

Database:
zipterior_db

DB 접속정보 실제 값:
/srv/zipterior/backend/.env

중요:
DB 비밀번호를 문서에 직접 기록하지 않는다.

DB 구조 확인 예:

sudo -u postgres psql -P pager=off -d zipterior_db

psql 사용 시 pager는 가급적 OFF 한다.

---

## 4. Backend 환경변수

환경파일:
/srv/zipterior/backend/.env

현재 주요 변수:

APP_NAME
APP_ENV
APP_DEBUG
DATABASE_HOST
DATABASE_PORT
DATABASE_NAME
DATABASE_USER
DATABASE_PASSWORD
JWT_SECRET_KEY
JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS
APP_VERSION
LOG_LEVEL
REQUEST_LOG_ENABLED
SLOW_REQUEST_MS
RATE_LIMIT_ENABLED
RATE_LIMIT_REQUESTS_PER_MINUTE
KAKAO_REST_KEY (건물명 기반 단지 자동 매칭용, 카카오맵 JS 키와는 별개)
DATA_GO_KR_STANREGINCD_KEY (법정동코드 자동수집용)

2026-08-24부터 추가(SNS 로그인, app/modules/oauth/ 참고,
V2.5.0_PLAN.md의 "SNS(카카오/네이버/Google) 실제 로그인 구현 착수"
항목부터 읽을 것):
PUBLIC_BASE_URL (OAuth redirect_uri 조립 기준, https://zipterior.kr)
OAUTH_STATE_SECRET (OAuth state JWT 서명용, Claude가 생성해 채움)
KAKAO_OAUTH_CLIENT_ID / KAKAO_OAUTH_CLIENT_SECRET (채워짐, 2026-08-24
  실제 로그인 테스트 성공 확인됨 -- 카카오 "카카오계정(이메일)" 동의
  항목은 아직 미승인 상태라 이메일 없이 가짜 이메일
  {provider}_{id}@no-email.zipterior.kr로 계정 생성하는 폴백 사용 중)
NAVER_OAUTH_CLIENT_ID / NAVER_OAUTH_CLIENT_SECRET (아직 비어있음,
  발급 전)
GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET (아직 비어있음,
  발급 전)

작업본 Backend 직접 실행/검증 시
.env가 작업본에 없다고 새로 만들거나 복사하지 않는다.

운영 `.env`에는 공백이 포함된 값이 있어 shell `source` 방식으로 읽지 않는다.
작업본 검증은 Python `python-dotenv`의 `load_dotenv('/srv/zipterior/backend/.env')`
또는 기존 안전한 환경파일 파서를 사용한다. Release에 `.env`를 복사하지 않는다.

---

## 5. Release 구조

Release Root:
/srv/zipterior/releases

현재 운영 기준 버전:
v2.4.0

v2.4.0 상태:
FINAL / STABLE / VERIFIED

v2.4.0 Stable:
/srv/zipterior/backups/releases/stable_v2.4.0_final_20260819_074245

v2.4.0 Release:
/srv/zipterior/releases/v2.4.0/zipterior_release_v2.4.0

v2.3.2 상태:
FINAL / STABLE / VERIFIED

v2.3.2 Stable:
/srv/zipterior/backups/releases/stable_v2.3.2_final_20260818_174509

v2.3.2 Release:
/srv/zipterior/releases/v2.3.2/zipterior_release_v2.3.2

v2.3.1 상태:
FINAL / STABLE / VERIFIED

v2.3.1 Stable:
/srv/zipterior/backups/releases/stable_v2.3.1_final_20260818_164443

v2.3.1 Release:
/srv/zipterior/releases/v2.3.1/zipterior_release_v2.3.1

v2.3.0 Stable:
/srv/zipterior/backups/releases/stable_v2.3.0_final_20260818_154825

v2.3.0 Release:
/srv/zipterior/releases/v2.3.0/zipterior_release_v2.3.0

v2.2.1 Stable:
/srv/zipterior/backups/releases/stable_v2.2.1_final_20260818_140104

v2.2.1 Release:
/srv/zipterior/releases/v2.2.1/zipterior_release_v2.2.1

v2.2.0 Stable:
/srv/zipterior/backups/releases/stable_v2.2.0_final_20260818_133641

v2.2.0 Release:
/srv/zipterior/releases/v2.2.0/zipterior_release_v2.2.0

v2.1.9 Stable:
/srv/zipterior/backups/releases/stable_v2.1.9_final_20260818_090929

v2.1.9 Release:
/srv/zipterior/releases/v2.1.9/zipterior_release_v2.1.9

이전 v2.1.8 Stable:
/srv/zipterior/backups/releases/stable_v2.1.8_final_20260814_165925

현재 개발 작업:
v2.5.0 IN PROGRESS (실질적 현재 작업 문서 — 2026-08-19부터 계속 갱신 중,
가장 최근 갱신 2026-08-21. v2.4.1은 모바일 화면 검증 대기로 보류된 채
멈춰있고, 실제 개발은 이 문서 갱신 시점부터 이미 v2.5.0으로 넘어가 있었음.
아래 "작업 추적 문서" 절 참고.)

v2.4.1 Release 작업본(모바일 검증 대기로 보류 중):
/srv/zipterior/releases/v2.4.1/zipterior_release_v2.4.1

v2.4.1 작업 문서(보류 상태 그대로 남겨둠, 최신 작업은 V2.5.0_PLAN.md 참고):
/srv/zipterior/V2.4.1_WORK.md

---

## 6. v2.4.0 사전 Rollback

v2.4.0 운영 배포 전 백업:

/srv/zipterior/backups/releases/pre_v2.4.0_20260818_224142

이 백업은 v2.4.0 배포 전 v2.3.2 운영 상태의
Frontend + Backend + PostgreSQL dump + nginx 설정 복구 기준점이다.

---

## 7. 작업 추적 문서

**현재 실질적 작업 문서(가장 먼저 읽을 것):**

/srv/zipterior/V2.5.0_PLAN.md

3,600줄 넘는 계속 갱신 중인 작업 로그. 새 세션에서 이어갈 때는 이 문서
**맨 아래 최신 항목부터** 확인한다. 트랜스크립트가 유실된 세션이 있었던
전례가 있어(2026-08-21, "[기록 복구]" 항목 참고), 이 문서 자체도 코드
백업 파일(`*.bak_YYYYMMDD_HHMMSS_설명`, `/var/www/zipterior`와
`/srv/zipterior/backend` 아래)과 실제 라이브 코드 대비 뒤처져 있을 수
있다 — 의심되면 `/api/health`의 `version`을 맹신하지 말고(현재 앱 코드
대비 갱신이 늦음), 최근 수정 시각 기준으로 백업 파일을 diff해서
직접 재확인한다.

과거 작업 문서(보류 상태, 참고용):

/srv/zipterior/V2.4.1_WORK.md

상태: IN PROGRESS이나 모바일 화면 검증 대기로 멈춰있음 (이미지·공간 매핑
교정은 검증 완료, 텍스트 재분리는 v2.5.0으로 이관). **실제 개발은 이
버전을 사실상 지나쳐 v2.5.0으로 넘어가 있으므로, 새 세션에서 "현재
버전이 뭔지" 판단할 때 이 문서만 보고 판단하지 말 것.**

일괄등록 시스템에 구조 신호 기반 신뢰도 % 계산 + 방/사진별 텍스트 재구성을
추가하는 작업. 2026-08-19 세션에서 백엔드 코드 작성, 테스트 DB 종단 검증,
**운영 DB 마이그레이션 적용 및 서비스 재기동까지 완료**(같은 날 Claude Code
세션에서 진행 — 백업 후 alembic 이력 어긋남 정정, 마이그레이션 적용, 재기동,
공개 API 스키마 누락 필드 수정, 전 구간 회귀 확인 완료). 데이터 손실 없음,
현재 운영 데이터는 캡션이 전부 비어있어 화면 변화 없음(정상). 같은 날 이어서
**관리자 검수 UI(신뢰도 %, 체크박스, 기준값 조정, 원본 링크, 방/사진별 실제
미리보기 렌더링)까지 전부 완료**하고 실제 관리자 화면에서 JSON·Excel 업로드
양쪽 다 업로드→미리보기→체크박스/기준값 조정→미리보기 렌더링까지 Chrome으로
직접 검증함(테스트 데이터, 운영에 흔적 없음). 이 과정에서 `bulk_import_jobs`
의 `job_type` CHECK 제약조건이 `company_portfolio_excel`을 막고 있던 실제
버그를 찾아 마이그레이션(`a25000000002`)으로 고쳤고, `admin-api.js` 캐시
버전 쿼리스트링을 안 올려서 새 코드가 브라우저에 반영 안 되던 문제도 고침
(앞으로 admin-api.js 수정 시 `admin-dashboard.html`의 버전 쿼리스트링도
같이 올릴 것). v2.5.0 백엔드+관리자 UI는 기능적으로 완성 상태.

**같은 날 이어서 사용자 지시로 기존 포트폴리오 33건 + 단지 34건을 운영 DB에서
전부 삭제함** (업체 27건은 유지). 그러므로 **현재 운영 DB에는 포트폴리오·단지
데이터가 0건**이다 — 화면에서 지도/포트폴리오가 비어있는 건 버그가 아니라
의도된 상태. 다음 등록은 v2.5.0 관리자 UI(신뢰도 계산 + 검수 화면)로
진행한다. 백업: `pre_portfolio_complex_wipe_20260819_172151`. 새 채팅에서
이어갈 경우 `V2.5.0_PLAN.md`의 "포트폴리오·단지 전체 삭제 실행 기록" 절부터
읽는다.

**같은 날 추가로, 단지 기본정보 Excel 일괄등록의 `floor_plan_path` 바인드
파라미터 누락 버그를 발견해 수정**(`_process_complex_job`, 이미 다른
함수에는 있던 것과 동일한 수정). 실제 195개 주소로 재테스트해 195/195
성공 확인. 관리자 화면에 "처리 결과 상세" 모달과 "파일 내 중복 제외"
표시도 추가함 — 자세한 건 `V2.5.0_PLAN.md`의 "단지 기본정보 Excel 일괄등록
버그 수정" 절 참고 (v2.5.0과 무관한 기존 버그였음).

**지도 마커 클러스터링 세분화 (2026-08-19, 공개 홈 지도)**: `js/map-provider.js`
의 `clusterCell(zoom)`과 `js/app.js`의 `premiumGridGroups`가 예전엔 5~6개
구간으로만 뭉텅뭉텅 바뀌는 계단식 함수였다. 매 확대 단계마다 부드럽게
좁아지는 지수함수(`20/1.8^zoom`, 도 단위)로 교체 — `MapProvider.clusterCellDegrees`
로 export해서 두 곳이 같은 공식을 씀. 실측(지도 컨테이너 1919px 기준):
카카오 레벨2 ≈ 화면폭 1km. 새 공식은 화면이 1km로 좁아지기 훨씬 전인
레벨 5~6대(줌 13~14)에서 이미 그룹 반경이 1km 미만으로 줄어들어 개별
마커가 최대한 보인다. 실제 홈 지도에서 확대/축소 반복해 콘솔 에러 없이
정상 동작 확인. 캐시 버전: `js/map-provider.js?v=2.1.6`,
`js/app.js?v=2.5.0-map-cluster` (index.html).

**실제 대량 데이터 첫 실행 (2026-08-19)**: `/home/zipterior/uploads/`의
91MB·1,870건짜리 실 원본 Excel로 v2.5.0 파이프라인을 처음 실제 규모로
돌림. 150건 스테이징 배치 — 150/150 포트폴리오 성공, 이미지 4,321/4,349
성공, 신뢰도 기준으로 144건 자동공개·6건 검수대기 정확히 갈림, 사진별
캡션이 실제 화면에 정상 노출됨을 확인. 이 과정에서 Excel 경로가 주소
확인 후 `preview` 상태로 못 넘어가던 진짜 버그를 발견·수정함(자세한 건
`V2.5.0_PLAN.md`의 "실제 대량 데이터(1,870건) 첫 실행" 절). **현재 운영
DB: 포트폴리오 150건 · 단지 352개 · 업체 118개.** 남은 약 1,638건은 사용자
확인 후 진행 예정 — 같은 파일로 `max_portfolios`만 올려서 다시 돌리면
이미 등록된 150건은 자동으로 건너뛴다.

**이미지 처리 속도 개선 (2026-08-19, 같은 세션 이어서)**: 150건 처리에
2시간 걸린 원인이 원본 다운로드가 아니라 서버의 리사이즈·WebP 인코딩·
디스크 저장(로컬 CPU 작업)이었음을 실측으로 확인. WebP 인코딩
`method=6`→`4`로 변경(속도 2배, 용량 +10%, 화질 차이 거의 없음) +
포트폴리오 하나 안에서 이미지 4장씩 동시 처리(원본 CDN 동시 연결 수는
그대로 4로 유지 — 원본 사이트 부하 우려 반영)로 실측 1.6배 개선(장당
1.70초→1.07초). 동시 저장 시 대표사진 중복 지정/순서 꼬임 위험이 있던
부분은 `image_service.py`에 `sort_order_override`/
`is_representative_override` 파라미터를 추가해 배치 전체를 미리 계산하는
방식으로 안전하게 재설계, 합성 테스트로 검증 완료. **배포·재기동
완료, 운영 반영됨.** 실제 대량(500건) 배치로는 아직 검증 안 함 — **다음
세션에서 500건 배치 진행 예정** (사용자가 세션을 새로 시작하기로 함).
자세한 내용과 다음 세션이 필요한 정보(원본 파일 경로, 업로드 방법,
max_portfolios 값 등)는 `V2.5.0_PLAN.md`의 "다음 세션에서 이어갈 것
(500건 배치)" 절 참고.

**포트폴리오 450건 삭제, content_blocks 테스트 6건(505~510)만 유지
(2026-08-20)**: 오늘의집 원본 문서 순서 재현 기능 검증 후, 사용자 지시로
기존 포트폴리오 450건 전부 삭제(업체 241·단지 618은 유지). **현재 운영
DB: 포트폴리오 6건뿐**(전부 content_blocks 보유, 공개 상세페이지에서
원문 순서로 정상 렌더링). 자세한 내용은 `V2.5.0_PLAN.md`의 "포트폴리오
450건 삭제" 절 참고.

**confidence.py 공간 라벨링 버그 수정 + 기존 450건 재계산 (2026-08-20, 새 세션)**:
일괄등록된 포트폴리오가 신뢰도 통과로 표시돼도 실제로는 거실/안방 등
서로 다른 방의 텍스트가 한 섹션에 섞이는 버그를 발견·수정(원인: 원본의
`sub_space_name` 필드를 더 안정적인 `space_code`보다 무조건 우선했고,
"룸명 + 구분자 + 부제목" 헤딩을 인식 못해 다음 방 문단이 이전 방 섹션에
흡수됨). 백업 후 코드 반영·서비스 재기동(사용자 직접 sudo 실행), 기존
450건 중 418건 재계산·반영(공간설명 293건·사진캡션 518건·전체설명
12건 수정, 승인→검수대기 17건/검수대기→승인 15건, 순 승인 373→371).
id=411 실제 화면에서 거실/안방 정상 분리 확인. 자세한 내용은
`V2.5.0_PLAN.md`의 "confidence.py 공간 라벨링 버그 수정 + 기존 450건
재계산" 절 참고.

**300건 배치 시도, 실제 업로드 전 중단 (2026-08-20)**: 500건 중 300건
먼저 진행 요청받아 사전 백업(`pre_300batch_20260820_033532`)까지 마쳤으나,
브라우저 JS 실행(청크 업로드에 필요)이 이 세션의 자동 모드 classifier에
막혀 **실제 업로드는 시작하지 못함 — 운영 DB 변경 없음**. 백업/청크분할/
job 파라미터(max_portfolios=450)는 준비됨. 재개 방법은 `V2.5.0_PLAN.md`의
"300건 배치 시도 및 중단 (2026-08-20)" 절 참고.

**오늘의집 v4 크롤링 91건 전문가 포트폴리오 등록 완료 (2026-08-21)**:
`method=4` 속도개선 검증을 겸해 part1~4(job #29~32) 순차 업로드,
목표했던 91건과 정확히 일치하게 전부 성공(이미지 일부 실패는 정상
범위). 자세한 내용은 `V2.5.0_PLAN.md`의 "part4(마지막 파일) 업로드"/
"v4 크롤링 91건 전체 완료" 절 참고.

**포트폴리오 하단 SNS링크 노출제어 + 고정 안내문구/CTA + 자동 타겟
견적문의, 시군구 기준 네이버부동산 단지 자동수집(체크박스 선택,
아파트+오피스텔 구분 저장, 단지 목록 페이지네이션 버그 수정), 단지
유형 화면 표시 + 지도 마커·단지정보 노출 설정 (2026-08-21)**: 세
작업 전부 완료·실사용 검증 완료. 자세한 내용은 `V2.5.0_PLAN.md`
해당 절 각각 참고.

**현재 운영 DB 실측 (2026-08-21 새 세션 시작 시점 확인)**:
portfolios 91건 · apartment_complexes 1,057건(그중 `complex_type`
미분류 773건 — 자동수집 기능 추가 이전에 들어간 단지들) · companies
239건. `/api/health` version 2.5.0 정상.

**포트폴리오·단지·업체 전체 삭제 후 재검증 + v5.3 파이프라인 버그
다수 수정 + 단지 자동수집 정확도 개선 (2026-08-21 밤 ~ 2026-08-22,
긴 세션)**: 사용자 지시로 운영 DB의 portfolios/apartment_complexes/
companies를 전부 삭제(계정 3개만 유지)한 뒤, v5.3 크롤링 파일
(JSON, 427건)로 처음부터 다시 등록하며 파이프라인을 실측으로
검증·수정. 대량등록(`bulk_import`) 쪽에서 진짜 버그 4개 발견·수정
(address_lookup_query 파서 누락, apartment_name 정규화 우회,
pyeong_label 글자접미사 미처리, **지역 무관 동일 아파트명 오매칭**
-- 마지막 건은 `find_complex_for_import`에 sigungu 파라미터 추가로
구조적으로 재발 방지). title/본문 텍스트 마이닝을 대량등록 완료 시
자동으로 이어지는 정식 기능(`title_mining.py`)으로 만듦. 시군구
자동수집(`complex_region_import`) 쪽에서는 네이버 API 남용(abuse)
차단을 실제로 겪고 원인 규명 → 무작위 지연+재시도 백오프+차단
시 10~15분 쿨다운 후 자동 재개 기능 추가, 읍면동별 세부내역 화면 +
시군구 체크박스 완성도 색상 표시(초록/주황) 추가, **네이버 통합검색
기반 이중검사 기능**(`job_kind='cross_check'`, 마이그레이션
`a25000000007`)을 신규 구축해 타입 필터 누락 버그 2개(B01=분양권,
A04=재건축) 추가 발견·수정. 양평군·과천시로 최종 검증한 결과
네이버 검색과 우리 DB가 **완전히 일치(확인필요 0건)**함을 확인.
자세한 내용은 `V2.5.0_PLAN.md` 하단(2026-08-22 항목들) 전부 참고
-- 이 세션 하나에서 나온 절이 매우 많음(대량등록 버그 수정 6개
+ 자동수집 기능 개선 5개 정도).

**현재 운영 DB 실측 (2026-08-22 세션 종료 시점)**: portfolios 427건
· apartment_complexes 505건(양평군 82 + 과천시 37 + 기존 자동수집분
포함) · companies 237건 · users 3건(super_admin/company/customer
각 1). `/api/health` version 2.5.0 정상.

**현재 운영 DB 실측 (2026-08-23 세션 중, construction_scope/페이지네이션/
CSS 버그 수정 세션 도중 확인)**: portfolios 427건(불변) ·
apartment_complexes **1,234건**(단지 자동수집이 그 사이 계속 진행돼
505건 -> 1,234건으로 큰 폭 증가 -- 고양시 등 추가 시군구 자동수집이
진행된 것으로 보임, 이 세션에서 직접 늘린 건 아니고 실측만 함) ·
companies 237건(불변) · users 3건(불변). `/api/health` version 2.5.0
정상. 이 세션의 실제 작업 내용은 `V2.5.0_PLAN.md`
"construction_scope(공사범위) 개별등록/일괄등록 값 체계 불일치 수정"
절부터 참고(2026-08-22 후반~2026-08-23).

최근 완료 작업:

/srv/zipterior/V2.4.0_WORK.md

새 채팅 또는 작업 재개 시 반드시 먼저 읽는다.

v2.4.0 상태: FINAL / STABLE / VERIFIED

코드 수정만으로 완료 처리하지 않는다.
실제 검증까지 성공한 뒤 [x] 완료 처리한다.

---

## 8. 새 작업 시작 절차

ZIPTERIOR 작업을 새 채팅에서 재개할 경우
무작정 서버 구조를 다시 탐색하지 않는다.

우선 다음을 확인한다.

1.
/srv/zipterior/SERVER_CONTEXT.md

2.
현재 버전 WORK 문서
예:
/srv/zipterior/V2.4.0_WORK.md

3.
현재 Release 문서 및 AI_HANDOFF가 있으면 확인

그 후 필요한 부분만 추가 조사한다.

---

## 9. 운영 원칙

- 기존 정상 기능 임의 변경 금지
- 요청 기능과 직접 관련된 부분만 수정
- 운영 배포 전 백업
- 작업본에서 우선 수정/검증
- 운영 배포 후 실제 API/UI 검증
- PC/모바일 확인
- 오류/빈 상태 확인
- 기존 기능 회귀 확인
- CHANGELOG 기록
- AI_HANDOFF 기록
- RELEASE 기록
- rollback 경로 기록
- 최종 Stable 백업

---

## 9-1. 서버 SSH 접속 (2026-08-21 갱신)

서버 IP: `115.68.195.144` / 계정: `zipterior` / 포트: `22`

등록된 SSH 개인키가 여러 개 있을 수 있다. 접속 안 될 때는 아래
순서로 확인한다.

- Windows에서 접속 시(표준 경로, 문제 생기면 우선 이걸로 시도):
  ```powershell
  ssh -i $HOME\.ssh\zipterior_key zipterior@115.68.195.144
  ```
- 예전 키(`Documents\Codex\2026-08-18\wlq\work\ssh\zipterior_codex_ed25519`,
  서버 등록명 `codex-zipterior-20260818`)도 서버에는 여전히 등록되어
  있어 살아있지만, **Windows 파일 권한이 너무 개방적이라("UNPROTECTED
  PRIVATE KEY FILE") OpenSSH가 거부하는 문제가 있었다.** 이 키로 접속
  안 되면 위 표준 경로 키를 대신 쓴다 -- `icacls`로 권한만 좁혀서
  고치려 하지 말 것(시도하다 파일 자체가 완전히 접근 불가 상태로
  꼬인 전례 있음, `V2.5.0_PLAN.md`의 "서버 SSH 접속 키 이슈 및 복구"
  절 참고).
- 서버 쪽 등록된 공개키 확인: `/home/zipterior/.ssh/authorized_keys`
  (백업 파일들 `authorized_keys.bak_*`도 같은 위치).
- 새 키 추가가 필요하면: 로컬에서 `ssh-keygen -t ed25519 -f
  $HOME\.ssh\<이름> -N '""'` 로 생성 → 공개키(`.pub` 파일 내용)를
  서버 `authorized_keys`에 한 줄 추가(append, 기존 줄은 안 지움) →
  새 키로 접속 확인.
- 비밀번호 로그인은 fail2ban이 SSH에 걸려 있어 여러 번 틀리면 해당
  IP가 일시 차단된다(기본 설정 기준 약 10분). 비밀번호를 모르면
  추측 대신 키 접속 경로를 먼저 해결한다.

## 10. 터미널 작업 방식

사용자는 복사/붙여넣기 문제 때문에
터미널 명령을 짧고 명확하게 받는 것을 선호한다.

단순 조회를 지나치게 여러 단계로 반복하지 않는다.

서로 연관되고 안전한 작업은
가능하면 한 덩어리로 묶어 빠르게 진행한다.

위험한 운영 변경은
검증과 rollback 지점을 확보한 뒤 실행한다.

---

## 11. 서버정보 변경 시

아래 정보가 변경되면 이 문서도 반드시 갱신한다.

- 운영 Frontend 위치
- Backend 위치
- .env 위치
- DB 구조/DB명
- nginx 구조
- 서비스 실행방식
- Release 구조
- Stable 위치
- 배포방식
- 로그 위치
- 백업 정책

SERVER_CONTEXT.md를 ZIPTERIOR의
서버 작업 기준정보(Single Source of Truth)로 유지한다.

## 12. 코드 전달 및 검증 원칙

- 화면에서 잘릴 수 있는 긴 코드를 한 번에 전달하지 않는다.
- 수정은 파일/기능 단위로 짧게 나눈다.
- 각 수정 직후 반드시 실제 적용 여부를 검증한다.
- PATCH OK 문구만으로 성공 판정하지 않는다.
- Python/JS 문법, 실제 파일 내용, API 동작을 단계별 검증한다.
- 검증되지 않은 작업은 완료 처리하지 않는다.
