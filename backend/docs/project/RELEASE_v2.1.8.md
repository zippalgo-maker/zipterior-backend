# v2.1.8 - Portfolio Space & Complex/Apartment Type Management

## Release Status
DEPLOYED / VERIFIED

## 주요 변경사항

### 포트폴리오 공간 관리
- `+같은 공간` 클릭 시 동일 공간이 해당 공간 바로 아래에 추가되도록 구현
- 공간 종류별 최소 1개 유지
- 마지막 공간 삭제 방지
- 포트폴리오 전체 이미지 최대 50장 제한
- 공간별 이미지 등록/삭제 및 미리보기 처리

### 포트폴리오 기본 입력
- 면적 입력 단위 명확화
- 공사기간 입력 단위 명확화
- 공사금액 입력 단위 명확화

### 단지 및 아파트 타입 관리
- 관리자 단지 추가 모달에 아파트 타입 등록 기능 추가
- 단지 생성과 최초 타입 등록을 단일 트랜잭션으로 처리
- 중간 실패 시 단지/타입 전체 rollback 검증
- 단지 상세 조회 및 기본정보 수정
- 주소 수정 시 카카오 Geocoder를 통한 주소/좌표 재확보
- 타입 추가/수정/삭제
- 마지막 타입 1개 삭제 방지
- 포트폴리오/견적에서 사용 중인 타입 삭제 시 백엔드 409 보호

### 업체 포트폴리오 단지 검색
- 카카오 단지/주소 검색
- 등록 단지와 미등록 단지 상태 구분
- 미등록 단지 선택 시 단지기본정보 등록 요청 모달
- 단지 등록 요청 처리 후 등록단지 목록 반영
- 등록된 단지 선택 시 해당 단지의 apartment_types를 조회하여 타입 선택 UI에 표시
- `/company/portfolios/complex-search` API 연동

## 주요 API
- `POST /api/v1/admin/complexes/with-types`
- `GET /api/v1/admin/complexes/{complex_id}`
- `POST /api/v1/admin/complexes/{complex_id}/types`
- `PUT /api/v1/admin/complexes/{complex_id}/types/{type_id}`
- `DELETE /api/v1/admin/complexes/{complex_id}/types/{type_id}`
- `POST /api/v1/company/portfolios/complex-search`
- `GET /api/v1/public/apartment-types`

## 검증

- 운영 서비스 `zipterior-api.service`: active
- Production `/api/health`: HTTP 200
- Admin complexes API: GET/POST 확인
- Admin complexes/with-types API: POST 확인
- Company portfolio complex-search API: POST 확인
- 등록 단지 선택 후 apartment_types 정상 조회 확인
- 미등록 단지 요청 모달 정상 동작 확인
- 단지+타입 일괄 생성 transaction 성공 검증
- transaction 실패 시 전체 rollback 검증
- Python 백엔드 문법 검사 PASS
- 운영 CSS/JS 반영 확인

## 배포/백업

- 기존 Stable Backup:
  `/srv/zipterior/backups/releases/stable_v2.1.8_20260814_144409`
- 최종 Stable Backup: /srv/zipterior/backups/releases/stable_v2.1.8_final_20260814_165925

## 상태

V2.1.8 FINAL / STABLE / VERIFIED
