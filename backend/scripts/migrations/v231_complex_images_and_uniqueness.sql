-- v2.3.1: 동일 단지 등록을 DB에서도 차단하고 단지 사진 여러 장을 관리한다.
-- #5는 v2.3.0 검증 중 생성된 #3의 무참조 중복본이다. 최신 타입 플래그만 #3에 병합한다.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM apartment_complexes
        WHERE id = 3 AND name = '미사역 호반 써밋'
          AND road_address = '경기 하남시 미사강변한강로 270'
    ) AND EXISTS (
        SELECT 1 FROM apartment_complexes
        WHERE id = 5 AND name = '미사역 호반 써밋'
          AND road_address = '경기 하남시 미사강변한강로 270'
    ) AND NOT EXISTS (
        SELECT 1 FROM portfolios WHERE complex_id = 5
        UNION ALL SELECT 1 FROM estimate_requests WHERE complex_id = 5
        UNION ALL SELECT 1 FROM complex_registration_requests
            WHERE completed_complex_id = 5
    ) THEN
        UPDATE apartment_types target
        SET has_basic_layout = source.has_basic_layout,
            has_expanded_layout = source.has_expanded_layout
        FROM apartment_types source
        WHERE target.complex_id = 3
          AND source.complex_id = 5
          AND lower(coalesce(target.type_name, '')) = lower(coalesce(source.type_name, ''))
          AND target.supply_area_m2 IS NOT DISTINCT FROM source.supply_area_m2
          AND target.exclusive_area_m2 IS NOT DISTINCT FROM source.exclusive_area_m2;

        DELETE FROM apartment_types WHERE complex_id = 5;
        DELETE FROM apartment_complexes WHERE id = 5;
    END IF;
END $$;

-- 이름의 장식문자·주거유형 표기와 주소 공백 차이를 제거한 활성 단지 키다.
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_complex_normalized_name_address
ON apartment_complexes (
    regexp_replace(
        regexp_replace(lower(name), '\([^)]*\)|아파트|주상복합|오피스텔', '', 'g'),
        '[^0-9a-z가-힣]', '', 'g'
    ),
    regexp_replace(
        replace(lower(coalesce(road_address, '')), '경기도', '경기'),
        '[^0-9a-z가-힣]', '', 'g'
    )
)
WHERE is_active = TRUE AND coalesce(road_address, '') <> '';

CREATE TABLE IF NOT EXISTS apartment_complex_images (
    id BIGSERIAL PRIMARY KEY,
    complex_id BIGINT NOT NULL REFERENCES apartment_complexes(id) ON DELETE CASCADE,
    image_path TEXT NOT NULL,
    thumbnail_path TEXT NOT NULL,
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_representative BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_complex_images_complex_sort
ON apartment_complex_images (complex_id, sort_order, id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_complex_images_representative
ON apartment_complex_images (complex_id)
WHERE is_representative = TRUE;

COMMENT ON TABLE apartment_complex_images IS
    '관리자가 등록한 단지 상세 이미지. 평면도와 별개이며 대표 이미지는 단지당 하나다.';
