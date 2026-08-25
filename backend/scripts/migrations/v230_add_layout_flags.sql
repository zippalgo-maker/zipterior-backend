-- v2.3.0: 평면도 이미지는 저장하지 않고 네이버의 기본형/확장형 존재 여부만 기록한다.
-- 기존 행은 아직 확인되지 않은 데이터이므로 NULL을 유지한다.
ALTER TABLE apartment_types
    ADD COLUMN IF NOT EXISTS has_basic_layout BOOLEAN,
    ADD COLUMN IF NOT EXISTS has_expanded_layout BOOLEAN;

COMMENT ON COLUMN apartment_types.has_basic_layout IS
    '네이버 타입정보에서 기본형(BASE) 존재 여부, NULL은 미확인';
COMMENT ON COLUMN apartment_types.has_expanded_layout IS
    '네이버 타입정보에서 확장형(EXPN) 존재 여부, NULL은 미확인';
