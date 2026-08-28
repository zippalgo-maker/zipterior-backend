from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import check_database
from app.core.logging import configure_logging
from app.middleware.request_context import RequestContextMiddleware
from app.modules.auth.router import router as auth_router
from app.modules.oauth.router import router as oauth_router
from app.modules.companies.router import (
    company_router,
    router as companies_router,
)
from app.modules.media.router import router as media_router
from app.modules.portfolios.router import router as portfolios_router
from app.modules.portfolios.image_router import router as portfolio_images_router
from app.modules.portfolios.keyword_router import router as portfolio_keywords_router
from app.modules.portfolios.public_router import router as public_portfolios_router
from app.modules.portfolios.like_router import router as portfolio_likes_router
from app.modules.portfolios.favorite_router import router as portfolio_favorites_router
from app.modules.portfolios.comment_router import router as portfolio_comments_router
from app.modules.portfolios.report_router import router as comment_reports_router
from app.modules.admin.router import router as admin_router
from app.modules.admin.overview_router import router as admin_overview_router
from app.modules.admin.portfolio_router import router as admin_portfolios_router
from app.modules.admin.comment_moderation_router import router as admin_comment_moderation_router
from app.modules.admin.complex_router import router as admin_complexes_router
from app.modules.admin.sales_contact_router import router as admin_sales_contacts_router
from app.modules.public_map.router import router as public_map_router
from app.modules.estimates.router import router as estimates_router
from app.modules.notifications.router import router as notifications_router
from app.modules.chat.router import router as chat_router
from app.modules.company_favorites.router import router as company_favorites_router
from app.modules.users.router import router as users_router
from app.modules.operations.router import router as operations_router
from app.modules.analytics.router import (
    admin_router as admin_analytics_router,
    company_router as company_analytics_router,
    router as analytics_router,
)
from app.modules.bulk_import.router import router as admin_bulk_import_router
from app.modules.complex_region_import.router import router as admin_complex_region_import_router
from app.modules.complex_region_import.worker import start_complex_region_import_worker
from app.modules.feature_flags.router import (
    admin_router as admin_portfolio_display_settings_router,
    public_router as public_portfolio_display_settings_router,
)
from app.modules.bulk_import.worker import start_bulk_import_worker
from app.modules.mobile_intro_slides.router import (
    admin_router as admin_mobile_intro_slides_router,
    public_router as public_mobile_intro_slides_router,
)


configure_logging()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.app_debug,
)


app.include_router(auth_router)
app.include_router(oauth_router)
app.include_router(companies_router)
app.include_router(company_router)
app.include_router(media_router)
app.include_router(portfolios_router)
app.include_router(portfolio_images_router)
app.include_router(portfolio_keywords_router)
app.include_router(public_portfolios_router)
app.include_router(portfolio_likes_router)
app.include_router(portfolio_favorites_router)
app.include_router(portfolio_comments_router)
app.include_router(comment_reports_router)
app.include_router(admin_router)
app.include_router(admin_overview_router)
app.include_router(admin_portfolios_router)
app.include_router(admin_comment_moderation_router)
app.include_router(admin_complexes_router)
app.include_router(admin_sales_contacts_router)
app.include_router(public_map_router)
app.include_router(estimates_router)
app.include_router(notifications_router)
app.include_router(chat_router)
app.include_router(company_favorites_router)
app.include_router(users_router)
app.include_router(operations_router)
app.include_router(analytics_router)
app.include_router(company_analytics_router)
app.include_router(admin_analytics_router)
app.include_router(admin_bulk_import_router)
app.include_router(admin_complex_region_import_router)
app.include_router(public_portfolio_display_settings_router)
app.include_router(admin_portfolio_display_settings_router)
app.include_router(public_mobile_intro_slides_router)
app.include_router(admin_mobile_intro_slides_router)

# RequestContext를 CORS보다 안쪽에 두어 정상/오류 응답 모두 request id를 갖게 한다.
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://zipterior.kr",
        "https://www.zipterior.kr",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def start_background_workers() -> None:
    # DB 작업 상태를 기준으로 재기동 후에도 중단된 일괄등록을 이어 처리한다.
    start_bulk_import_worker()
    start_complex_region_import_worker()


@app.get("/api/health", tags=["system"])
def health() -> dict:
    try:
        database = check_database()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        ) from exc

    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "database": {
            "user": database["user"],
            "database": database["database"],
            "timezone": database["timezone"],
        },
    }
