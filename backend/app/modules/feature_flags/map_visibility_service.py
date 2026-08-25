"""v2.5.1: 관리자가 지도 마커·단지 기본정보를 아파트/오피스텔 유형별로
노출할지 결정하는 설정. system_features 테이블의 `map_complex_type_
visibility` 행을 그대로 읽고 쓴다 -- 실제 필터링은
`app.modules.public_map.repository`가 이 값을 직접 읽어 쿼리 조건에
반영한다(별도 공개 API 불필요). V2.5.0_PLAN.md 참고."""

from typing import Any

from sqlalchemy.orm import Session

from app.modules.feature_flags import repository

MAP_COMPLEX_TYPE_VISIBILITY_KEY = "map_complex_type_visibility"


class MapVisibilityService:
    @staticmethod
    def get(session: Session) -> dict[str, Any]:
        feature = repository.get_base_feature(
            session, MAP_COMPLEX_TYPE_VISIBILITY_KEY
        )
        settings = (feature or {}).get("settings") or {}
        return {
            "apartment_visible": settings.get("apartment_visible", True) is not False,
            "officetel_visible": settings.get("officetel_visible", True) is not False,
        }

    @staticmethod
    def update(
        session: Session,
        *,
        admin_user_id: int,
        apartment_visible: bool,
        officetel_visible: bool,
    ) -> dict[str, Any]:
        repository.merge_feature_settings(
            session,
            feature_key=MAP_COMPLEX_TYPE_VISIBILITY_KEY,
            patch={
                "apartment_visible": apartment_visible,
                "officetel_visible": officetel_visible,
            },
            updated_by=admin_user_id,
        )
        session.commit()
        return MapVisibilityService.get(session)
