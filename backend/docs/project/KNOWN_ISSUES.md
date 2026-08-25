# KNOWN ISSUES
- Full Regression은 실제 운영 DB에 임시 데이터를 짧게 생성하지만 종료 시 자동 정리한다.
- 강제 종료 시 테스트 데이터가 남을 수 있으므로 `@regression.zipterior.kr` 계정은 회귀테스트 전용으로 식별 가능하다.

## v0.6.2 RC route inventory precheck 보완
- 증상: `app.routes` 직접 검사 시 include_router 기반 실제 경로가 누락된 것으로 판정됨.
- 영향: precheck 단계에서만 중단되며 코드/DB 변경 전이라 운영 영향 없음.
- 조치: 실제 `/openapi.json`의 paths/methods를 기준으로 route inventory 검증하도록 변경.
- 상태: 해결.

## v0.6.2 Regression route inventory 2차 보정
- 현상: `/openapi.json` 응답이 regression harness에서 object로 판정되지 않아 smoke test가 중단됨.
- 영향: precheck 단계에서만 중단되어 운영 v0.6.1에는 변경 없음.
- 조치: OpenAPI 및 app.routes 의존을 제거하고 auth/public portfolio/public map/estimate/notification APIRouter 자체의 routes를 직접 합산하여 필수 method/path를 검증하도록 변경.
