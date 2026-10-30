from django.db import migrations


# Frozen copy: future catalog edits must not change this one-time backfill.
DEFAULT_PROMPTS = {'3d': 'Transform the uploaded photo into a playful sculpted 3D illustration with softly rounded '
       'forms, tactile matte materials, gentle studio lighting and subtle depth. Use only the '
       'uploaded photo as the subject reference. Preserve the number and identities of people or '
       'animals, recognizable facial features, hairstyles, animal markings, expressions, poses, '
       'clothing and important accessories. For scenery, retain the recognizable setting as a '
       'cohesive miniature world. Follow the phone-model composition requirements, repositioning '
       'the whole subject and extending the background naturally without stretching or cutting '
       'through faces and ears. Output one continuous full-bleed flat artwork, with no phone, case '
       'mockup, camera, holes, borders, added text, logos or watermark.',
 'anime': 'Transform the uploaded photo into a refined anime illustration with clean expressive '
          'linework, soft cel shading, luminous colors and a gently painted background. Use only '
          'the uploaded photo as the subject reference. Preserve the number and identities of '
          'people or animals, recognizable facial features, hairstyles, animal markings, '
          'expressions, poses, clothing and important accessories. For scenery, preserve '
          'recognizable landmarks and their spatial relationships. Follow the phone-model '
          'composition requirements, repositioning the whole subject and extending the background '
          'naturally without stretching or cutting through faces and ears. Output one continuous '
          'full-bleed flat artwork, with no phone, case mockup, camera, holes, borders, added '
          'text, logos or watermark.',
 'realism': 'Refine the uploaded photo into cinematic photographic artwork with natural detail, '
            'soft directional light, balanced contrast and subtle editorial color grading. Use '
            'only the uploaded photo as the subject reference. Preserve the number and identities '
            'of people or animals, recognizable facial features, natural skin or fur texture, '
            'expressions, poses, clothing and important accessories. Keep scenery and landmarks '
            'recognizable without adding unrelated subjects. Follow the phone-model composition '
            'requirements, repositioning the whole subject and extending the background naturally '
            'without stretching or cutting through faces and ears. Output one continuous '
            'full-bleed flat artwork, with no phone, case mockup, camera, holes, borders, added '
            'text, logos or watermark.'}


def fill_missing_prompts(apps, schema_editor):
    styles = apps.get_model("management_api", "AIStyle").objects.using(schema_editor.connection.alias)
    for style in styles.filter(code__in=DEFAULT_PROMPTS):
        if not style.prompt.strip():
            styles.filter(pk=style.pk, prompt=style.prompt).update(prompt=DEFAULT_PROMPTS[style.code])


class Migration(migrations.Migration):
    dependencies = [("management_api", "0014_merge_payments_relay_credits")]
    operations = [migrations.RunPython(fill_missing_prompts, migrations.RunPython.noop)]
