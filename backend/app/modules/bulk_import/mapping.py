import re
from collections import defaultdict
from typing import Any

from app.modules.bulk_import.confidence import (
    ImageRow,
    ParagraphRow,
    PortfolioConfidence,
    SpaceRow,
    build_photo_captions,
    score_portfolio,
    strip_platform_mentions,
)


# ZIPTERIOR 화면이 지원하는 공간 분류로만 변환한다. 원본의 세부 구역명은
# space_name에 그대로 보존해 공용욕실·안방욕실이나 여러 방이 섞이지 않게 한다.
SPACE_CODE_MAP = {
    "LIVING_ROOM": "living_room",
    "KITCHEN": "kitchen",
    "MASTER_BEDROOM": "master_room",
    "BEDROOM": "room",
    "KIDS_ROOM": "room",
    "STUDY": "room",
    "OFFICE": "room",
    "BATHROOM": "bathroom",
    "COMMON_BATHROOM": "bathroom",
    "MASTER_BATHROOM": "bathroom",
    "ENTRANCE": "entrance",
    "BALCONY": "balcony",
    "DRESSING_ROOM": "dressing_room",
    "DRESS_ROOM": "dressing_room",
    "UTILITY_ROOM": "utility_room",
    "LAUNDRY_ROOM": "utility_room",
}

SPACE_NAMES = {
    "LIVING_ROOM": "거실",
    "KITCHEN": "주방",
    "MASTER_BEDROOM": "안방",
    "BEDROOM": "침실",
    "KIDS_ROOM": "아이방",
    "STUDY": "서재",
    "OFFICE": "업무공간",
    "BATHROOM": "욕실",
    "COMMON_BATHROOM": "공용욕실",
    "MASTER_BATHROOM": "안방욕실",
    "ENTRANCE": "현관",
    "BALCONY": "발코니/베란다",
    "DRESSING_ROOM": "드레스룸",
    "DRESS_ROOM": "드레스룸",
    "UTILITY_ROOM": "다용도실",
    "LAUNDRY_ROOM": "세탁실",
    "HALLWAY": "복도",
    "PANTRY": "팬트리",
    "ETC": "기타",
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def source_space_key(item: dict[str, Any]) -> str:
    """Return the image section, trusting extPlace's raw room classification first."""
    raw_code = _clean(item.get("space_code") or "ETC").upper()
    sub_code = _clean(item.get("sub_space_code")).upper()
    # 하위 코드는 같은 종류 안의 세부 구역을 구별할 때만 사용한다.
    # 거실 사진에 공용욕실 하위 코드가 남는 등 원본 문서의 sticky context가
    # 다른 공간으로 이어지는 사례가 있어 무조건 sub_space를 우선하지 않는다.
    if raw_code == "BATHROOM" and sub_code in {"COMMON_BATHROOM", "MASTER_BATHROOM"}:
        return sub_code
    if raw_code == "BEDROOM" and sub_code == "MASTER_BEDROOM":
        return "MASTER_BEDROOM"
    if raw_code == "MASTER_BEDROOM":
        return "MASTER_BEDROOM"
    return raw_code or "ETC"


def description_space_key(item: dict[str, Any]) -> str:
    """Resolve copy using explicit room wording when source labels conflict."""
    raw_key = source_space_key(item)
    sub_code = _clean(item.get("sub_space_code")).upper()
    description = _clean(item.get("description"))
    compact = re.sub(r"\s+", "", description)
    bathroom_terms = sum(
        word in compact
        for word in ("욕실", "화장실", "세면대", "수전", "샤워", "양변기", "젠다이")
    )
    if bathroom_terms:
        if "안방욕실" in compact:
            return "MASTER_BATHROOM"
        if "거실욕실" in compact or "공용욕실" in compact:
            return "COMMON_BATHROOM"
        if sub_code in {"COMMON_BATHROOM", "MASTER_BATHROOM"}:
            return sub_code
    return raw_key


def grouped_portfolio_spaces(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge source rows that belong to one semantic section without mixing sections."""
    groups: dict[str, dict[str, Any]] = {}
    code_numbers: defaultdict[str, int] = defaultdict(int)
    ordered_spaces = sorted(
        item.get("spaces") or [],
        key=lambda space: (_positive_int(space.get("space_order"), 1_000_000),),
    )
    for source_index, space in enumerate(ordered_spaces):
        image_key = source_space_key(space)
        image_group = _ensure_group(groups, code_numbers, image_key)
        image_group["source_orders"].append(
            _positive_int(space.get("space_order"), source_index + 1)
        )
        description = str(space.get("description") or "").strip()
        if description:
            copy_key = description_space_key(space)
            copy_group = _ensure_group(groups, code_numbers, copy_key)
            if description not in copy_group["descriptions"]:
                copy_group["descriptions"].append(description)
            if copy_group is not image_group:
                copy_group["source_orders"].append(
                    _positive_int(space.get("space_order"), source_index + 1)
                )

    result = []
    for group in groups.values():
        result.append(
            {
                **group,
                "description": "\n\n".join(group.pop("descriptions"))[:30000] or None,
            }
        )
    return result


def portfolio_overview(item: dict[str, Any]) -> str:
    """Build portfolio-level copy only from project metadata, never from room copy."""
    title = _clean(item.get("title"))
    apartment = _clean(item.get("apartment_name"))
    area = _clean(item.get("area_pyeong"))
    residence = _clean(item.get("residence_type"))
    expertise = _clean(item.get("expertise")) or "인테리어"
    style = _deduplicated_list(item.get("style"))
    family = _clean(item.get("family"))
    construction = _deduplicated_list(item.get("construction"))

    subject_parts = []
    if apartment:
        subject_parts.append(apartment)
    if area and area not in apartment:
        subject_parts.append(area)
    if residence and residence not in apartment:
        subject_parts.append(residence)
    subject = " ".join(subject_parts) or title or "주거 공간"

    paragraphs = [f"{subject} {expertise} 포트폴리오입니다."]
    if style:
        paragraphs.append(f"전체 콘셉트는 {style} 스타일입니다.")
    if family:
        paragraphs.append(f"생활 구성은 {family} 기준으로 계획했습니다.")
    if construction:
        paragraphs.append(f"주요 공사 범위는 {construction}입니다.")
    return "\n\n".join(paragraphs)[:30000]


def content_blocks_overview(item: dict[str, Any]) -> str | None:
    """v2.5.0 (테스트, additive): content_blocks[]가 있는 포트폴리오는 원본
    작성자가 실제로 쓴 첫 본문 문단을 description으로 그대로 쓴다 --
    portfolio_overview()의 메타데이터 조합 문장("OO 포트폴리오입니다. 전체
    콘셉트는...") 대신이다. 원본 스타일/공사범위를 억지로 문장화하지 않고
    실제 글을 우선한다. 문서 맨 앞의 커버 이미지(node_type='image')는
    건너뛰고, 첫 번째 실제 본문 문단(node_type='p', 텍스트 있음)만 쓴다 --
    h2/h4 같은 소제목이나 callout 박스를 만나면 그 전까지 못 찾은 것으로
    보고 None을 반환한다(무리해서 이상한 문단을 끌어오지 않음).
    summary(카드 요약)에는 이걸 쓰지 않는다 -- portfolio_summary()가 이미
    항상 담당하며, 여기서 같은 텍스트를 또 쓰면 description과 겹치는
    문제가 재발한다(오늘 이전 세션에서 고친 것과 같은 종류의 버그)."""
    blocks = sorted(
        item.get("content_blocks") or [],
        key=lambda b: _positive_int(b.get("document_order"), 0),
    )
    for block in blocks:
        node_type = _clean(block.get("node_type"))
        if node_type == "image":
            continue
        if node_type in ("h2", "h3", "h4", "callout"):
            return None
        text_value = _clean(block.get("text"))
        if text_value:
            return text_value[:30000]
    return None


def portfolio_summary(item: dict[str, Any]) -> str:
    """Use project facts for the card summary instead of the company introduction."""
    overview = portfolio_overview(item)
    return overview.split("\n\n", 1)[0][:1000]


def _excluded_photo_keys(item: dict[str, Any]) -> tuple[set[Any], set[str]]:
    """Identify photos that must never be shown on ZIPTERIOR, in either the
    structured room gallery (`select_portfolio_images`) or the verbatim
    document reproduction (`content_blocks_from_item`) -- a photo excluded
    from one must be excluded from both, or it still reaches the public
    screen through the other path (실제로 발견된 문제: 갤러리에서는 빠졌는데
    문서 재현 쪽엔 그대로 남아 고객 화면에 노출됨).

    Two rules (v2.5.0):
    - `space_code == "ETC"`(기타) 사진 -- 광고/도면/태그 실패 사진이 대부분이다.
    - 문서/사진 순서 기준 마지막 두 장 중 `classification_source`가
      "text_context"인 것 -- 본문 끝 저작권/홍보 안내 옆에 붙은 실제 방 사진이
      아닌 카드인 경우가 실측으로 확인됨. 마지막 두 장에만 적용한다(본문
      중간의 text_context 사진은 정상 사진일 수 있어 그대로 둔다).

    Returns (ext_card_ids, image_urls) -- `content_blocks_from_item`의 이미지
    노드는 `images[]`와 다른 배열이라 이 두 키로 대조해서 같은 사진을 찾는다.
    """
    all_images = list(item.get("images") or [])
    ordered_all = sorted(
        enumerate(all_images),
        key=lambda pair: _image_order(pair[1], pair[0]),
    )
    excluded_tail_indexes = {
        index
        for index, image in ordered_all[-2:]
        if _clean(image.get("classification_source")).lower() == "text_context"
    }
    ext_card_ids: set[Any] = set()
    image_urls: set[str] = set()
    for index, image in enumerate(all_images):
        if source_space_key(image) != "ETC" and index not in excluded_tail_indexes:
            continue
        card_id = image.get("ext_card_id")
        if card_id not in (None, ""):
            ext_card_ids.add(card_id)
        url = _clean(image.get("image_url"))
        if url:
            image_urls.add(url)
    return ext_card_ids, image_urls


def select_portfolio_images(
    item: dict[str, Any],
    *,
    max_images: int | None,
) -> list[dict[str, Any]]:
    """Select completed images while retaining at least one image per source
    section. `max_images=None` means no cap -- every AFTER-phase image in the
    source is registered, in original document/image order.

    Excludes the photos identified by `_excluded_photo_keys` (ETC-tagged, and
    the trailing text_context pair) before the AFTER-phase filter -- see that
    function's docstring."""
    all_images = list(item.get("images") or [])
    excluded_card_ids, excluded_urls = _excluded_photo_keys(item)

    indexed = [
        (index, image)
        for index, image in enumerate(all_images)
        if _clean(image.get("phase")).upper() == "AFTER"
        and image.get("ext_card_id") not in excluded_card_ids
        and _clean(image.get("image_url")) not in excluded_urls
    ]
    indexed.sort(key=lambda pair: _image_order(pair[1], pair[0]))

    if max_images is None:
        return [image for _index, image in indexed]
    if max_images <= 0:
        return []

    by_space: defaultdict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for pair in indexed:
        by_space[source_space_key(pair[1])].append(pair)

    space_order = [group["key"] for group in grouped_portfolio_spaces(item)]
    selected_indexes: set[int] = set()
    for key in space_order:
        candidates = by_space.get(key) or []
        if not candidates or len(selected_indexes) >= max_images:
            continue
        # 공간 대표 한 장은 신뢰도가 높은 사진을 우선한다. 나머지 사진의
        # 표시 순서는 선택 후 원문 document/image 순서로 다시 정렬한다.
        best = min(
            candidates,
            key=lambda pair: (
                _confidence_rank(pair[1].get("classification_confidence")),
                _image_order(pair[1], pair[0]),
            ),
        )
        selected_indexes.add(best[0])

    # 앞쪽 거실 사진만 한도를 독점하던 기존 순차 절단을 대체한다. 각 공간의
    # 다음 사진을 한 장씩 순환 선택해 주방·욕실·방 사진도 고르게 남긴다.
    while len(selected_indexes) < max_images:
        added = False
        for key in space_order:
            for index, _image in by_space.get(key) or []:
                if index in selected_indexes:
                    continue
                selected_indexes.add(index)
                added = True
                break
            if len(selected_indexes) >= max_images:
                break
        if not added:
            break

    selected = [
        (index, image)
        for index, image in indexed
        if index in selected_indexes
    ]
    selected.sort(key=lambda pair: _image_order(pair[1], pair[0]))
    return [image for _index, image in selected]


def representative_image_index(
    space_groups: list[dict[str, Any]],
    selected_images: list[dict[str, Any]],
) -> int:
    """대표사진 선택: 거실(LIVING_ROOM) 사진이 있으면 그 중에서, 없으면
    (부분 리모델링, 예: 주방만) 첫 번째로 나오는 실제 공간(space_order
    기준, '기타'는 광고/도면 사진일 때가 많아 제외)의 사진 중에서 고른다.
    같은 공간 안에서도 그냥 첫 장을 쓰지 않고 classification_confidence가
    가장 높은 사진을 고른다 -- 실측 결과 그 공간으로 분류된 첫 장이
    평면도/광고 이미지인데 신뢰도가 LOW로 낮게 찍힌 채 순서만 앞서는
    경우가 있었다(예: 도면이 "text_context/LOW"로 KITCHEN 분류됨).
    신뢰도가 동점이면 문서 순서가 빠른 쪽. 아무것도 못 찾으면 이전 동작과 동일하게
    0번(맨 처음 선택된 사진)."""
    has_living_room = any(g["key"] == "LIVING_ROOM" for g in space_groups)
    if has_living_room:
        target_key = "LIVING_ROOM"
    else:
        target_key = next(
            (g["key"] for g in space_groups if g["key"] != "ETC"), None
        )
    if target_key:
        candidates = [
            (i, image) for i, image in enumerate(selected_images)
            if source_space_key(image) == target_key
        ]
        if candidates:
            best = min(
                candidates,
                key=lambda pair: (
                    _confidence_rank(pair[1].get("classification_confidence")),
                    pair[0],
                ),
            )
            return best[0]
    return 0


def _paragraph_rows(item: dict[str, Any]) -> list[ParagraphRow]:
    return [
        ParagraphRow(
            document_order=_positive_int(p.get("document_order"), 0),
            node_type=str(p.get("node_type") or "p"),
            space_code=p.get("space_code"),
            sub_space_name=p.get("sub_space_name"),
            text=str(p.get("text") or ""),
        )
        for p in item.get("paragraphs") or []
    ]


def _image_rows(item: dict[str, Any]) -> list[ImageRow]:
    return [
        ImageRow(
            document_order=_positive_int(image.get("document_order"), 0),
            space_code=image.get("space_code"),
            sub_space_name=image.get("sub_space_name"),
            space_name=image.get("space_name"),
            phase=image.get("phase"),
        )
        for image in item.get("images") or []
    ]


def build_confidence(item: dict[str, Any]) -> PortfolioConfidence | None:
    """Compute structural confidence + reconstructed intro/room/closing text
    from the source's paragraph-level data (document_order per paragraph),
    when present. Returns None for input that doesn't carry that granularity
    (older-format JSON without 'paragraphs') -- callers fall back to
    portfolio_overview()/spaces[].description as before, unchanged."""
    if not item.get("paragraphs"):
        return None
    known_spaces = [
        SpaceRow(
            space_code=space.get("space_code"),
            space_name=space.get("space_name"),
            sub_space_name=space.get("sub_space_name"),
        )
        for space in item.get("spaces") or []
    ]
    return score_portfolio(_paragraph_rows(item), _image_rows(item), known_spaces)


def build_image_captions(item: dict[str, Any]) -> tuple[dict[str, str], dict[int, str]] | None:
    """Split each room's text into its opening description (before that
    room's first photo) and a caption per individual photo, when the source
    carries paragraph-level data. Returns None otherwise -- callers keep
    showing one description block per room with no per-photo captions."""
    if not item.get("paragraphs"):
        return None
    return build_photo_captions(_paragraph_rows(item), _image_rows(item))


def _norm_space_name(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


# v2.5.0 (테스트, additive): 원본 문서 순서 재현용 -- portfolio_spaces/
# portfolio_images(검색·필터·공간분류용)는 그대로 두고, 상세페이지 원문
# 재현은 이 블록들만으로 별도로 시험한다. node_type은 크롤러가 준 원본
# 타입 문자열 그대로 저장하고, block_type은 렌더러가 템플릿을 고르기
# 위한 정규화 값이다 -- 처음 보는 node_type도 'unknown'으로 저장하되
# raw_node에는 원본을 그대로 남겨 데이터를 버리지 않는다.
_BLOCK_TYPE_MAP: dict[str, str] = {
    "p": "text",
    "h2": "heading",
    "h3": "heading",
    "h4": "heading",
    "callout": "callout",
    "quote": "text",
    "image": "image",
    "hr": "divider",
    "button": "link",
    "video": "video",
    "product": "product",
}


def _opt_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


# v2.5.0: 오늘의집 자체 홍보용 고정 문구. confidence.py의 strip_platform_mentions
# (오늘의집/오늘의 집/오집/집들이 단어 제거)와 별개로, 이건 "⚡리모델링 솔루션
# 미리보기"처럼 단어 하나가 아니라 헤딩 전체가 홍보문구인 경우다. 앞뒤에 붙는
# 이모지/특수문자/숫자까지 통째로 지운다 -- [^가-힣]*는 "한글 음절이 아닌 모든
# 문자"라 이모지·기호·숫자·영문을 다 걸러내면서 정작 한글 문장은 건드리지 않는다.
_PROMO_PHRASES = ["리모델링 솔루션 미리보기"]
_PROMO_PHRASE_PATTERN = re.compile(
    "|".join(
        rf"[^가-힣]*{re.escape(phrase).replace(re.escape(' '), r'\s*')}[^가-힣]*"
        for phrase in _PROMO_PHRASES
    )
)

# v2.5.0: 원문 "인테리어 영수증 (미포함)"/"인테리어 영수증 (vat 미포함)" 같은
# 제목을 "얼마 들었을까요?"로 바꾼다. 원본에 미포함/vat미포함 표시가 있었으면
# "(부가세 미포함)"을 무조건 붙이고, 표시가 아예 없었으면 제목만 바꾼다.
_RECEIPT_TITLE_PATTERN = re.compile(
    r"인테리어\s*영수증(?:\s*\(\s*(?:vat\s*)?미포함\s*\))?", re.IGNORECASE
)


def _normalize_receipt_title(text: str) -> tuple[str, bool]:
    def _replace(match: re.Match[str]) -> str:
        matched = match.group(0)
        return "얼마 들었을까요?" + ("(부가세 미포함)" if "미포함" in matched else "")

    new_text, count = _RECEIPT_TITLE_PATTERN.subn(_replace, text)
    return new_text, count > 0


def _clean_text_string(value: str) -> tuple[str, dict[str, int]]:
    """One shared cleaning pass for every string that ends up on the public
    document-reproduction screen (content_blocks) -- platform-name words,
    the promo heading phrase, and the receipt title rename all go through
    here so text_content and raw_node's rich-text spans (which the frontend
    actually renders from) never drift out of sync."""
    stats = {"platform_mentions_removed": 0, "receipt_titles_normalized": 0}
    cleaned, found = strip_platform_mentions(value)
    if found:
        stats["platform_mentions_removed"] += 1
    before_promo = cleaned
    cleaned = _PROMO_PHRASE_PATTERN.sub("", cleaned)
    if cleaned != before_promo:
        stats["platform_mentions_removed"] += 1
    cleaned, receipt_hit = _normalize_receipt_title(cleaned)
    if receipt_hit:
        stats["receipt_titles_normalized"] += 1
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned, stats


def _accumulate_stats(total: dict[str, int], part: dict[str, int]) -> None:
    for key, value in part.items():
        total[key] = total.get(key, 0) + value


def _clean_raw_node_text(node: Any) -> tuple[Any, dict[str, int]]:
    """Recursively clean every string inside a raw_node's rich-text span
    `content` arrays (used by both `text` and `titleText`, callout/heading
    alike) -- the frontend renders straight from raw_node, not text_content,
    so cleaning only the flat text_content column would leave the visible
    page untouched. Structure-preserving: only strings under a "content" key
    are ever rewritten, everything else (entity styling, node type, ...)
    passes through unchanged."""
    total: dict[str, int] = {}
    if isinstance(node, dict):
        new_node: dict[str, Any] = {}
        for key, value in node.items():
            if key == "content" and isinstance(value, list):
                new_content = []
                for item in value:
                    if isinstance(item, str):
                        cleaned, stats = _clean_text_string(item)
                        _accumulate_stats(total, stats)
                        new_content.append(cleaned)
                    else:
                        cleaned_item, stats = _clean_raw_node_text(item)
                        _accumulate_stats(total, stats)
                        new_content.append(cleaned_item)
                new_node[key] = new_content
            else:
                cleaned_value, stats = _clean_raw_node_text(value)
                _accumulate_stats(total, stats)
                new_node[key] = cleaned_value
        return new_node, total
    if isinstance(node, list):
        new_list = []
        for item in node:
            cleaned_item, stats = _clean_raw_node_text(item)
            _accumulate_stats(total, stats)
            new_list.append(cleaned_item)
        return new_list, total
    return node, total


def content_blocks_from_item(
    item: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Normalize the source's raw `content_blocks[]` (one row per original
    bpdDocument.contents node, document_order == that array's own index --
    never recomputed here) into rows ready for
    `bulk_import.repository.replace_content_blocks`. Returns `([], zeroed
    stats)` when the source doesn't carry this data (older-schema JSON) --
    callers should treat that as "nothing to do", not an error.

    Skips `image` blocks matched (by ext_card_id, falling back to image_url)
    to `_excluded_photo_keys(item)` -- ETC-tagged / trailing text_context
    photos must not reach the public document reproduction either, or a
    photo dropped from the room gallery still shows up here (실제로 있었던
    문제: select_portfolio_images만 고쳤을 때 이 화면엔 그대로 남아있었음).

    Every text-bearing block goes through `_clean_text_string`/
    `_clean_raw_node_text` (platform mentions, promo heading, receipt title
    rename) before being stored -- document_order keeps its original gaps,
    nothing is renumbered, and non-text fields (image_url, entity styling
    등) are untouched."""
    excluded_card_ids, excluded_urls = _excluded_photo_keys(item)
    rows = []
    total_stats = {"platform_mentions_removed": 0, "receipt_titles_normalized": 0}
    for block in item.get("content_blocks") or []:
        node_type = _clean(block.get("node_type")) or "unknown"
        if node_type == "image" and (
            block.get("ext_card_id") in excluded_card_ids
            or _clean(block.get("image_url")) in excluded_urls
        ):
            continue
        text_content, text_stats = _clean_text_string(_clean(block.get("text")) or "")
        _accumulate_stats(total_stats, text_stats)
        raw_node, raw_stats = _clean_raw_node_text(block.get("raw_node") or {})
        _accumulate_stats(total_stats, raw_stats)
        rows.append({
            "document_order": _positive_int(block.get("document_order"), 0),
            "node_type": node_type,
            "block_type": _BLOCK_TYPE_MAP.get(node_type, "unknown"),
            "text_content": text_content or None,
            "image_url": _clean(block.get("image_url")) or None,
            "image_width": _opt_int(block.get("width")),
            "image_height": _opt_int(block.get("height")),
            "raw_node": raw_node,
            "metadata_json": (
                {"ext_card_id": block.get("ext_card_id")}
                if block.get("ext_card_id") not in (None, "")
                else {}
            ),
        })
    rows.sort(key=lambda r: r["document_order"])
    return rows, total_stats


def apply_confidence_text(
    space_groups: list[dict[str, Any]],
    confidence: PortfolioConfidence,
    room_openings: dict[str, str] | None = None,
) -> None:
    """Overwrite each group's description with the paragraph-reconstructed
    text for that room, where confidence.py found a matching, non-empty
    section. Groups with no match keep their original spaces[]-derived
    description untouched -- nothing is deleted, only improved where a
    better (paragraph-level, correctly ordered) source exists.

    When `room_openings` is given (from `build_image_captions`), it's used
    in preference to the section's full text -- the room-level description
    should only be the opening paragraphs before that room's first photo;
    the rest is attached to individual photos as their own captions instead
    of being duplicated here."""
    openings_by_name = {
        _norm_space_name(label): text for label, text in (room_openings or {}).items()
    }
    by_name: defaultdict[str, list[Any]] = defaultdict(list)
    for section in confidence.sections:
        if section.text:
            by_name[_norm_space_name(section.label)].append(section)
    for group in space_groups:
        key = _norm_space_name(group["space_name"])
        if key in openings_by_name:
            # present even when empty: all of this room's text went to
            # individual photo captions instead, so the room-level
            # description should be cleared rather than keep stale text.
            group["description"] = openings_by_name[key] or None
            continue
        candidates = by_name.get(key)
        if candidates:
            group["description"] = candidates.pop(0).text


def portfolio_overview_from_confidence(confidence: PortfolioConfidence) -> str | None:
    """Build the top-level description from the source's own intro/closing
    paragraphs instead of metadata tags, when paragraph data produced real
    intro text. Returns None when there's nothing usable -- callers keep
    the existing metadata-based portfolio_overview() in that case."""
    if not confidence.intro_text:
        return None
    parts = [confidence.intro_text]
    if confidence.closing_text:
        parts.append(confidence.closing_text)
    return "\n\n".join(parts)[:30000]


def _positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def _ensure_group(
    groups: dict[str, dict[str, Any]],
    code_numbers: defaultdict[str, int],
    source_code: str,
) -> dict[str, Any]:
    group = groups.get(source_code)
    if group is not None:
        return group
    platform_code = SPACE_CODE_MAP.get(source_code, "etc")
    code_numbers[platform_code] += 1
    group = {
        "key": source_code,
        "source_code": source_code,
        "space_code": platform_code,
        "space_name": SPACE_NAMES.get(source_code, "기타"),
        "space_number": code_numbers[platform_code],
        "sort_order": len(groups),
        "source_orders": [],
        "descriptions": [],
    }
    groups[source_code] = group
    return group


def _deduplicated_list(value: Any) -> str:
    parts = [_clean(part) for part in str(value or "").split("|")]
    unique = []
    for part in parts:
        if part and part not in unique:
            unique.append(part)
    return " · ".join(unique)


def _image_order(image: dict[str, Any], source_index: int) -> tuple[int, int, int]:
    return (
        _positive_int(image.get("document_order"), 1_000_000),
        _positive_int(image.get("image_order"), 1_000_000),
        source_index,
    )


def _confidence_rank(value: Any) -> int:
    return {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(_clean(value).upper(), 3)
