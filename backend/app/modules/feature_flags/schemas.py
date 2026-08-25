from pydantic import BaseModel, Field


# v2.5.1: 포트폴리오 상세 하단 표시 설정(2건 요청) --
# 1) 크롤링 원본에 포함된 SNS/블로그 링크 노출 여부(전역 토글)
# 2) 하단 고정 안내문구/이미지 + 견적문의 CTA 버튼 문구
# system_features 테이블의 두 feature_key(portfolio_bottom_sns_links,
# portfolio_bottom_notice)를 그대로 읽고 쓴다. V2.5.0_PLAN.md 참고.

DEFAULT_NOTICE_BUTTON_LABEL = "이 포트폴리오의 집 인테리어 견적 문의하기"


class PortfolioDisplaySettingsResponse(BaseModel):
    sns_links_enabled: bool
    notice_enabled: bool
    notice_text: str | None = None
    notice_image_path: str | None = None
    notice_button_label: str = DEFAULT_NOTICE_BUTTON_LABEL


class PortfolioDisplaySettingsUpdateRequest(BaseModel):
    sns_links_enabled: bool | None = None
    notice_enabled: bool | None = None
    notice_text: str | None = Field(default=None, max_length=2000)
    notice_button_label: str | None = Field(default=None, min_length=1, max_length=100)


class NoticeImageUploadResponse(BaseModel):
    notice_image_path: str | None


# v2.5.1: 지도 마커·단지 기본정보를 아파트/오피스텔 유형별로 노출 여부
# 결정하는 설정. 공개 API는 없음 -- public_map/repository.py가 서버
# 쪽에서 직접 이 설정을 읽어 쿼리 조건에 반영한다(프론트가 알 필요
# 없음). 관리자 조회/수정만 제공. V2.5.0_PLAN.md 참고.
class MapComplexTypeVisibilityResponse(BaseModel):
    apartment_visible: bool
    officetel_visible: bool


class MapComplexTypeVisibilityUpdateRequest(BaseModel):
    apartment_visible: bool
    officetel_visible: bool
