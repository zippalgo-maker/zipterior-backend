# Zipterior Development Roadmap

## 전체 진행률

- 현재 전체 진행률: 27%
- Platform Core: 90%
- Authentication: 15%

## Phase 1. Infrastructure - 완료

- Ubuntu VPS
- Nginx
- HTTPS
- systemd
- PostgreSQL 16
- FastAPI
- Alembic

## Phase 2. Platform Core - 진행 중

- [x] RBAC 기본 구조
- [x] 사용자별 권한 예외
- [x] Feature Flag
- [x] Feature Flag 범위 설정
- [x] Audit Log
- [x] Event Outbox
- [x] 이벤트 중복 소비 방지
- [ ] FastAPI 공통 권한 Dependency
- [ ] 관리자 Platform Core API
- [ ] Event Outbox Worker

## Phase 3. Authentication

- [ ] 비밀번호 Argon2 해시
- [ ] 고객 회원가입
- [ ] 업체회원 가입
- [ ] 로그인
- [ ] Access Token
- [ ] Refresh Token
- [ ] 로그아웃
- [ ] 현재 사용자 조회
- [ ] 비밀번호 변경
- [ ] 계정 정지·탈퇴
- [ ] 이메일·휴대전화 인증 확장 구조

## Phase 4. Company

- [ ] 업체 가입·승인
- [ ] 업체정보
- [ ] 사업자정보
- [ ] 업체 로고
- [ ] 런칭 파트너
- [ ] 회원등급·결제 상태

## Phase 5. Portfolio and Media

- [ ] 포트폴리오 등록
- [ ] 관리자 대리등록
- [ ] 원본 이미지 저장
- [ ] WebP 변환
- [ ] Large·Medium·Thumbnail 생성
- [ ] 파일명 기반 공간 자동분류
- [ ] AI 분석 확장 구조

## Phase 6. Estimates and Chat

- [ ] 견적문의
- [ ] 업체 자동배정
- [ ] 채팅
- [ ] 응답률·응답시간
- [ ] 상담 종료·전환 관리

## Phase 7. Zip Score and Exposure

- [ ] 점수 계산 엔진
- [ ] 항목별 점수
- [ ] 관리자 수동 가감점
- [ ] 메뉴별 노출정책
- [ ] 정책 버전 비교
- [ ] 지역·단지·평형 우선순위

## Phase 8. Analytics

- [ ] 방문 세션
- [ ] 노출·클릭·마우스오버
- [ ] 업체 관심도
- [ ] 포트폴리오 성과
- [ ] 견적 전환 퍼널
- [ ] 채팅 성과
- [ ] 집스코어 효과 분석
- [ ] 관리자 분석 대시보드

## Phase 9. Frontend Integration

- [ ] localStorage 데모 로그인 제거
- [ ] 실제 회원 API 연결
- [ ] 실제 업체·포트폴리오 API 연결
- [ ] 실제 견적·채팅 연결
- [ ] 분석 이벤트 수집 SDK 적용

## Authentication 완료 기록

- [x] Customer Register
- [x] Login
- [x] JWT Access Token
- [x] Refresh Token
- [x] Refresh Rotation
- [x] Refresh Reuse Detection
- [x] Logout
- [x] Logout All
- [x] /auth/me
- [x] Login Attempt Log

Authentication 진행률: 95%
전체 진행률: 35%

## Company Module 시작

목표:

- [ ] 업체회원 가입
- [ ] 업체 계정 승인대기
- [ ] 관리자 승인·반려
- [ ] 업체 기본정보 조회·수정
- [ ] 업체 로고 등록
- [ ] 사업자정보
- [ ] 서비스 지역
- [ ] 런칭 파트너 설정
- [ ] 업체 등급·회원권 연결
- [ ] 업체 상태 관리

Company 진행률: 10%
전체 진행률: 35%

## Company DB 분석 완료

- [x] Company 관련 기존 테이블 목록 확인
- [x] company_onboarding 분석
- [x] company_members 분석
- [x] membership_plans 분석
- [x] 업체 상태 흐름 확정
- [x] 업체 멤버 역할 확정
- [ ] companies 전체 컬럼 분석
- [ ] 업체회원 가입 API
- [ ] 업체정보 조회·수정 API
- [ ] 관리자 승인·반려 API

Company 진행률: 18%
전체 진행률: 36%

## Company 스키마 분석 완료

- [x] companies 구조 확인
- [x] companies 상태 제약조건 확인
- [x] company_members 구조 확인
- [x] company_onboarding 구조 확인
- [x] membership_plans 데이터 확인
- [ ] company_memberships 구조 확인
- [ ] 업체회원 가입 API
- [ ] 업체 내 정보 조회·수정 API
- [ ] 관리자 승인·반려 API

Company 진행률: 25%
전체 진행률: 38%

## 업체회원 가입 API 완료

- [x] 업체회원 가입 API
- [x] 업체 계정 승인대기
- [x] 업체 owner 멤버 연결
- [x] onboarding registering 생성
- [x] launch_partner 자동 배정
- [x] Audit Log
- [x] Event Outbox
- [x] 가입 승인 전 로그인 차단
- [ ] 관리자 승인·반려·정지
- [ ] 업체 기본정보 조회·수정
- [ ] 업체 로고 등록
- [ ] 서비스 지역 관리

Company 진행률: 40%
전체 진행률: 37%

## 관리자 업체 승인 및 관리도구 완료

- [x] 최고관리자 생성
- [x] 관리자 업체 승인 API
- [x] 업체·대표계정 active 전환
- [x] onboarding completed 전환
- [x] 승인 Audit Log
- [x] CompanyApproved Event Outbox
- [x] 승인 후 업체 로그인
- [x] manage.py
- [x] 관리자 목록 명령
- [x] 승인 대기 업체 목록 명령
- [x] 시스템 상태 명령
- [ ] 업체 반려 API 실제 검증
- [ ] 업체 정지 API 실제 검증
- [ ] 업체 기본정보 조회·수정

Company 진행률: 55%
전체 진행률: 39%

## 관리자 업체 승인 및 관리도구 완료

- [x] 최고관리자 생성
- [x] 관리자 업체 승인 API
- [x] 업체·대표계정 active 전환
- [x] onboarding completed 전환
- [x] 승인 Audit Log
- [x] CompanyApproved Event Outbox
- [x] 승인 전 로그인 차단
- [x] 승인 후 업체 로그인
- [x] manage.py 관리도구
- [x] 관리자 목록 명령
- [x] 승인 대기 업체 목록 명령
- [x] 시스템 상태 명령
- [ ] 업체 반려 API 실제 검증
- [ ] 업체 정지 API 실제 검증
- [ ] 업체 기본정보 조회·수정

Company 진행률: 55%
전체 진행률: 39%

## 업체 반려·정지 API 완료

- [x] 업체 반려 API
- [x] 반려 시 업체 inactive 전환
- [x] 반려 시 대표계정 withdrawn 전환
- [x] onboarding declined 전환
- [x] 반려 사유 기록
- [x] 반려 계정 로그인 차단
- [x] 업체 정지 API
- [x] 정지 시 업체·대표계정 suspended 전환
- [x] 정지 시 Refresh Token 폐기
- [x] 반려·정지 Audit Log
- [x] 반려·정지 Event Outbox
- [ ] 업체 기본정보 조회·수정
- [ ] 업체 로고 등록
- [ ] 서비스 지역 관리
- [ ] 업체 멤버 관리

Company 진행률: 68%
전체 진행률: 41%

## 업체 MY페이지 API 완료

- [x] 업체 본인정보 조회
- [x] 업체 기본정보 수정
- [x] Membership 조회
- [x] owner·manager 수정 권한
- [x] 업체정보 수정 Audit Log
- [x] CompanyUpdated Event Outbox
- [ ] 업체 로고 등록
- [ ] 서비스 지역 관리
- [ ] 업체 멤버 관리
- [ ] 포트폴리오 관리

Company 진행률: 78%
전체 진행률: 44%

## 업체 로고 업로드 완료

- [x] 업체 로고 업로드
- [x] JPG, PNG, WEBP 검증
- [x] 파일 크기 제한
- [x] 파일 시그니처 검증
- [x] 정적 이미지 URL 제공
- [x] 기존 로고 자동 교체
- [x] 업체 로고 삭제
- [x] 로고 변경 Audit Log
- [x] 로고 변경 Event Outbox
- [ ] 서비스 지역 관리
- [ ] 업체 멤버 관리
- [ ] 포트폴리오 관리

Company 진행률: 85%
Media 진행률: 35%
전체 진행률: 46%

## 업체 서비스 지역 관리 완료

- [x] 서비스 지역 목록 조회
- [x] 서비스 지역 등록
- [x] 서비스 지역 삭제
- [x] 대표지역 자동 지정
- [x] 대표지역 변경
- [x] 대표지역 삭제 후 자동 승계
- [x] 동일 지역 중복 차단
- [x] 업체당 최대 30개 제한
- [x] 서비스 지역 Audit Log
- [x] 서비스 지역 Event Outbox
- [ ] 업체 멤버 관리
- [ ] 포트폴리오 관리

Company 진행률: 92%
Media 진행률: 35%
전체 진행률: 48%

## 포트폴리오 기본 CRUD 완료

- [x] 포트폴리오 목록 조회
- [x] 포트폴리오 생성
- [x] 포트폴리오 상세 조회
- [x] 포트폴리오 수정
- [x] 포트폴리오 소프트 삭제
- [x] 임시저장
- [x] 관리자 검수 요청
- [x] 검수 중 수정·삭제 차단
- [x] 단지·평형 연결 검증
- [x] 예산 범위 검증
- [x] 포트폴리오 Audit Log
- [x] 포트폴리오 Event Outbox
- [ ] 포트폴리오 이미지 업로드
- [ ] 공간별 이미지 분류
- [ ] 대표 이미지 지정
- [ ] 이미지 순서 변경
- [ ] 포트폴리오 키워드
- [ ] 관리자 승인·반려

Portfolio 진행률: 38%
Company 진행률: 92%
Media 진행률: 35%
전체 진행률: 53%

## 포트폴리오 이미지 관리 완료

- [x] 이미지 업로드
- [x] 원본 저장
- [x] large 이미지 생성
- [x] medium 이미지 생성
- [x] thumbnail 이미지 생성
- [x] WebP 변환
- [x] EXIF 회전 보정
- [x] 공간별 room_code 분류
- [x] 이미지 순서 변경
- [x] 대표 이미지 자동 지정
- [x] 대표 이미지 변경
- [x] 대표 이미지 삭제 후 자동 승계
- [x] 실제 파일 삭제
- [x] 이미지 Audit Log
- [x] 이미지 Event Outbox
- [ ] 포트폴리오 키워드
- [ ] 관리자 승인·반려
- [ ] 공개 포트폴리오 조회 API

Portfolio 진행률: 60%
Media 진행률: 65%
Company 진행률: 92%
전체 진행률: 57%

## 관리자 포트폴리오 검수 완료

- [x] 승인 대기 포트폴리오 목록
- [x] 포트폴리오 승인
- [x] 포트폴리오 반려
- [x] 반려 사유 저장
- [x] 반려 후 업체 수정
- [x] 업체 재제출
- [x] 관리자 재승인
- [x] 승인 포트폴리오 숨김
- [x] 승인 시 published_at 기록
- [x] 숨김 후 published_at 유지
- [x] 관리자 포트폴리오 Audit Log
- [x] 관리자 포트폴리오 Event Outbox
- [ ] 포트폴리오 키워드 관리
- [ ] 공개 포트폴리오 조회 API
- [ ] 관리자 숨김 해제 또는 재공개

Portfolio 진행률: 75%
Admin 진행률: 50%
Media 진행률: 65%
Company 진행률: 92%
전체 진행률: 61%

## 포트폴리오 키워드 관리 완료

- [x] 키워드 마스터 데이터 등록
- [x] 키워드 목록 조회
- [x] 포트폴리오 선택 키워드 조회
- [x] 포트폴리오 키워드 저장
- [x] 기존 선택 전체 교체
- [x] 전체 선택 해제
- [x] 최대 10개 제한
- [x] 중복 선택 차단
- [x] 비활성·존재하지 않는 키워드 차단
- [x] 상태별 수정 권한 적용
- [x] 키워드 Audit Log
- [x] 키워드 Event Outbox
- [ ] 공개 포트폴리오 목록·상세 API
- [ ] 숨김 포트폴리오 재공개
- [ ] 관리자 키워드 마스터 관리

Portfolio 진행률: 85%
Admin 진행률: 50%
Media 진행률: 65%
Company 진행률: 92%
전체 진행률: 64%

## 공개 포트폴리오 기본 조회 완료

- [x] 공개 포트폴리오 목록
- [x] 공개 포트폴리오 상세
- [x] approved 상태만 공개
- [x] active 업체만 공개
- [x] 지도 공개 업체만 공개
- [x] 업체 정보 포함
- [x] 대표 이미지 포함
- [x] 상세 이미지 목록 포함
- [x] 키워드 포함
- [x] 숨김 포트폴리오 404
- [x] 존재하지 않는 포트폴리오 404
- [x] limit 및 offset 검증
- [ ] 공개 목록 전체 개수
- [ ] 지역·단지·평형·키워드 필터
- [ ] 최신순·인기순 정렬
- [ ] 숨김 포트폴리오 재공개

Portfolio 진행률: 93%
Admin 진행률: 50%
Media 진행률: 65%
Company 진행률: 92%
전체 진행률: 68%

## 공개 포트폴리오 필터·정렬 완료

- [x] 목록 전체 개수
- [x] items, total, limit, offset 응답
- [x] 시도 필터
- [x] 시군구 필터
- [x] 단지 필터
- [x] 평형 필터
- [x] 키워드 필터
- [x] 시공 범위 필터
- [x] 최신순 정렬
- [x] 인기순 정렬
- [x] 잘못된 정렬값 차단
- [x] offset 페이지 이동
- [ ] 공개 상세 조회수 증가
- [ ] 조회 이벤트 중복 방지
- [ ] 공개 포트폴리오 좋아요
- [ ] 숨김 포트폴리오 재공개

Portfolio 진행률: 96%
Admin 진행률: 50%
Media 진행률: 65%
Company 진행률: 92%
전체 진행률: 70%

## 포트폴리오 조회 이벤트 처리 완료

- [x] 공개 상세 조회수 증가
- [x] 조회 이벤트 저장
- [x] 비로그인 visitor_hash 처리
- [x] IP 원문 미저장
- [x] 로그인 사용자 user_id 처리
- [x] 비로그인 세션 ID 처리
- [x] 동일 세션 30분 중복 방지
- [x] 동일 회원 30분 중복 방지
- [x] 조회 이벤트 복합 인덱스
- [x] PortfolioViewed Event Outbox
- [ ] 좋아요 기능
- [ ] 즐겨찾기 기능
- [ ] 조회 이벤트 통계 집계
- [ ] Outbox 소비자 처리

Portfolio 진행률: 98%
Analytics 진행률: 20%
Admin 진행률: 50%
Media 진행률: 65%
Company 진행률: 92%
전체 진행률: 72%

## 포트폴리오 좋아요 완료

- [x] 좋아요 상태 조회
- [x] 좋아요 등록
- [x] 중복 좋아요 방지
- [x] 좋아요 취소
- [x] 중복 취소 안전 처리
- [x] like_count 증감
- [x] 공개 포트폴리오만 허용
- [x] 비로그인 차단
- [x] PortfolioLiked Event Outbox
- [x] PortfolioUnliked Event Outbox
- [ ] 즐겨찾기
- [ ] 댓글
- [ ] 공개 상세 is_liked 포함
- [ ] 좋아요 사용자 목록 관리자 조회

Portfolio 진행률: 99%
Analytics 진행률: 25%
Admin 진행률: 50%
Media 진행률: 65%
Company 진행률: 92%
전체 진행률: 74%

## 포트폴리오 즐겨찾기 완료

- [x] 즐겨찾기 상태 조회
- [x] 즐겨찾기 등록
- [x] 중복 등록 방지
- [x] 즐겨찾기 해제
- [x] 중복 해제 안전 처리
- [x] 내 즐겨찾기 목록
- [x] 목록 total, limit, offset
- [x] 공개 포트폴리오만 신규 등록 허용
- [x] 숨김 포트폴리오 차단
- [x] 비로그인 차단
- [x] PortfolioFavorited Event Outbox
- [x] PortfolioUnfavorited Event Outbox
- [ ] 포트폴리오 댓글
- [ ] 즐겨찾기 목록 정렬·검색
- [ ] 공개 상세 is_favorited 포함

Portfolio 진행률: 100%
Analytics 진행률: 25%
Admin 진행률: 50%
Media 진행률: 65%
Company 진행률: 92%
전체 진행률: 76%

## 포트폴리오 댓글 완료

- [x] 댓글 목록 조회
- [x] 댓글 작성
- [x] 댓글 수정
- [x] 댓글 소프트 삭제
- [x] 답글 작성
- [x] 2단계 답글 차단
- [x] 본인 댓글 수정·삭제 권한
- [x] 삭제 댓글 목록 제외
- [x] comment_count 증감
- [x] 비로그인 작성 차단
- [x] hidden 포트폴리오 작성 차단
- [x] 댓글 Event Outbox
- [ ] 댓글 신고
- [ ] 관리자 댓글 숨김·검토
- [ ] 댓글 페이지네이션 고도화

Portfolio 진행률: 100%
Analytics 진행률: 25%
Admin 진행률: 50%
Media 진행률: 65%
Company 진행률: 92%
전체 진행률: 78%

## v0.5.1 공개 포트폴리오 검색 고도화 완료

### 공개 포트폴리오 검색
- [x] 기존 sido 검색 유지
- [x] 기존 sigungu 검색 유지
- [x] 기존 complex_id 검색 유지
- [x] 기존 apartment_type_id 검색 유지
- [x] 기존 construction_scope 검색 유지
- [x] 기존 keyword_id 단일 검색 유지
- [x] latest 정렬 유지
- [x] popular 정렬 유지
- [x] limit / offset 페이지네이션 유지

### 신규 검색 기능
- [x] q 통합검색
- [x] 포트폴리오 제목 통합검색
- [x] 포트폴리오 요약 통합검색
- [x] 포트폴리오 설명 통합검색
- [x] 업체명 통합검색
- [x] 아파트 단지명 통합검색
- [x] company_id 검색
- [x] company_name 부분검색
- [x] complex_name 부분검색
- [x] keyword_ids 다중검색
- [x] 다중 키워드 AND 조건 적용
- [x] pyeong_min 검색
- [x] pyeong_max 검색
- [x] 공급면적 기준 평형 계산
- [x] 공급면적 없을 경우 전용면적 fallback
- [x] budget_min 검색
- [x] budget_max 검색
- [x] 예산범위 겹침 방식 검색

### 실제 검증
- [x] 기존 Query Parameter 9개 보존 검증
- [x] 신규 Query Parameter 9개 등록 검증
- [x] company_name 실제 검색 검증
- [x] budget_min / budget_max 실제 검색 검증
- [x] keyword_ids 3개 AND 검색 검증
- [x] 존재하지 않는 키워드 혼합 시 0건 검증
- [x] complex_name 실제 검색 검증
- [x] 33~35평 검색 검증
- [x] 40~50평 제외 검증
- [x] 단지명 q 통합검색 검증
- [x] 테스트용 단지/평형/키워드 데이터 원상복구 검증

### 다음 예정
- [ ] v0.5.2 공개 포트폴리오 이미지/미디어 응답 정리
- [ ] MY집테리어 사용자 활동 API 고도화
- [ ] 지도용 단지/평형/포트폴리오 조회 API
- [ ] 업체 공개 상세 API 고도화
- [ ] 관리자 통계/운영 기능 고도화

- [x] v0.5.4 Map Advanced - cluster/zoom/exposure policy

- [x] v0.6.0 Estimate Core

- [x] v0.6.1 Estimate Distribution & Notifications
