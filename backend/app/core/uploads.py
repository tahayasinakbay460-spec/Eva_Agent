"""Ham gövdeyle (multipart değil) dosya yükleyen uçlar için ortak yardımcı."""

from fastapi import HTTPException, Request, status


async def read_body_limited(request: Request, limit: int) -> bytes:
    """İstek gövdesini okur; sınır aşılırsa hemen keser (dosyanın tamamını belleğe almadan)."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file_too_large")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file_too_large")
    return bytes(data)
