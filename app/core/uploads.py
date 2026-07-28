"""Shared helper for writing an UploadFile to disk with a size cap.

`UploadFile.read()` without a limit loads the whole request body into
memory before any validation runs — a single large POST is an easy OOM on
a modest VPS. This streams in chunks and aborts as soon as the cap is
exceeded, without ever buffering the full file.
"""

from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings

CHUNK_SIZE = 1024 * 1024  # 1 MiB


async def read_upload_capped(file: UploadFile) -> bytes:
    """Read `file` fully into memory, raising 413 if it exceeds the cap.

    For inputs (like xlsx) that a downstream parser needs as a whole
    in-memory buffer anyway, so streaming to disk first buys nothing —
    but the cap still applies, checked chunk by chunk rather than after
    a single unbounded `.read()`.
    """
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    try:
        while chunk := await file.read(CHUNK_SIZE):
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    f"File exceeds the {get_settings().max_upload_mb} MB upload limit",
                )
            chunks.append(chunk)
    finally:
        await file.close()
    return b"".join(chunks)


async def save_upload_capped(file: UploadFile, destination: Path) -> int:
    """Stream `file` to `destination`, raising 413 if it exceeds the cap.

    Returns the number of bytes written. Partial output is removed on
    failure so a rejected upload never leaves a truncated file behind.
    """
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    written = 0
    try:
        with destination.open("wb") as out:
            while chunk := await file.read(CHUNK_SIZE):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        f"File exceeds the {get_settings().max_upload_mb} MB upload limit",
                    )
                out.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return written
