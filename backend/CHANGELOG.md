
## v0.2.0 - 2026-08-06

- Platform Core 마이그레이션 적용
- 사용자별 권한 예외 구조 추가
- Feature Flag 범위 설정 추가
- Audit Log 저장 기능 구현
- Event Outbox 저장 기능 구현
- 인증 토큰 테이블 추가
- Argon2 비밀번호 해시 구현
- 일반고객 회원가입 API 구현
- 로그인 및 JWT Access Token 발급 구현
- Refresh Token 해시 저장 구현
- 현재 사용자 조회 API 구현
- 로그인 성공·실패 기록 구현

## v0.2.0 - Authentication Complete

- Customer Register
- Login
- JWT Access Token
- Refresh Token
- Refresh Rotation
- Refresh Reuse Detection
- Logout
- Logout All
- /auth/me
- Login Attempt Log

## v0.3.0 - Company Module Started

- Company Module 개발 시작
- 기존 업체 DB 구조 분석
- 업체회원 가입 및 관리자 승인 흐름 준비

## v0.3.0 - Company Schema Analysis

- 기존 Company 관련 16개 테이블 확인
- companies를 업체 중심 테이블로 사용하도록 확정
- company_members의 owner, manager, staff 역할 구조 확인
- company_onboarding을 업체 영업·등록 CRM으로 사용하도록 확정
- membership_plans의 포트폴리오·견적·지도 우선순위 구조 확인
- 프리미엄과 런칭파트너는 업체 status가 아닌 회원권·프로모션으로 관리하도록 확정

## v0.3.1 - Company Schema Analysis Complete

- companies 28개 컬럼 및 상태 제약조건 확인
- company_members owner, manager, staff 역할 확인
- company_onboarding CRM 상태 흐름 확인
- membership_plans free, basic, premium, launch_partner 확인
- 런칭파트너의 무제한 포트폴리오·무료 견적·관리자 대리등록 정책 확인
- 업체 등급은 status가 아닌 membership으로 관리하도록 확정

## v0.3.2 - Company Registration Complete

- 업체회원 가입 API 구현
- users에 company/pending 계정 생성
- companies에 pending 업체 생성
- company_members에 owner 연결
- company_onboarding에 registering 상태 생성
- 신규 업체에 launch_partner 회원권 자동 배정
- 업체 가입 Audit Log 기록
- CompanyRegistered Event Outbox 기록
- 모든 생성 작업을 단일 트랜잭션으로 처리
- 가입 승인 전 로그인 차단 검증 완료

## v0.3.3 - Company Approval and Management CLI

- 관리자 업체 승인 API 구현
- 승인 시 업체와 대표계정을 active로 전환
- approved_by 및 approved_at 기록
- company_onboarding을 completed로 전환
- CompanyApproved Audit Log 및 Event Outbox 기록
- 승인 후 업체 로그인 검증 완료
- super_admin 생성 기능 구축
- manage.py 관리 명령 구축
- 관리자 목록, 승인대기 업체 목록, DB 상태 확인 명령 추가

## v0.3.3 - Company Approval and Management CLI

- 최고관리자 계정 생성 기능 구축
- 관리자 업체 승인 API 구현
- 승인 시 업체와 대표계정을 active 상태로 전환
- approved_by 및 approved_at 기록
- company_onboarding을 completed 상태로 전환
- company.approved Audit Log 기록
- CompanyApproved Event Outbox 기록
- 승인 전 로그인 차단 및 승인 후 로그인 성공 검증
- manage.py 관리 명령 구축
- 관리자 목록, 승인 대기 업체 목록, DB 상태 확인 기능 추가

## v0.3.4 - Company Rejection and Suspension Complete

- 업체 가입 반려 API 실제 검증 완료
- 반려 시 업체 inactive 전환
- 반려 시 대표계정 withdrawn 전환
- onboarding declined 전환
- 반려 사유를 company_onboarding.notes에 저장
- 반려 계정 로그인 차단 검증
- 업체 정지 API 실제 검증 완료
- 정지 시 업체·대표계정 suspended 전환
- 정지 시 활성 Refresh Token 전부 폐기
- company.rejected 및 company.suspended Audit Log 검증
- CompanyRejected 및 CompanySuspended Event Outbox 검증

## v0.3.5 - Company MyPage API Complete

- GET /api/v1/company/me 구현
- PATCH /api/v1/company/me 구현
- 업체 기본정보 조회 및 수정
- 대표자, 연락처, 주소, 소개, 홈페이지, 카카오채널 수정
- 상담 가능 여부 및 지도 노출 여부 수정
- 업체 Membership 정보 조회
- owner 및 manager 수정 권한 적용
- company.updated Audit Log 검증
- CompanyUpdated Event Outbox 검증

## v0.3.6 - Company Logo Upload Complete

- 업체 로고 업로드 API 구현
- JPG, PNG, WEBP 이미지 검증
- 최대 파일 크기 5MB 제한
- 파일 시그니처와 MIME 형식 검증
- 안전한 UUID 기반 파일명 생성
- Nginx 정적 파일 경로 제공
- companies.logo_path 저장
- 신규 로고 업로드 시 기존 로고 자동 삭제
- 업체 로고 삭제 API 구현
- company.logo_updated 및 company.logo_deleted Audit Log 검증
- CompanyLogoUpdated 및 CompanyLogoDeleted Event Outbox 검증

## v0.3.7 - Company Service Regions Complete

- 업체 서비스 지역 목록 조회 API 구현
- 업체 서비스 지역 등록 API 구현
- 업체 서비스 지역 삭제 API 구현
- 첫 번째 등록 지역 자동 대표지역 지정
- 새 대표지역 지정 시 기존 대표지역 자동 해제
- 대표지역 삭제 시 남은 지역 자동 승계
- 업체별 동일 region_code 중복 차단 구현
- 업체당 최대 30개 등록 제한
- company.service_region_created Audit Log 검증
- company.service_region_deleted Audit Log 검증
- CompanyServiceRegionCreated Event Outbox 검증
- CompanyServiceRegionDeleted Event Outbox 검증

## v0.4.0 - Portfolio Core CRUD Complete

- 업체 포트폴리오 목록 조회 API 구현
- 업체 포트폴리오 생성 API 구현
- 업체 포트폴리오 상세 조회 API 구현
- 업체 포트폴리오 수정 API 구현
- 업체 포트폴리오 소프트 삭제 API 구현
- draft 상태 임시저장 생성
- draft 및 rejected 상태 검수 제출 구현
- 제출 시 pending 상태 전환
- pending 및 approved 상태 수정·삭제 차단
- 아파트 단지와 평형 연결 검증
- 최소·최대 예산 검증
- portfolio.created Audit Log 검증
- portfolio.updated Audit Log 검증
- portfolio.submitted Audit Log 검증
- portfolio.deleted Audit Log 검증
- PortfolioCreated Event Outbox 검증
- PortfolioUpdated Event Outbox 검증
- PortfolioSubmitted Event Outbox 검증
- PortfolioDeleted Event Outbox 검증

## v0.4.1 - Portfolio Image Management Complete

- 포트폴리오 이미지 업로드 API 구현
- JPG, PNG, WEBP 업로드 지원
- 파일당 최대 15MB 제한
- 실제 이미지 형식 검증
- EXIF 회전 자동 보정
- 원본 이미지 저장
- large 최대 1920px WebP 생성
- medium 최대 1200px WebP 생성
- thumbnail 최대 480px WebP 생성
- 공간별 room_code 분류
- 이미지 sort_order 수정
- 첫 이미지 자동 대표 지정
- 대표 이미지 변경 API 구현
- 대표 이미지 삭제 시 다음 이미지 자동 승계
- DB와 실제 이미지 파일 동시 삭제
- portfolio.image_uploaded Audit Log 검증
- portfolio.image_updated Audit Log 검증
- portfolio.representative_image_set Audit Log 검증
- portfolio.image_deleted Audit Log 검증
- PortfolioImageUploaded Event Outbox 검증
- PortfolioImageUpdated Event Outbox 검증
- PortfolioRepresentativeImageSet Event Outbox 검증
- PortfolioImageDeleted Event Outbox 검증

## v0.4.2 - Admin Portfolio Review Complete

- 관리자 승인 대기 포트폴리오 목록 API 구현
- 관리자 포트폴리오 승인 API 구현
- 관리자 포트폴리오 반려 API 구현
- 관리자 포트폴리오 숨김 API 구현
- 승인 시 approved 상태 및 published_at 기록
- 반려 시 rejected 상태 및 rejection_reason 기록
- 반려 후 업체 수정 및 재제출 흐름 검증
- 재승인 후 published_at 재기록 검증
- 승인 포트폴리오 hidden 상태 전환 검증
- 숨김 후 published_at 유지 검증
- portfolio.approved Audit Log 검증
- portfolio.rejected Audit Log 검증
- portfolio.hidden Audit Log 검증
- PortfolioApproved Event Outbox 검증
- PortfolioRejected Event Outbox 검증
- PortfolioHidden Event Outbox 검증

## v0.4.3 - Portfolio Keywords Complete

- 포트폴리오 기본 키워드 24개 등록
- 스타일, 색상·소재, 특징, 시공범위 카테고리 구성
- 공개 포트폴리오 키워드 목록 API 구현
- 업체 포트폴리오 선택 키워드 조회 API 구현
- 업체 포트폴리오 키워드 전체 교체 API 구현
- 빈 배열을 통한 전체 선택 해제 구현
- 포트폴리오당 최대 10개 선택 제한
- 중복 키워드 선택 차단
- 존재하지 않거나 비활성화된 키워드 선택 차단
- draft, rejected, hidden 상태 키워드 수정 허용
- pending, approved 상태 키워드 수정 차단
- portfolio.keywords_updated Audit Log 검증
- PortfolioKeywordsUpdated Event Outbox 검증

## v0.4.3 - Portfolio Keywords Complete

- 포트폴리오 기본 키워드 24개 등록
- 스타일, 색상·소재, 특징, 시공범위 카테고리 구성
- 공개 포트폴리오 키워드 목록 API 구현
- 업체 포트폴리오 선택 키워드 조회 API 구현
- 업체 포트폴리오 키워드 전체 교체 API 구현
- 빈 배열을 통한 전체 선택 해제 구현
- 포트폴리오당 최대 10개 선택 제한
- 중복 키워드 선택 차단
- 존재하지 않거나 비활성화된 키워드 선택 차단
- draft, rejected, hidden 상태 키워드 수정 허용
- pending, approved 상태 키워드 수정 차단
- portfolio.keywords_updated Audit Log 검증
- PortfolioKeywordsUpdated Event Outbox 검증

## v0.4.4 - Public Portfolio Read API Complete

- 공개 포트폴리오 목록 API 구현
- 공개 포트폴리오 상세 API 구현
- approved 포트폴리오만 공개
- active 업체의 포트폴리오만 공개
- 지도 공개 설정 업체만 노출
- 업체 기본정보 포함
- 대표 이미지 경로 포함
- 단지 및 평형 정보 포함
- 공개 키워드 포함
- 상세 이미지 목록 포함
- hidden 포트폴리오 접근 차단 검증
- 존재하지 않는 포트폴리오 404 검증
- 목록 limit 및 offset 검증

## v0.4.5 - Public Portfolio Filters Complete

- 공개 포트폴리오 목록 응답에 items, total, limit, offset 추가
- 시도 필터 구현
- 시군구 필터 구현
- 아파트 단지 필터 구현
- 아파트 평형 필터 구현
- 포트폴리오 키워드 필터 구현
- 시공 범위 필터 구현
- 최신순 정렬 구현
- 인기순 정렬 구현
- 인기순 정렬 기준에 조회수, 좋아요, 댓글수 적용
- 잘못된 정렬값 422 검증
- offset 페이지 이동 검증
- 필터 적용 후 전체 개수 계산 검증

## v0.4.6 - Portfolio View Tracking Complete

- 공개 포트폴리오 상세 조회수 증가 구현
- portfolio_view_events 기록 구현
- 비로그인 방문자 visitor_hash 기록
- IP 원문 미저장
- 로그인 사용자 user_id 기준 조회 기록
- X-Session-ID 기반 비로그인 세션 구분
- 동일 세션 30분 중복 조회 방지
- 동일 로그인 사용자 30분 중복 조회 방지
- 다른 비로그인 세션의 독립 조회 집계
- portfolios.view_count 증가 검증
- PortfolioViewed Event Outbox 검증
- 조회 이벤트용 복합 인덱스 추가

## v0.4.7 - Portfolio Likes Complete

- 로그인 사용자 포트폴리오 좋아요 상태 조회 구현
- 포트폴리오 좋아요 등록 구현
- 중복 좋아요 방지 구현
- 포트폴리오 좋아요 취소 구현
- 중복 취소 시 안전하게 0 유지
- portfolio_likes 복합 기본키 기반 중복 차단
- portfolios.like_count 증감 연동
- 공개 approved 포트폴리오만 좋아요 허용
- hidden 포트폴리오 좋아요 404 검증
- 비로그인 좋아요 401 검증
- PortfolioLiked Event Outbox 검증
- PortfolioUnliked Event Outbox 검증

## v0.4.8 - Portfolio Favorites Complete

- 로그인 사용자 포트폴리오 즐겨찾기 상태 조회 구현
- 포트폴리오 즐겨찾기 등록 구현
- 중복 즐겨찾기 등록 방지 구현
- 포트폴리오 즐겨찾기 해제 구현
- 중복 해제 안전 처리 구현
- 내 즐겨찾기 포트폴리오 목록 API 구현
- 목록 total, limit, offset 지원
- 공개 approved 포트폴리오만 신규 즐겨찾기 허용
- hidden 포트폴리오 신규 등록 404 검증
- 비로그인 즐겨찾기 401 검증
- PortfolioFavorited Event Outbox 검증
- PortfolioUnfavorited Event Outbox 검증

## v0.4.9 - Portfolio Comments Complete

- 공개 포트폴리오 댓글 목록 조회 구현
- 로그인 사용자 댓글 작성 구현
- 댓글 수정 구현
- 댓글 소프트 삭제 구현
- 1단계 답글 작성 구현
- 답글에 재답글 작성 차단
- 본인 댓글만 수정·삭제 가능
- 삭제 댓글 공개 목록 제외
- portfolios.comment_count 증감 연동
- 비로그인 댓글 작성 401 검증
- hidden 포트폴리오 댓글 작성 404 검증
- PortfolioCommentCreated Event Outbox 검증
- PortfolioCommentUpdated Event Outbox 검증
- PortfolioCommentDeleted Event Outbox 검증

## v0.5.4 - Map Advanced
- 지도 viewport API 추가
- 줌레벨 기반 grid clustering 추가
- zoom 16 이상 개별 마커 전환
- membership plan map_priority 기반 premium 판정
- company marker에 map_priority/is_premium/marker_level 추가
- consultation_available/premium_only/has_portfolio 필터 추가
- bbox/지역 필터와 클러스터 조합 지원
- 기존 Public Map Core endpoint 하위호환 유지

## v0.6.0 - Estimate Core
- 고객 견적요청 생성/조회/취소 API
- 회원사 배정 견적 조회 및 확인/응답/거절/계약 상태 API
- 관리자 견적 조회/업체배정/상태변경 API
- 견적 상태 전이 및 권한 검증
- 관리자 Audit Log
- Event Outbox 이벤트 발행
- 기존 estimate 스키마 활용 (migration 없음)

## v0.6.1 - Estimate Distribution & Notifications
- 견적 이미지 첨부/삭제 API 추가 (JPG/PNG/WEBP, 장당 10MB, 최대 10장)
- 견적 응답에 images 배열 포함
- 관리자 자동 추천/배정 API 추가
- 지역(service region/company region) + estimate_base_score + membership priority 기반 배정 점수
- assignment_score / score_breakdown 저장
- 수동/자동 배정 시 업체 알림 생성
- 업체 응답/거절/계약 시 고객 알림 생성
- 관리자 상태변경 시 고객 알림 생성
- 내 알림 목록 / 개별 읽음 / 전체 읽음 API 추가
- EstimateImageAdded / EstimateImageDeleted / EstimateAutoAssigned Outbox 이벤트 추가
- estimate.auto_assigned Audit Log 추가
- DB Migration 없음 (기존 estimate_request_images / notifications 스키마 활용)
- Full Integration 업무사이클 검증은 마일스톤 통합테스트로 이관

## v0.6.3 - Production Hardening
- JSON Application/Request Logging 및 X-Request-ID
- Production runtime guard / optional rate limit foundation
- Event Outbox conservative maintenance timer
- Temp media cleanup / DB index health / backup archive verification
- Smoke + Full Regression 재검증

## v1.0.0 - Production Ready
- Production environment cutover (APP_ENV=production, APP_DEBUG=false)
- Runtime rate limit enabled (300 requests/minute/IP)
- APP_VERSION=1.0.0
- Production CORS/HTTPS/Request-ID/Logging verification
- Smoke + Full Regression final verification
- Final stable backend/database/config backup
