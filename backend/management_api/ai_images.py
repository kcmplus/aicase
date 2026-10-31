"""Private generated images with fixed expiry dates and bounded cleanup."""
import logging
from io import BytesIO

from django.core.cache import cache
from django.db.models.functions import Length
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.response import Response
from PIL import Image, ImageOps

from .models import AIRender

TERMINAL_STATUSES = ('ready', 'failed', 'cancelled')
IMAGE_EXTENSIONS = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}


def image_expired(job, now=None):
    return bool(job.image_deleted_at or (job.image_expires_at and job.image_expires_at <= (now or timezone.now())))


def image_metadata(row, *, original=False):
    size = row.pop('original_size_bytes' if original else 'image_size_bytes', None) or 0
    expires = row['image_expires_at']
    deleted = row['image_deleted_at']
    if not original and row['status'] != 'ready':
        state = 'pending' if row['status'] in ('queued', 'generating') else 'none'
    elif deleted:
        state = 'deleted'
    elif expires and expires <= timezone.now():
        state = 'expired'
    else:
        state = 'available' if size else 'missing'
    mime = row.get('input_mime', '') if original else 'image/png'
    if state == 'available' and mime not in IMAGE_EXTENSIONS:
        state = 'missing'
    path = 'original' if original else 'image'
    url = f"/api/v1/admin/ai-renders/{row['id']}/{path}/" if state == 'available' else None
    filename = f"ai-{row['id']}{'-original' if original else ''}.{IMAGE_EXTENSIONS.get(mime, 'png')}"
    return {'state': state, 'expires_at': expires, 'deleted_at': deleted,
            'size_bytes': size if state == 'available' else None,
            'mime_type': mime, 'filename': filename,
            'preview_url': url, 'download_url': url + '?download=1' if url else None,
            'thumbnail_url': url + '?thumbnail=1' if url else None}


def with_image_size(qs):
    # Ask the database for the byte count; never fetch image blobs in a log list.
    return qs.annotate(image_size_bytes=Length('result_image'), original_size_bytes=Length('input_image'))


def image_response(job, download=False, *, original=False, thumbnail=False):
    # Check time on every request, even if the scheduled cleanup has not run yet.
    if image_expired(job):
        return Response({'detail': 'This generated image has expired and is no longer available.',
                         'code': 'image_expired'}, status=410)
    content = job.input_image if original else job.result_image
    mime = job.input_mime if original else 'image/png'
    if not content or mime not in IMAGE_EXTENSIONS:
        return Response({'detail': 'The generated image is unavailable.', 'code': 'image_missing'}, status=404)
    content = bytes(content)
    ext = IMAGE_EXTENSIONS[mime]
    if thumbnail:
        try:
            with Image.open(BytesIO(content)) as source:
                if source.width * source.height > 16_000_000:
                    raise ValueError('Image too large')
                image = ImageOps.exif_transpose(source)
                image.thumbnail((160, 160))
                output = BytesIO()
                image.convert('RGB').save(output, format='JPEG', quality=75)
                content, mime, ext = output.getvalue(), 'image/jpeg', 'jpg'
        except (OSError, ValueError, Image.DecompressionBombError):
            return Response({'detail': 'The image preview is unavailable.', 'code': 'image_invalid'}, status=404)
    response = HttpResponse(content, content_type=mime)
    disposition = 'attachment' if download else 'inline'
    suffix = '-original' if original else ''
    response['Content-Disposition'] = f'{disposition}; filename="ai-{job.id}{suffix}{"-preview" if thumbnail else ""}.{ext}"'
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def cleanup_expired_images(*, now=None, batch_size=100, max_batches=100):
    now = now or timezone.now()
    expired = AIRender.objects.filter(status__in=TERMINAL_STATUSES, image_expires_at__lte=now, image_deleted_at__isnull=True)
    count = 0
    for _ in range(max_batches):
        ids = list(expired.order_by('image_expires_at', 'id').values_list('pk', flat=True)[:batch_size])
        if not ids:
            break
        # Recheck expiry/status in the UPDATE; concurrent runs are idempotent.
        count += expired.filter(pk__in=ids).update(input_image=b'', result_image=None, image_deleted_at=now)
    return count


def maybe_cleanup_images():
    # A small traffic-driven fallback for local installs without a scheduler.
    key = 'ai-image-cleanup-v1'
    if cache.add(key, True, timeout=600):
        try:
            cleanup_expired_images(max_batches=1)
        except Exception:
            cache.delete(key)
            logging.getLogger(__name__).exception('Generated image cleanup failed')
