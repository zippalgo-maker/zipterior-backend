"""아주 제한된 화이트리스트 기반 리치텍스트(굵게/밑줄/기울임/색상) sanitizer.

영업관리 통화기록 "상세내용"이 contenteditable에서 만든 HTML을 그대로
저장/렌더링해야 하는데, 브라우저가 만든 HTML을 검증 없이 저장하면 XSS로
이어진다(예: 사용자가 개발자도구로 <script> 태그를 끼워넣어 저장). 그래서
허용 태그/속성을 극도로 좁게 화이트리스트로 제한하고, 그 외는 전부
제거(닫는 태그까지 무시)한 뒤 텍스트는 다시 escape해서 재조립한다.

절대 신뢰하면 안 됨: 이 함수를 거치지 않은 content를 DB에 쓰거나
화면에 그대로 뿌리지 않는다.
"""

import re
from html import escape
from html.parser import HTMLParser

_ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "br", "span"}
_VOID_TAGS = {"br"}
_COLOR_STYLE_RE = re.compile(r"^\s*color\s*:\s*#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\s*;?\s*$")


class _RichTextSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _ALLOWED_TAGS:
            return
        if tag in _VOID_TAGS:
            self._out.append(f"<{tag}>")
            return
        if tag == "span":
            style_value = ""
            for name, value in attrs:
                if name == "style" and value and _COLOR_STYLE_RE.match(value):
                    style_value = value.strip().rstrip(";")
                    break
            if style_value:
                self._out.append(f'<span style="{escape(style_value, quote=True)}">')
            else:
                self._out.append("<span>")
        else:
            self._out.append(f"<{tag}>")
        self._open_tags.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID_TAGS:
            self._out.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if tag not in _ALLOWED_TAGS or tag in _VOID_TAGS:
            return
        if tag in self._open_tags:
            self._out.append(f"</{tag}>")
            for index in range(len(self._open_tags) - 1, -1, -1):
                if self._open_tags[index] == tag:
                    del self._open_tags[index]
                    break

    def handle_data(self, data: str) -> None:
        self._out.append(escape(data))

    def result(self) -> str:
        for tag in reversed(self._open_tags):
            self._out.append(f"</{tag}>")
        self._open_tags = []
        return "".join(self._out)


def sanitize_rich_text(raw_html: str | None) -> str:
    if not raw_html:
        return ""
    parser = _RichTextSanitizer()
    parser.feed(raw_html)
    parser.close()
    return parser.result()
