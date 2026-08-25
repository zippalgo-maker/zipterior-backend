"""Structural confidence scoring for bulk-imported portfolio text/image placement.

No content understanding is used anywhere in this module -- every signal is
derived from structure already present in the source data: explicit section
headings, the `sub_space_name`/`space_code` fields the source crawler already
assigned, and `document_order` (each paragraph's and each image's position in
the original document).

Core principle (v2.5.0 design, see /srv/zipterior/V2.5.0_PLAN.md): the goal is
not to guess the "correct" room name for a sentence, it is to preserve the
same text/image adjacency the original document had. A paragraph that sits
right next to a room's photos in the source should end up right next to that
same room's photos on zipterior -- readers should feel no discontinuity
versus the original listing.

Confidence is computed per SECTION (a room-label group of text+images), not
one number per portfolio. The portfolio-level number a reviewer sees is the
minimum across its sections, so one weak section can't hide behind several
strong ones.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Vocabulary

SPACE_CODE_STANDARD: dict[str, str] = {
    "LIVING_ROOM": "거실",
    "KITCHEN": "주방",
    "ENTRANCE": "현관",
    "BEDROOM": "침실",
    "MASTER_BEDROOM": "안방",
    "KIDS_ROOM": "아이방",
    "BATHROOM": "욕실",
    "DRESS_ROOM": "드레스룸",
    "POWDER_ROOM": "파우더룸",
    "STUDY": "서재",
    "BALCONY": "발코니/베란다",
    "LAUNDRY_ROOM": "세탁실",
    "PANTRY": "팬트리",
    "HALLWAY": "복도",
    "OFFICE": "사무공간",
    "ETC": "기타",
}

# Room-name vocabulary accepted as a *heading* when no structural h2/h3/h4 tag
# exists but a short standalone line names a room outright (e.g. "현관",
# "공용욕실", "Entrance"). Deliberately narrow -- a false positive here turns
# an ordinary sentence into a fabricated section boundary.
_STRICT_KO_HEADINGS = {
    "거실", "주방", "현관", "욕실", "공용욕실", "안방욕실", "부부욕실", "거실욕실",
    "침실", "작은침실", "안방", "부부침실", "서재", "아이방", "발코니", "베란다",
    "발코니/베란다", "드레스룸", "파우더룸", "복도", "세탁실", "팬트리", "기타",
    "입구방", "작은방", "메인룸", "각방", "기타방", "안방드레스룸", "방",
}
_STRICT_KO_NOSPACE = {s.replace(" ", ""): s for s in _STRICT_KO_HEADINGS}

_EN_HEADING_TO_KO = {
    "entrance": "현관", "foyer": "현관",
    "living room": "거실", "livingroom": "거실", "living & dining": "거실", "living and dining": "거실",
    "kitchen": "주방", "kitchen & dining": "주방", "dining": "주방",
    "bathroom": "욕실", "bath room": "욕실", "bath": "욕실",
    "bedroom": "침실", "bed room": "침실", "room": "침실",
    "master bedroom": "안방", "master room": "안방", "main room": "안방",
    "other rooms": "기타방", "other room": "기타방",
    "dress room": "드레스룸", "dressroom": "드레스룸",
    "balcony": "발코니", "veranda": "베란다",
    "study": "서재",
    "kids room": "아이방", "kid room": "아이방",
    "hallway": "복도", "corridor": "복도",
    "powder room": "파우더룸",
}

_CLOSING_KEYWORDS = ("마치며", "마무리", "마지막으로", "이상으로", "정리하며", "마치겠습니다", "글을 마칩니다", "포스팅을 마칩니다")
_SKIP_HEADING_KEYWORDS = ("미리보기", "도면", "평면도", "공사정보", "리모델링 솔루션")

_FILLER_EXACT = {"", "​", "before", "after", "before & after", "b e f o r e", "a f t e r"}

# A very common heading style in this source data is "룸명 + separator + long
# descriptive subtitle" (e.g. "욕실 – 모던한 색감과 공간 분리", "안방 - 파우더룸 +
# 붙박이장 + 행거 After"). Neither the strict exact-match check nor the
# non-strict <=12-char check below recognizes these as headings, so the
# paragraph silently falls into whatever the PREVIOUS room's bucket was --
# merging two rooms' text under one label. Matched independent of strict
# mode since the signal (a known room word immediately followed by a
# dash/colon, at the very start of the line) is reliable on its own --
# ordinary Korean sentences don't open with a bare room noun + dash.
_ROOM_PREFIX_HEADING = re.compile(
    r"^(" + "|".join(re.escape(w) for w in sorted(_STRICT_KO_HEADINGS, key=len, reverse=True)) + r")\s*[-–—:：]\s*\S"
)

# Source-platform brand mentions to strip before storing description text --
# the content is being republished on zipterior, not the original platform.
# This never affects the confidence score; it is a text-hygiene note only.
_PLATFORM_MENTION = re.compile(r"오늘의\s*집|오집|집들이")

# document_order units; beyond this a photo/paragraph pairing is "far" from
# where the rest of that room's evidence sits in the source document.
_FAR_DISTANCE_THRESHOLD = 25


def strip_platform_mentions(text_value: str | None) -> tuple[str, bool]:
    """Remove '오늘의집'/'오늘의 집'/'오집'/'집들이' mentions. Returns (cleaned, found)."""
    raw = text_value or ""
    found = bool(_PLATFORM_MENTION.search(raw))
    cleaned = _PLATFORM_MENTION.sub("", raw)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned, found


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _norm_key(value: Any) -> str:
    return _clean(value).replace(" ", "")


def _is_filler(text_value: str) -> bool:
    t = text_value.strip()
    if t.lower() in _FILLER_EXACT:
        return True
    if re.match(r"^(before|after)\s*[:\-]?\s*.{0,15}(공사전|공사후)?\s*$", t, re.I) and len(t) <= 20:
        return True
    return False


def _normalize_heading(raw_text: str) -> str:
    t = _clean(raw_text)
    t = re.sub(r"[\U0001F300-\U0001FAFF☀-➿←-⇿⬀-⯿]", "", t).strip()
    t = re.sub(r"^\s*\d{1,2}[\.\)]\s*", "", t)
    m = re.match(r"^\[\s*(.*?)\s*\]$", t)
    if m:
        t = m.group(1)
    m = re.match(r"^(Before|After)\s*[:\-]\s*(.*)$", t, re.I)
    if m:
        t = m.group(2)
    t = re.sub(r"\s*공사(전|후)\s*$", "", t)
    m = re.match(r"^(.*?)\s*\([A-Za-z\s\-]+\)\s*$", t)
    if m and m.group(1).strip():
        t = m.group(1).strip()
    m = re.match(r"^([가-힣][가-힣/\s]*?)\s+([A-Za-z][A-Za-z\-\s]*)$", t)
    if m and m.group(2).strip().lower() in _EN_HEADING_TO_KO:
        t = m.group(1).strip()
    t = re.sub(r"\s*[-]?\s*\d+\s*$", "", t).strip()
    m = re.match(r"^\|\s*(.*?)\s*\|$", t)
    if m:
        t = m.group(1)
    m = re.match(r'^["“]\s*(.*?)\s*["”]$', t)
    if m:
        t = m.group(1)
    if "|" in t:
        parts = [p.strip() for p in t.split("|")]
        hangul_parts = [p for p in parts if re.search(r"[가-힣]", p)]
        t = hangul_parts[0] if hangul_parts else parts[0]
    if re.match(r"^([A-Za-z]\s){2,}[A-Za-z]$", t):
        t = t.replace(" ", "")
    t2 = re.sub(r"\s*(Before|After|before\s*&\s*after)\s*$", "", t, flags=re.I).strip()
    if t2:
        t = t2
    return re.sub(r"\s+", " ", t).strip()


def _classify_heading(normalized: str, *, strict: bool) -> tuple[str | None, str | None]:
    if not normalized:
        return None, None
    for kw in _CLOSING_KEYWORDS:
        if kw in normalized:
            return "closing", normalized
    for kw in _SKIP_HEADING_KEYWORDS:
        if kw in normalized:
            return "skip", None
    m = _ROOM_PREFIX_HEADING.match(normalized)
    if m:
        return "room", m.group(1)
    lowered = normalized.lower()
    if strict:
        nospace = normalized.replace(" ", "")
        if normalized in _STRICT_KO_HEADINGS or nospace in _STRICT_KO_NOSPACE:
            return "room", _STRICT_KO_NOSPACE.get(nospace, normalized)
        if lowered in _EN_HEADING_TO_KO:
            return "room", _EN_HEADING_TO_KO[lowered]
        return None, None
    if re.search(r"[가-힣]", normalized):
        return ("room", normalized) if len(normalized) <= 12 else (None, None)
    if lowered in _EN_HEADING_TO_KO:
        return "room", _EN_HEADING_TO_KO[lowered]
    return None, None


@dataclass
class ParagraphRow:
    document_order: int
    node_type: str  # 'p' | 'quote' | 'callout' | 'h2' | 'h3' | 'h4'
    space_code: str | None
    sub_space_name: str | None
    text: str


@dataclass
class ImageRow:
    document_order: int
    space_code: str | None
    sub_space_name: str | None
    space_name: str | None
    phase: str | None


@dataclass
class SpaceRow:
    """One row from the source's own already-aggregated space list (JSON
    `spaces[]` / Excel '03_공간' sheet). This is the source of truth for
    "what rooms does this portfolio's text actually claim to cover" --
    independent of whether any photo exists for that room."""
    space_code: str | None
    space_name: str | None
    sub_space_name: str | None


@dataclass
class SectionScore:
    label: str
    score: int | None  # None only for "heading confirmed this room, it just has no photos" -- not a defect
    reason: str
    text: str  # the paragraphs assigned to this room, reconstructed in original order -- ready to use as its description
    n_images: int
    n_text_paragraphs: int
    far_paragraph_orders: list[int] = field(default_factory=list)


@dataclass
class PortfolioConfidence:
    portfolio_score: int
    sections: list[SectionScore]
    intro_text: str
    closing_text: str
    platform_mentions_removed: int
    used_structural_headings: bool


# Which space_code(s) a given sub_space_name value is a legitimate
# *refinement* of. The source's own per-paragraph/per-image sub_space_name
# field is noisier than space_code -- e.g. a summary sentence that merely
# *mentions* "안방" among several rooms can leak that word onto sub_space_name
# for rows that are actually about a different room, while space_code stays
# correct. When the two disagree, trust space_code instead of blindly
# trusting the narrower field. Legitimate multi-instance cases (e.g. two
# bathrooms distinguished as 공용욕실/안방욕실, both space_code=BATHROOM) are
# unaffected -- they're consistent with this map by construction.
_SUB_SPACE_COMPATIBLE_CODES: dict[str, frozenset[str]] = {
    "거실": frozenset({"LIVING_ROOM"}),
    "주방": frozenset({"KITCHEN"}),
    "현관": frozenset({"ENTRANCE"}),
    "침실": frozenset({"BEDROOM", "MASTER_BEDROOM", "KIDS_ROOM"}),
    "작은침실": frozenset({"BEDROOM"}),
    "안방": frozenset({"MASTER_BEDROOM"}),
    "부부침실": frozenset({"MASTER_BEDROOM"}),
    "아이방": frozenset({"KIDS_ROOM", "BEDROOM"}),
    "욕실": frozenset({"BATHROOM"}),
    "공용욕실": frozenset({"BATHROOM"}),
    "안방욕실": frozenset({"BATHROOM"}),
    "부부욕실": frozenset({"BATHROOM"}),
    "거실욕실": frozenset({"BATHROOM"}),
    "드레스룸": frozenset({"DRESS_ROOM"}),
    "안방드레스룸": frozenset({"DRESS_ROOM"}),
    "파우더룸": frozenset({"POWDER_ROOM"}),
    "서재": frozenset({"STUDY"}),
    "발코니": frozenset({"BALCONY"}),
    "베란다": frozenset({"BALCONY"}),
    "발코니/베란다": frozenset({"BALCONY"}),
    "복도": frozenset({"HALLWAY"}),
    "세탁실": frozenset({"LAUNDRY_ROOM"}),
    "팬트리": frozenset({"PANTRY"}),
    "기타": frozenset({"ETC"}),
    "입구방": frozenset({"BEDROOM"}),
    "작은방": frozenset({"BEDROOM"}),
    "메인룸": frozenset({"MASTER_BEDROOM"}),
    "각방": frozenset({"BEDROOM"}),
    "기타방": frozenset({"BEDROOM", "ETC"}),
}


def _resolved_label(space_code: str | None, sub_space_name: str | None, space_name: str | None = None) -> str:
    """Pick the room label for a source row, cross-checking sub_space_name
    against space_code instead of blindly trusting the narrower field (see
    _SUB_SPACE_COMPATIBLE_CODES). Falls back to space_code's standard name
    (or the row's own space_name for images) when sub_space_name is absent
    or contradicts space_code."""
    sub = _norm_key(sub_space_name)
    code = (space_code or "").strip().upper()
    if sub:
        compat = _SUB_SPACE_COMPATIBLE_CODES.get(sub)
        if compat is None or not code or code in compat:
            return sub
        # sub contradicts space_code -- fall through and trust space_code.
    return SPACE_CODE_STANDARD.get(code) or _norm_key(space_name)


def _label_for_image(image: ImageRow) -> str:
    return _resolved_label(image.space_code, image.sub_space_name, image.space_name)


def _nearest_distance_score(text_orders: list[int], image_orders: list[int]) -> tuple[int, list[int]]:
    """For each text paragraph, distance to the nearest image with the same
    label. No clustering, no minimum-sample-size special case -- this works
    identically whether there is 1 image or 50."""
    far_orders = []
    for order in text_orders:
        distance = min(abs(order - img_order) for img_order in image_orders)
        if distance > _FAR_DISTANCE_THRESHOLD:
            far_orders.append(order)
    ratio_far = len(far_orders) / len(text_orders)
    score = 100 - int(ratio_far * 70)
    return score, far_orders


@dataclass
class _Segmented:
    text_by_label: dict[str, list[tuple[int, str]]]
    label_source: dict[str, str]
    intro_paragraphs: list[str]
    closing_paragraphs: list[str]
    images_by_label: dict[str, list[int]]
    platform_mentions_removed: int
    used_structural_headings: bool


def _segment(paragraphs: list[ParagraphRow], images: list[ImageRow]) -> _Segmented:
    """Group paragraphs into per-room text (in original order) plus a
    portfolio-level intro/closing, using only structural signals -- shared by
    `score_portfolio` (which checks whether the grouping looks right) and
    `build_photo_captions` (which further splits a room's text between its
    opening description and individual photo captions)."""
    prows = sorted(paragraphs, key=lambda r: r.document_order)

    heading_rows = [r for r in prows if r.node_type in ("h2", "h3", "h4")]
    use_structural = len(heading_rows) > 0
    if not use_structural:
        heading_rows = []
        for r in prows:
            if r.node_type not in ("p", "quote"):
                continue
            normalized = _normalize_heading(r.text)
            kind, _ = _classify_heading(normalized, strict=True)
            if kind in ("room", "closing"):
                heading_rows.append(r)

    markers: list[tuple[int, str, str]] = []
    for r in heading_rows:
        normalized = _normalize_heading(r.text)
        kind, label = _classify_heading(normalized, strict=not use_structural)
        if kind in ("room", "closing") and label:
            markers.append((r.document_order, kind, label))
    markers.sort()
    room_marker_count = sum(1 for _, kind, _ in markers if kind == "room")

    def bucket_for(order: int) -> tuple[str, str] | None:
        current = None
        for marker_order, kind, label in markers:
            if order >= marker_order:
                current = (kind, label)
            else:
                break
        return current

    heading_orders = {r.document_order for r in heading_rows}
    text_by_label: dict[str, list[tuple[int, str]]] = defaultdict(list)
    label_source: dict[str, str] = {}
    intro_paragraphs: list[str] = []
    closing_paragraphs: list[str] = []
    platform_mentions_removed = 0

    for r in prows:
        if r.node_type not in ("p", "quote", "callout"):
            continue
        if r.document_order in heading_orders and r in heading_rows:
            continue
        text_value = r.text.strip()
        if _is_filler(text_value):
            continue
        cleaned, found = strip_platform_mentions(text_value)
        if found:
            platform_mentions_removed += 1
        text_value = cleaned or text_value

        bucket = bucket_for(r.document_order)
        if bucket is None:
            if room_marker_count == 0:
                label = _resolved_label(r.space_code, r.sub_space_name)
                if label:
                    text_by_label[label].append((r.document_order, text_value))
                    label_source[label] = "fallback"
                else:
                    intro_paragraphs.append(text_value)
            else:
                intro_paragraphs.append(text_value)
        elif bucket[0] == "room":
            text_by_label[bucket[1]].append((r.document_order, text_value))
            label_source[bucket[1]] = "heading"
        elif bucket[0] == "closing":
            closing_paragraphs.append(text_value)

    images_by_label: dict[str, list[int]] = defaultdict(list)
    for image in images:
        if (image.phase or "").strip().upper() != "AFTER":
            continue
        images_by_label[_label_for_image(image)].append(image.document_order)

    return _Segmented(
        text_by_label=text_by_label,
        label_source=label_source,
        intro_paragraphs=intro_paragraphs,
        closing_paragraphs=closing_paragraphs,
        images_by_label=images_by_label,
        platform_mentions_removed=platform_mentions_removed,
        used_structural_headings=use_structural,
    )


def score_portfolio(
    paragraphs: list[ParagraphRow],
    images: list[ImageRow],
    known_spaces: list[SpaceRow] | None = None,
) -> PortfolioConfidence:
    """Score a portfolio's text/image placement using structural signals only.

    Every signal here is either (a) an explicit heading already in the source
    document, (b) the `sub_space_name`/`space_code` the source crawler already
    assigned, or (c) `document_order` proximity between text and images that
    share a label. Nothing here reads paragraph text for meaning.

    `known_spaces` is the source's own already-aggregated space list (JSON
    `spaces[]` / Excel '03_공간'). A room label with zero matching photos is
    only ever a *symmetric, normal* case -- exactly like a room with photos
    but no text -- when that label actually exists in `known_spaces`. A label
    with zero photos AND no match in `known_spaces` means the classification
    likely invented a room the source never actually recorded, which is the
    one case worth flagging.
    """
    known_space_keys = {
        _norm_key(s.sub_space_name) or _norm_key(s.space_name)
        for s in (known_spaces or [])
    }
    known_space_keys.discard("")
    seg = _segment(paragraphs, images)
    text_by_label = seg.text_by_label
    label_source = seg.label_source
    images_by_label = seg.images_by_label

    sections: list[SectionScore] = []
    for label, text_entries in text_by_label.items():
        key = _norm_key(label)
        image_orders = images_by_label.get(key, [])
        text_orders = [order for order, _ in text_entries]
        section_text = "\n\n".join(t for _, t in text_entries)

        if not image_orders:
            # A label with zero matching photos is only suspect when nothing
            # confirms it as a room the source actually recorded. Either the
            # source's own space list already names this exact room (the
            # strongest confirmation -- symmetric to "photos with no text",
            # which is already normal), or an explicit heading in the
            # document itself named it. No known-space list was passed at
            # all -> fall back to heading-only confirmation rather than
            # penalize by default.
            known_confirmed = key in known_space_keys
            heading_confirmed = label_source.get(label) == "heading"
            if known_confirmed or heading_confirmed:
                reason = "NO_IMAGES_KNOWN_SPACE_OK" if known_confirmed else "NO_IMAGES_HEADING_CONFIRMED"
                sections.append(SectionScore(label, None, reason, section_text, 0, len(text_orders)))
            else:
                # Doesn't match the source's own space list and no heading
                # confirms it either -- likely invented by the space_code
                # fallback rather than reflecting a room the source recorded.
                sections.append(SectionScore(label, 35, "LABEL_NOT_IN_SOURCE_SPACE_LIST", section_text, 0, len(text_orders)))
            continue

        score, far_orders = _nearest_distance_score(text_orders, image_orders)
        reason = "OK" if score == 100 else "TEXT_FAR_FROM_IMAGES"
        sections.append(SectionScore(label, score, reason, section_text, len(image_orders), len(text_orders), far_orders))

    # Portfolio-level score is a paragraph-count-weighted average across
    # sections, NOT the minimum. A single small section with an issue (e.g.
    # 2 orphan sentences with no matching photos) should not veto an entire
    # portfolio that is otherwise clean -- that made almost every multi-room
    # portfolio fail on some minor blemish, defeating the point of scoring at
    # all. A large weak section (many paragraphs affected) still pulls the
    # score down proportionally to how much content it actually represents.
    # Section-level scores/reasons are still returned in full for per-section
    # review -- nothing here hides which section has the issue.
    scored_sections = [s for s in sections if s.score is not None]
    if scored_sections:
        total_weight = sum(s.n_text_paragraphs for s in scored_sections) or len(scored_sections)
        weighted_sum = sum(
            s.score * (s.n_text_paragraphs or 1) for s in scored_sections
        )
        portfolio_score = round(weighted_sum / total_weight)
    else:
        # No section was ever populated with unscored risk -- either there was
        # nothing to place at all, or every section was heading-confirmed with
        # no photos (both are fine, nothing that could be misplaced).
        portfolio_score = 100

    return PortfolioConfidence(
        portfolio_score=portfolio_score,
        sections=sections,
        intro_text="\n\n".join(seg.intro_paragraphs),
        closing_text="\n\n".join(seg.closing_paragraphs),
        platform_mentions_removed=seg.platform_mentions_removed,
        used_structural_headings=seg.used_structural_headings,
    )


def build_photo_captions(
    paragraphs: list[ParagraphRow],
    images: list[ImageRow],
) -> tuple[dict[str, str], dict[int, str]]:
    """Split each room's paragraphs into the opening text before that room's
    first photo (-> room-level description, shown once above the gallery)
    and a caption per individual photo for paragraphs that sit right next to
    a specific photo (-> that photo's own description).

    This is what actually lets zipterior show "이 문장 -> 이 사진" the way the
    source article does, instead of one text block above a whole photo grid.

    Nothing is dropped: a paragraph too far from every photo in its room
    stays in the room-level description rather than being discarded, so no
    original content silently disappears.

    Returns (room_description_by_label, caption_by_image_document_order).
    Both are keyed by the same conventions `score_portfolio` uses (label =
    room's sub_space_name/space_name; image key = its own document_order),
    so a caller can zip this against `grouped_portfolio_spaces()` output and
    the source `images[]` list the same way `apply_confidence_text` does.
    """
    seg = _segment(paragraphs, images)
    room_description: dict[str, str] = {}
    caption_by_image: dict[int, list[str]] = defaultdict(list)

    for label, text_entries in seg.text_by_label.items():
        image_orders = sorted(seg.images_by_label.get(_norm_key(label), []))
        entries = sorted(text_entries)  # [(document_order, text), ...]

        if not image_orders:
            room_description[label] = "\n\n".join(t for _, t in entries)
            continue

        first_image_order = image_orders[0]
        opening_texts = []
        for order, text in entries:
            if order < first_image_order:
                opening_texts.append(text)
                continue
            nearest = min(image_orders, key=lambda io: abs(io - order))
            if abs(nearest - order) <= _FAR_DISTANCE_THRESHOLD:
                caption_by_image[nearest].append(text)
            else:
                # too far from every photo in this room -- keep it visible in
                # the room description rather than silently dropping it.
                opening_texts.append(text)
        room_description[label] = "\n\n".join(opening_texts)

    return room_description, {order: "\n\n".join(texts) for order, texts in caption_by_image.items()}
