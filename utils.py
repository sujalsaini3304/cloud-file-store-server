import io
from PIL import Image

IMAGE_LIMIT = 800 * 1024        # 800 KB
DOC_LIMIT = 6 * 1024 * 1024     # 6 MB


def compress_image(file_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(file_bytes))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", optimize=True, quality=70)
    return buffer.getvalue()


def should_compress_image(size: int) -> bool:
    return size > IMAGE_LIMIT


def should_compress_doc(size: int) -> bool:
    return size > DOC_LIMIT
