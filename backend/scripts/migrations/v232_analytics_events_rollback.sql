BEGIN;

DROP TRIGGER IF EXISTS trg_company_favorites_analytics ON company_favorites;
DROP TRIGGER IF EXISTS trg_portfolio_favorites_analytics ON portfolio_favorites;
DROP TRIGGER IF EXISTS trg_portfolio_likes_analytics ON portfolio_likes;
DROP FUNCTION IF EXISTS record_zipterior_engagement_analytics();
DROP TABLE IF EXISTS analytics_events;

COMMIT;
