# v1.1.0 Public Map Real Data Integration

이 릴리스는 기존 화면 디자인을 재작성하지 않고 `js/app.js`의 데이터 공급원을 실제 Zipterior Backend API로 연결한다.

## 안전 원칙
- 실데이터가 0건이면 기존 샘플 화면을 유지한다.
- API 장애 시 샘플/기존 UI로 fallback한다.
- 기존 HTML/CSS는 수정하지 않는다.
- 배포 직전 `/var/www/zipterior` 전체를 자동 백업한다.
- `rollback.sh`로 직전 프론트 상태 복구 가능하다.
