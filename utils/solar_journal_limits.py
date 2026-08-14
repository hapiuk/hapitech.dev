"""
Solar Journal upload limits — agreed numbers:

- Resize: longest edge 2560px
- JPEG quality: 90
- Hard reject raw upload over 15MB (before processing)
- Per-user cap: 20 entries
- Global soft ceiling: 18GB (out of a 20GB budget), uploads blocked past this
"""

from io import BytesIO

from PIL import Image, ImageOps

MAX_RAW_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_LONGEST_EDGE = 2560
JPEG_QUALITY = 90
PER_BODY_ENTRY_CAP = 2
GLOBAL_SOFT_CEILING_BYTES = 18 * 1024 * 1024 * 1024

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


class UploadError(Exception):
    """Base for all rejections below — callers turn this into a 4xx JSON response."""


class UploadTooLargeError(UploadError):
    pass


class InvalidImageError(UploadError):
    pass


class EntryCapReachedError(UploadError):
    pass


class GlobalCeilingReachedError(UploadError):
    pass


def process_image(file_storage):
    """
    Reads an uploaded file, hard-rejects it if the raw upload is over the
    size limit, then resizes (if needed) and re-encodes as JPEG at the
    agreed quality. Returns (jpeg_bytes, byte_size).

    Raises UploadTooLargeError or InvalidImageError — never partially
    processes an oversized or corrupt file.
    """
    raw = file_storage.read()

    if len(raw) > MAX_RAW_UPLOAD_BYTES:
        raise UploadTooLargeError(
            f"That image is too large — please keep uploads under {MAX_RAW_UPLOAD_BYTES // (1024 * 1024)}MB."
        )

    try:
        img = Image.open(BytesIO(raw))
        img.load()
    except Exception as e:
        raise InvalidImageError("That file doesn't look like a valid image.") from e

    # Respect the camera's EXIF rotation tag before anything else, or
    # phone photos come out sideways.
    img = ImageOps.exif_transpose(img)

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    width, height = img.size
    longest_edge = max(width, height)

    if longest_edge > MAX_LONGEST_EDGE:
        scale = MAX_LONGEST_EDGE / longest_edge
        new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        img = img.resize(new_size, Image.LANCZOS)

    out = BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    data = out.getvalue()

    return data, len(data)