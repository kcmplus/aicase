"""Prebuilt public-library image previews; private order photos never enter here."""
import hashlib
import json
import re
from pathlib import PurePosixPath
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from .image_processing import display_variants


def manifest_name(name):
    return f"previews/{PurePosixPath(name).stem}.json"


def save_display_variants(name, image):
    variants = []
    for width, height, data in display_variants(image):
        digest = hashlib.sha256(data).hexdigest()[:20]
        target = f"previews/{digest}-{width}.webp"
        if not default_storage.exists(target):
            target = default_storage.save(target, ContentFile(data))
        variants.append({"src": default_storage.url(target), "width": width, "height": height})
    result = {"width": image.width, "height": image.height, "variants": variants}
    manifest = manifest_name(name)
    # Source names are unique; repeat maintenance runs preserve existing manifests.
    if not default_storage.exists(manifest):
        default_storage.save(manifest, ContentFile(json.dumps(result).encode()))
    return result


def image_variants(paths):
    result = {}
    for path in set(paths):
        # Only the public upload library, never arbitrary storage paths or URLs.
        if not isinstance(path, str) or not re.fullmatch(r"/media/uploads/[a-zA-Z0-9_-]+\.(?:png|jpe?g|webp)", path):
            continue
        try:
            with default_storage.open(manifest_name(path.removeprefix("/media/"))) as stream:
                result[path] = json.load(stream)
        except (FileNotFoundError, ValueError):
            pass  # Older uploads remain usable until previews are backfilled.
    return result
