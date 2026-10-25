from io import BytesIO, StringIO
from pathlib import Path
import tempfile
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from PIL import Image
from .image_processing import normalized_image, display_variants
from .images import image_variants
from .models import AIStyle, AIExample, AIExampleResult


class ImageTests(TestCase):
    def test_orientation_transparency_and_small_images(self):
        source=Image.new('RGB',(60,30),'red')
        source.getexif()[274]=6
        self.assertEqual(normalized_image(source).size,(30,60))
        transparent=normalized_image(Image.new('RGBA',(64,48),(30,100,160,0)))
        variants=list(display_variants(transparent))
        self.assertEqual(len(variants),1)
        with Image.open(BytesIO(variants[0][2])) as preview:
            self.assertEqual(preview.size,(64,48))
            self.assertEqual(preview.getpixel((0,0))[3],0)
        # Valid narrow uploads must not exceed WebP's dimension limit or fail with 500.
        strip=list(display_variants(Image.new('RGB',(1,20000),'red')))
        self.assertEqual(len(strip),1)
        self.assertEqual(strip[0][:2],(1,2560))

    def test_upload_keeps_full_resolution_and_exposes_prebuilt_previews_in_catalog_and_admin(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            user=User.objects.create_superuser('image-test',password='Temporary-test-only!73')
            client=APIClient();client.force_login(user)
            source=BytesIO();Image.new('RGB',(2600,1300),'teal').save(source,'JPEG')
            result=client.post('/api/v1/admin/uploads/',{'file':SimpleUploadedFile('photo.jpg',source.getvalue(),content_type='image/jpeg')})
            self.assertEqual(result.status_code,201,result.data)
            path=result.data['path'];metadata=result.data['image_variants'][path]
            with Image.open(Path(directory)/path.removeprefix('/media/')) as original:
                self.assertEqual(original.size,(2600,1300))
                self.assertFalse(original.getexif())
            self.assertEqual([v['width'] for v in metadata['variants']],[320,640,1280])
            for v in metadata['variants']:
                with Image.open(Path(directory)/v['src'].removeprefix('/media/')) as preview:
                    self.assertEqual(preview.size,(v['width'],v['height']))
                    self.assertEqual(preview.format,'WEBP')
            style=AIStyle.objects.create(code='image-test',name='Test',image_path=path)
            example=AIExample.objects.create(code='image-test',name='Test',subject='Test',original_path=path)
            AIExampleResult.objects.create(example=example,style=style,image_path=path)
            admin=client.get(f'/api/v1/admin/ai-examples/{example.pk}/').json()
            self.assertEqual(admin['image_variants'][path],metadata)
            client.logout()
            catalog=client.get('/api/v1/catalog/').json()
            self.assertEqual(catalog['image_variants'][path],metadata)
            self.assertEqual(catalog['ai_examples'][0]['original_path'],path)
            files=set(Path(directory).rglob('*'))
            call_command('optimize_library_images',stdout=StringIO())
            self.assertEqual(files,set(Path(directory).rglob('*')))
            self.assertEqual(image_variants(['/media/../../private.png','/media/uploads/missing.png']),{})
