# ZIPTERIOR v2.1.1


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

## Status

DEPLOYED / VERIFIED
