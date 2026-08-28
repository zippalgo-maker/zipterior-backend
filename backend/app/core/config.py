from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Zipterior API"
    # 운영 .env가 우선이며 이 값은 개발·Release 검증용 fallback이다.
    # v2.2.1부터 health/OpenAPI가 과거 기본값으로 롤백되지 않도록 Release와 함께 갱신한다.
    app_version: str = "2.4.1"
    app_env: str = "development"
    app_debug: bool = False

    database_host: str = "127.0.0.1"
    database_port: int = 5432
    database_name: str
    database_user: str
    database_password: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # v0.6.3 production hardening defaults.
    # 기존 .env 값을 강제로 바꾸지 않고 운영 전환 시 환경변수로 조정한다.
    log_level: str = "INFO"
    request_log_enabled: bool = True
    request_id_header: str = "X-Request-ID"
    slow_request_ms: int = 1500
    rate_limit_enabled: bool = False
    rate_limit_requests_per_minute: int = 120

    # v2.5.1: 건물명 기반 단지 자동 매칭(서버 사이드)에 쓴다. 프론트의
    # kakao_js_key(admin-dashboard.html에 하드코딩)와는 별개 키 --
    # /srv/zipterior/config/kakao_maps.env가 SSOT, .env는 안 건드린다.
    kakao_rest_key: str | None = None

    # v2.5.1: 시군구 기준 네이버부동산 단지 자동수집 기능에 쓴다. 공공데이터
    # 포털(data.go.kr) "행정안전부_행정표준코드_법정동코드" API 키 --
    # 이미 URL 인코딩된 "Encoding" 키를 그대로 저장하고 쓸 때도 추가
    # urlencode 없이 그대로 쿼리스트링에 붙인다. V2.5.0_PLAN.md 참고.
    data_go_kr_stanregincd_key: str | None = None

    # v2.5.57(2026-08-24): SNS(소셜) 로그인. 사용자가 각 제공사 개발자
    # 콘솔에서 직접 발급받아 나중에 채워 넣을 값들 -- 지금은 비어 있어도
    # 서버가 정상 기동하고, 미설정 상태로 로그인 시도하면 (500이 아니라)
    # "준비 중"으로 안전하게 안내한다(app/modules/oauth/service.py의
    # is_configured 체크 참고). redirect_uri는 이 public_base_url +
    # "/api/v1/auth/oauth/{provider}/callback"로 서버가 조합하므로 각
    # 제공사 콘솔에 등록할 콜백 URL도 이 규칙을 따라야 한다.
    public_base_url: str = "https://zipterior.kr"
    oauth_state_secret: str | None = None
    kakao_oauth_client_id: str | None = None
    kakao_oauth_client_secret: str | None = None
    naver_oauth_client_id: str | None = None
    naver_oauth_client_secret: str | None = None
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None

    # 2026-08-26: 집팔고360 SSO 연동(iframe 임베드 시 자동 로그인).
    # 미설정이면(둘 다 None/기본값) 기존과 동일하게 안전 폴백 — SSO
    # exchange 엔드포인트가 그냥 None을 반환하고 프론트는 자체 로그인
    # 화면으로 이어짐. zippalgo360 저장소 docs/WORK_LOG.md 참고.
    sso_shared_secret: str | None = None
    zippalgo360_api_base_url: str = "https://zippalgo360.com"

    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", Path("/srv/zipterior/config/kakao_maps.env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.database_user,
            password=self.database_password,
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    def runtime_warnings(self) -> list[str]:
        warnings: list[str] = []
        if self.is_production and self.app_debug:
            warnings.append("production 환경에서는 APP_DEBUG=false 여야 합니다.")
        if len(self.jwt_secret_key) < 32:
            warnings.append("JWT_SECRET_KEY는 최소 32자 이상을 권장합니다.")
        if self.rate_limit_requests_per_minute < 1:
            warnings.append("RATE_LIMIT_REQUESTS_PER_MINUTE는 1 이상이어야 합니다.")
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
