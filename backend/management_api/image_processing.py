"""Display derivatives only: callers keep the full-resolution source separately."""
from io import BytesIO
from PIL import Image, ImageCms, ImageOps

WIDTHS = (320, 640, 1280)


def normalized_image(image):
    image = ImageOps.exif_transpose(image)
    mode = "RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB"
    if image.info.get("icc_profile"):
        try:
            image = ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(BytesIO(image.info["icc_profile"])), ImageCms.createProfile("sRGB"), outputMode=mode)
        except (ImageCms.PyCMSError, OSError, ValueError):
            pass  # Malformed optional profiles must not make valid pixels unusable.
    return image.convert(mode)


def display_variants(image):
    """Yield real widths, heights and WebP bytes. Never upscale or crop artwork."""
    widths = {max(1, min(value, image.width, round(2560 * image.width / image.height))) for value in WIDTHS}
    for width in sorted(widths):
        height = min(2560, max(1, round(image.height * width / image.width)))
        preview = image.resize((width, height), Image.Resampling.LANCZOS)
        output = BytesIO()
        preview.save(output, format="WEBP", quality=86, method=6)
        yield width, height, output.getvalue()
