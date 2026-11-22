# utils/uploads.py — client photo uploads. Every image is decoded and re-encoded with Pillow:
# that rotates it upright, caps its size, and strips EXIF metadata (phone photos carry GPS location).
import os
import secrets

from flask import current_app, url_for
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SIDE = 2000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "HEIC", "HEIF", "MPO"}
Image.MAX_IMAGE_PIXELS = 60_000_000        # refuse decompression bombs


class UploadError(ValueError):
    pass


def account_dir(account) -> str:
    path = os.path.join(current_app.config["UPLOAD_ROOT"], account.slug)
    os.makedirs(path, exist_ok=True)
    return path


def save_image(file_storage, account, prefix="photo"):
    """Validate + normalise an uploaded image. Returns (relative_path, width, height)."""
    try:
        img = Image.open(file_storage.stream)
        fmt = (img.format or "").upper()
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise UploadError("That file isn't a photo we can read. Try a JPG or PNG.")
    if fmt not in ALLOWED_FORMATS:
        raise UploadError("Please upload a JPG, PNG or WebP photo.")
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    name = f"{prefix}-{secrets.token_hex(8)}.webp"
    dest = os.path.join(account_dir(account), name)
    img.save(dest, "WEBP", quality=82, method=4)        # no exif= → metadata dropped
    return f"{account.slug}/{name}", img.width, img.height


def media_url(media, external=False) -> str:
    return url_for("reviews_public.media_file", path=media.file_path, _external=external)


def delete_file(rel_path: str):
    root = os.path.realpath(current_app.config["UPLOAD_ROOT"])
    full = os.path.realpath(os.path.join(root, rel_path))
    if full.startswith(root + os.sep) and os.path.isfile(full):
        os.remove(full)
