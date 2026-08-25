#!/usr/bin/env python3
"""v2.5.1: content_blocks(원문 재현) 본문에 나오는 사진 중, 일괄등록 당시
"포트폴리오당 이미지 상한"(예: 100장)에 걸려 우리 서버에 저장되지 못한
사진을 추가로 내려받고, content_blocks.image_url을 전부 우리 서버 경로로
재작성한다.

원칙: 본문에 나오는 사진은 전부 우리 서버에 있어야 한다 -- 외부(오늘의집)
CDN을 그대로 가리키면 원본이 지워지거나 바뀌었을 때 우리 사이트도 같이
깨진다. worker.py의 select_portfolio_images(max_images=None) 지원 덕분에
이미 다운로드된 이미지는 건드리지 않고(source_import_links로 dedup),
빠진 것만 추가로 받는다 -- 재다운로드 없음, 무손실.

대상은 이 스크립트를 만든 시점(2026-08-21) 기준 bulk_import job 하나
(--job-id)의 성공한 portfolio 레코드들이다. 원본 JSON은 그 job의
source_path(/srv/zipterior/imports/{job_id}/source.json)에서 다시 읽는다
-- 이미 업로드된 파일이라 재업로드 불필요.

사용법(반드시 --apply를 붙여야 실제로 반영됨, 기본은 무엇을 할지만 출력):
    cd /srv/zipterior/backend
    ../venv/bin/python -m scripts.ops.backfill_content_blocks_images --job-id 28
    ../venv/bin/python -m scripts.ops.backfill_content_blocks_images --job-id 28 --apply

v2.5.40(2026-08-23): --portfolio-id 옵션 추가. 큰 job 안에서 특정
포폴 1~2건만(예: MAX_IMAGES_PER_PORTFOLIO 하드캡에 걸렸던 건만)
백필하고 싶을 때 job 전체를 다시 돌 필요 없이 좁혀서 실행:
    ../venv/bin/python -m scripts.ops.backfill_content_blocks_images --job-id 33 --portfolio-id 1241
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.bulk_import import repository
from app.modules.bulk_import.mapping import (
    build_image_captions,
    content_blocks_from_item,
    grouped_portfolio_spaces,
    representative_image_index,
    select_portfolio_images,
)
from app.modules.bulk_import.worker import (
    _download_selected_images,
    _include_content_block_only_images,
    _localize_and_save_content_blocks,
)


def _load_job(job_id: int) -> tuple[dict, int]:
    with SessionLocal() as session:
        row = (
            session.execute(
                text(
                    "SELECT source_path, requested_by FROM bulk_import_jobs WHERE id=:id"
                ),
                {"id": job_id},
            )
            .mappings()
            .one()
        )
    data = json.loads(Path(row["source_path"]).read_text(encoding="utf-8"))
    return data, int(row["requested_by"])


def _succeeded_portfolios(job_id: int) -> list[tuple[int, str]]:
    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT target_id, record_key FROM bulk_import_records
                WHERE job_id=:job_id AND record_type='portfolio' AND status='succeeded'
                  AND target_id IS NOT NULL
                ORDER BY id
                """
            ),
            {"job_id": job_id},
        ).all()
    return [(int(r.target_id), r.record_key) for r in rows]


def _backfill_one(*, job: dict, item: dict, portfolio_id: int, source_key: str) -> dict:
    with SessionLocal() as session:
        company_id = session.execute(
            text("SELECT company_id FROM portfolios WHERE id=:id"), {"id": portfolio_id}
        ).scalar_one()
        existing_spaces = repository.import_spaces(session, portfolio_id=portfolio_id)

    space_groups = grouped_portfolio_spaces(item)
    if len(existing_spaces) != len(space_groups):
        return {"portfolio_id": portfolio_id, "skipped": "space_count_mismatch"}
    space_ids = {
        expected["key"]: int(existing["id"])
        for existing, expected in zip(existing_spaces, space_groups, strict=True)
    }
    room_codes = {space["key"]: space["space_code"] for space in space_groups}

    captions = build_image_captions(item)
    _room_openings, image_captions_by_order = captions if captions else (None, {})

    content_blocks, content_blocks_stats = content_blocks_from_item(item)
    if not content_blocks:
        return {"portfolio_id": portfolio_id, "skipped": "no_content_blocks"}

    # v2.5.1의 핵심: max_images=None -- 상한 없이 원본 사진을 전부 대상으로.
    # 이미 있는 건 _download_selected_images가 알아서 건너뛴다.
    selected_images = select_portfolio_images(item, max_images=None)
    representative_index = representative_image_index(space_groups, selected_images)
    # BEFORE phase 등 AFTER 필터에 안 걸리지만 content_blocks 본문에는
    # 나오는 사진도 추가로 받는다(worker.py 설명 참고).
    selected_images = _include_content_block_only_images(
        item=item, content_blocks=content_blocks, selected_images=selected_images
    )

    image_success, image_failed = _download_selected_images(
        job=job,
        job_id=job["id"],
        source_key=source_key,
        company_id=company_id,
        portfolio_id=portfolio_id,
        space_ids=space_ids,
        room_codes=room_codes,
        image_captions_by_order=image_captions_by_order,
        selected_images=selected_images,
        representative_index=representative_index,
        # 백필 대상은 이미 검수·승인이 끝난 포트폴리오가 대부분이라, 관리자
        # "원본대조·수정" 화면과 같은 우회 플래그가 없으면 전부
        # PortfolioStateConflictError로 막힌다. 기존 사진을 바꾸는 게
        # 아니라 원문에는 있는데 우리 서버엔 없던 사진을 채우기만 하는
        # 백필이라 이 우회는 이 스크립트 전용으로 켠다.
        bypass_editable_status=True,
    )
    content_blocks_stats = _localize_and_save_content_blocks(
        job_id=job["id"],
        portfolio_id=portfolio_id,
        source_key=source_key,
        content_blocks=content_blocks,
        content_blocks_stats=content_blocks_stats,
    )
    return {
        "portfolio_id": portfolio_id,
        "new_images_downloaded": image_success,
        "new_images_failed": image_failed,
        "content_blocks_localized": content_blocks_stats.get("images_localized_count", 0),
        "content_blocks_still_external": content_blocks_stats.get(
            "images_still_external_count", 0
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", type=int, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="실제로 다운로드/DB 반영. 없으면 대상 목록만 세어서 보여준다(dry-run).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="앞에서부터 N건만 처리(소규모 검증용).",
    )
    parser.add_argument(
        "--portfolio-id",
        type=int,
        default=None,
        help="이 포트폴리오 id 하나만 대상으로 좁힌다(job 전체를 다시 돌리지 않음).",
    )
    args = parser.parse_args()

    data, requested_by = _load_job(args.job_id)
    items_by_key = {str(p["portfolio_id"]): p for p in data.get("portfolios", [])}
    targets = _succeeded_portfolios(args.job_id)
    if args.portfolio_id is not None:
        targets = [(pid, key) for pid, key in targets if pid == args.portfolio_id]
        if not targets:
            print(f"job #{args.job_id}에서 포트폴리오 #{args.portfolio_id}를 찾지 못함(성공 레코드가 아니거나 다른 job 소속).")
            return 1
    print(f"job #{args.job_id}: 성공 레코드 {len(targets)}건, 원본 JSON 포트폴리오 {len(items_by_key)}건")

    if not args.apply:
        matched = sum(1 for _pid, key in targets if key in items_by_key)
        print(f"[dry-run] 원본과 매칭되는 대상 {matched}건. 실제 반영하려면 --apply를 붙이세요.")
        return 0

    job = {"id": args.job_id, "requested_by": requested_by}
    results = []
    for portfolio_id, source_key in (targets[: args.limit] if args.limit else targets):
        item = items_by_key.get(source_key)
        if item is None:
            print(f"  #{portfolio_id} ({source_key}): 원본 JSON에서 못 찾음 -- 스킵")
            continue
        result = _backfill_one(job=job, item=item, portfolio_id=portfolio_id, source_key=source_key)
        results.append(result)
        print(f"  #{portfolio_id}: {result}")

    total_new_images = sum(r.get("new_images_downloaded", 0) for r in results)
    total_localized = sum(r.get("content_blocks_localized", 0) for r in results)
    total_still_external = sum(r.get("content_blocks_still_external", 0) for r in results)
    print(
        f"\n완료: {len(results)}건 처리 / 신규 다운로드 {total_new_images}장 / "
        f"content_blocks 로컬화 {total_localized}장 / 여전히 외부 {total_still_external}장"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
