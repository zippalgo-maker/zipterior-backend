# 복구 참고 노트 (2026-08-22)

`repository.py`와 `worker.py`를 v5.3 타입/주소 우선순위 로직으로
고치면서, 평소 관례(`cp file file.bak_YYYYMMDD_HHMMSS_설명`)를 편집
전에 실행하지 못했다(실수). `excel_portfolio.py`와 프론트 2개 파일은
정상적으로 백업했지만 이 두 파일은 없다. git도 안 쓰는 환경이라
diff로 되돌릴 방법이 없어서, 대신 이 세션 대화 중 Read로 확인했던
**원본(수정 전) 코드를 그대로 옮겨 적어** 남긴다. 문제가 생기면 아래
내용으로 해당 함수만 되돌리면 된다.

## repository.py -- 원래 `find_type_for_import` (교체 전)

```python
def find_type_for_import(
    session: Session,
    *,
    complex_id: int,
    area_type: str | None,
    area_pyeong: str | None,
) -> int | None:
    value = session.execute(text("""
        SELECT id
        FROM apartment_types
        WHERE complex_id=:complex_id
          AND (
              (
                  NULLIF(TRIM(:area_type), '') IS NOT NULL
                  AND LOWER(REGEXP_REPLACE(COALESCE(type_name, ''), '[^0-9A-Za-z가-힣]', '', 'g'))
                      = LOWER(REGEXP_REPLACE(:area_type, '[^0-9A-Za-z가-힣]', '', 'g'))
              )
              OR (
                  NULLIF(TRIM(:area_pyeong), '') IS NOT NULL
                  AND LOWER(REGEXP_REPLACE(COALESCE(pyeong_label, ''), '[^0-9A-Za-z가-힣]', '', 'g'))
                      = LOWER(REGEXP_REPLACE(:area_pyeong, '[^0-9A-Za-z가-힣]', '', 'g'))
              )
          )
        ORDER BY sort_order, id
        LIMIT 1
    """), {
        "complex_id": complex_id,
        "area_type": area_type,
        "area_pyeong": area_pyeong,
    }).scalar_one_or_none()
    return int(value) if value is not None else None
```

이걸 되돌리려면: 새로 추가된 `_TYPE_TOKEN_RE`/`_normalize_type_token`/
`_pyeong_label_candidates`/`resolve_type_for_import` 블록을 지우고
위 함수로 교체 + `worker.py`의 호출부도 아래처럼 되돌린다(`import re`는
다른 데서 안 쓰면 같이 지워도 됨, 단 `_normalize_apartment_name`도
`re`를 쓰므로 그것까지 되돌리는 게 아니면 `import re`는 남겨둘 것).

## worker.py -- 원래 호출부 (교체 전, 약 961번째 줄 부근)

```python
            apartment_type_id = None
            if complex_id:
                with SessionLocal() as lookup_session:
                    apartment_type_id = repository.find_type_for_import(
                        lookup_session,
                        complex_id=complex_id,
                        area_type=_text(item.get("area_type"), 100),
                        area_pyeong=_text(item.get("area_pyeong"), 50),
                    )
```

## worker.py -- 원래 review_reason 부분 (교체 전, 약 1150번째 줄 부근)

```python
        if complex_id and not apartment_type_id:
            review_reasons.append("apartment_type_missing")
```

## worker.py -- `_ensure_portfolio_complex`의 원래 `name` 할당 (교체 전, 약 461번째 줄)

```python
    name = _text(
        resolution.get("name") or item.get("apartment_name"),
        200,
    )
```

(`_normalize_apartment_name()` 함수 자체와 `_APARTMENT_NAME_DONG_HO_SUFFIX_RE`는
이번에 새로 추가된 것이라 원래는 존재하지 않았음 -- 되돌릴 땐 통째로 삭제.)

## 이 노트를 지워도 되는 시점

v5.3 파일로 실제 업로드까지 끝나서 새 로직이 문제없이 동작함을 확인한
뒤(`V2.5.0_PLAN.md`의 "v5.3 필드 우선순위 규칙 구현" 절이 실사용
검증까지 [완료]로 갱신된 뒤)에는 이 파일을 지워도 된다. 그 전까지는
남겨둔다.
