BEGIN;

-- v2.3.2 replaces the browser-only test counter with first-party server analytics.
-- Tokens, cookies, form values and precise IP addresses are deliberately excluded.
CREATE TABLE IF NOT EXISTS analytics_events (
    id BIGSERIAL PRIMARY KEY,
    client_event_id VARCHAR(64) UNIQUE,
    session_id VARCHAR(64),
    user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    company_id BIGINT REFERENCES companies(id) ON DELETE SET NULL,
    portfolio_id BIGINT REFERENCES portfolios(id) ON DELETE SET NULL,
    complex_id BIGINT REFERENCES apartment_complexes(id) ON DELETE SET NULL,
    event_type VARCHAR(40) NOT NULL,
    duration_seconds INTEGER,
    search_query VARCHAR(200),
    page_path VARCHAR(500),
    referrer VARCHAR(1000),
    traffic_source VARCHAR(80),
    browser VARCHAR(40),
    operating_system VARCHAR(40),
    device_type VARCHAR(20),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT analytics_events_duration_check
        CHECK (duration_seconds IS NULL OR duration_seconds BETWEEN 0 AND 86400),
    CONSTRAINT analytics_events_type_check CHECK (event_type IN (
        'page_view','search','search_select','company_view','company_dwell',
        'portfolio_view','portfolio_dwell','inquiry_submit',
        'company_favorite_add','company_favorite_remove',
        'portfolio_favorite_add','portfolio_favorite_remove',
        'portfolio_like_add','portfolio_like_remove'
    ))
);

CREATE INDEX IF NOT EXISTS idx_analytics_events_occurred
    ON analytics_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_events_company_occurred
    ON analytics_events (company_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_events_portfolio_occurred
    ON analytics_events (portfolio_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_events_type_occurred
    ON analytics_events (event_type, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_events_session_occurred
    ON analytics_events (session_id, occurred_at DESC)
    WHERE session_id IS NOT NULL;

-- Favorite/like changes are recorded at the database boundary so every UI and API
-- follows one authoritative path and add/remove history cannot be missed.
CREATE OR REPLACE FUNCTION record_zipterior_engagement_analytics()
RETURNS TRIGGER AS $$
DECLARE
    resolved_company_id BIGINT;
    resolved_portfolio_id BIGINT;
    resolved_user_id BIGINT;
    resolved_event_type VARCHAR(40);
BEGIN
    IF TG_TABLE_NAME = 'company_favorites' THEN
        resolved_company_id := COALESCE(NEW.company_id, OLD.company_id);
        resolved_user_id := COALESCE(NEW.user_id, OLD.user_id);
        resolved_event_type := CASE WHEN TG_OP = 'INSERT'
            THEN 'company_favorite_add' ELSE 'company_favorite_remove' END;
    ELSE
        resolved_portfolio_id := COALESCE(NEW.portfolio_id, OLD.portfolio_id);
        resolved_user_id := COALESCE(NEW.user_id, OLD.user_id);
        SELECT company_id INTO resolved_company_id
        FROM portfolios WHERE id = resolved_portfolio_id;
        IF TG_TABLE_NAME = 'portfolio_likes' THEN
            resolved_event_type := CASE WHEN TG_OP = 'INSERT'
                THEN 'portfolio_like_add' ELSE 'portfolio_like_remove' END;
        ELSE
            resolved_event_type := CASE WHEN TG_OP = 'INSERT'
                THEN 'portfolio_favorite_add' ELSE 'portfolio_favorite_remove' END;
        END IF;
    END IF;

    INSERT INTO analytics_events (
        user_id, company_id, portfolio_id, event_type, metadata
    ) VALUES (
        resolved_user_id, resolved_company_id, resolved_portfolio_id,
        resolved_event_type, jsonb_build_object('source', 'database_trigger')
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_company_favorites_analytics ON company_favorites;
CREATE TRIGGER trg_company_favorites_analytics
AFTER INSERT OR DELETE ON company_favorites
FOR EACH ROW EXECUTE FUNCTION record_zipterior_engagement_analytics();

DROP TRIGGER IF EXISTS trg_portfolio_favorites_analytics ON portfolio_favorites;
CREATE TRIGGER trg_portfolio_favorites_analytics
AFTER INSERT OR DELETE ON portfolio_favorites
FOR EACH ROW EXECUTE FUNCTION record_zipterior_engagement_analytics();

DROP TRIGGER IF EXISTS trg_portfolio_likes_analytics ON portfolio_likes;
CREATE TRIGGER trg_portfolio_likes_analytics
AFTER INSERT OR DELETE ON portfolio_likes
FOR EACH ROW EXECUTE FUNCTION record_zipterior_engagement_analytics();

COMMIT;
