from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from PIL import Image
from management_api.image_processing import normalized_image
from management_api.images import manifest_name, save_display_variants


class Command(BaseCommand):
    help = "Build missing display previews for public library uploads; preserve originals."

    def handle(self, *args, **options):
        try:
            _, names = default_storage.listdir("uploads")
        except FileNotFoundError:
            names = []
        count = 0
        for filename in names:
            name = f"uploads/{filename}"
            if not name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) or default_storage.exists(manifest_name(name)):
                continue
            with default_storage.open(name) as source, Image.open(source) as image:
                if image.width * image.height > 20_000_000:
                    self.stderr.write(f"Skipped oversized image: {name}")
                    continue
                save_display_variants(name, normalized_image(image))
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Prepared {count} public images. Originals unchanged."))
