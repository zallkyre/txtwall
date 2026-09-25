"""Upload validation.

An uploaded image is never written to disk as-is. It is checked against
known magic bytes, fully decoded, stripped of metadata, resized and
re-encoded as PNG — which removes anything smuggled inside the file.
"""

import io

from PIL import Image

from .config import CONFIG

_MAGIC = {
    b"\x89PNG\r\n\x1a\n": "PNG",
    b"\xff\xd8\xff": "JPEG",
    b"GIF87a": "GIF",
    b"GIF89a": "GIF",
    b"RIFF": "WEBP",  # RIFF....WEBP
}


def _detect_format(data: bytes):
    for magic, fmt in _MAGIC.items():
        if data.startswith(magic):
            if fmt == "WEBP" and data[8:12] != b"WEBP":
                continue
            return fmt
    return None


def process_image(data: bytes) -> bytes:
    """Return safe PNG bytes. Raises ValueError with a usable message."""
    if len(data) > CONFIG["max_image_bytes"]:
        raise ValueError("image too large")
    if _detect_format(data) is None:
        raise ValueError("unsupported image type")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise ValueError("corrupt image")

    img = img.convert("RGB")
    dim = CONFIG["image_max_dim"]
    img.thumbnail((dim, dim), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()
