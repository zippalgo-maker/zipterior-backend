from pathlib import Path

# 2026-08-26: /srv/zipterior/media/chat(URL /media/chat)는 nginx root(
# /var/www/zipterior)에 media/ 폴더가 없어서 저장은 되지만 열어보면 항상
# 404였다(첨부가 한 번도 실사용된 적 없어 안 걸렸음). uploads/ 밑으로
# 옮겨서 1) nginx 정적서빙 대상에 들어가고 2) 포트폴리오 업로드와 동일하게
# 두 번째 디스크(vdb, /var/www/zipterior/uploads bind mount)에 저장되게 한다.
CHAT_MEDIA_DIR = Path("/var/www/zipterior/uploads/chat")
CHAT_MEDIA_URL = "/uploads/chat"
CHAT_ALLOWED_MIME_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
CHAT_MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024

DEFAULT_MESSAGE_PAGE_SIZE = 50
MAX_MESSAGE_PAGE_SIZE = 200
