"""Explicit, local-only import of the reviewed reference; never seed on startup."""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from django.db import transaction
from rest_framework import serializers

from .audit import audit
from .models import PhoneColor, PhoneModel
from .phone_colors import ColorSerializer

REFERENCE_PATH = Path(__file__).parent / 'seed' / 'phone-color-reference.json'


def load_reference():
    # No caller-controlled path, remote URL, or submitted color data is accepted.
    raw = REFERENCE_PATH.read_bytes()
    reference = json.loads(raw)
    if reference['version'] != 1 or reference['kind'] != 'phone_body_color_reference':
        raise serializers.ValidationError('颜色参考资料版本不受支持。')
    fields = ColorSerializer().fields
    entries = []
    keys = set()
    for entry in reference['models']:
        key = (entry['brand'], entry['model_name'])
        if key in keys or entry['match_status'] not in ('verified', 'needs_review'):
            raise serializers.ValidationError('颜色参考资料机型重复或核实状态无效。')
        keys.add(key)
        colors = []
        codes = set()
        for index, color in enumerate(entry['colors']):
            payload = {
                'code': color['code'], 'name': f"{color['name_zh']} / {color['name_en']}",
                'rgb': color['rgb'], 'sort_order': index,
                'source': f"phone-color-reference.json v1 ({reference['researched_at']}); "
                          + '; '.join(source['url'] for source in entry['sources']),
                'region_note': '；'.join(entry.get(k, '') for k in ('market', 'connectivity', 'notes')),
            }
            # Validate the entire source before doing any writes. Never truncate
            # special-edition/source notes or silently coerce invalid RGB.
            payload = {key: fields[key].run_validation(value) for key, value in payload.items()}
            if payload['code'] in codes:
                raise serializers.ValidationError('颜色参考资料编码重复。')
            codes.add(payload['code'])
            colors.append(payload)
        entries.append({**entry, 'payloads': colors})
    return reference, hashlib.sha256(raw).hexdigest(), entries


@transaction.atomic
def initialize_reference(request, *, execute=False, expected_digest=None):
    reference, digest, entries = load_reference()
    if execute and expected_digest != digest:
        raise serializers.ValidationError('颜色参考资料已变化，请重新预览后确认。')
    models = PhoneModel.objects.select_related('brand').order_by('pk')
    if execute:
        # Same parent lock used by regular color writes: serialize imports and
        # manual edits without replacing existing rows, defaults or resources.
        models = models.select_for_update(of=('self',))
    matches = defaultdict(list)
    for model in models:
        matches[(model.brand.name, model.name)].append(model)
    summary = dict(total_models=len(entries), verified_models=0, reference_colors=0,
                   matched_models=0, unmatched_models=0, ambiguous_models=0,
                   needs_review_models=0, new_colors=0, existing_colors=0)
    items = []
    for entry in entries:
        item = {key: entry[key] for key in ('brand', 'model_name', 'match_status', 'notes')}
        item.update(phone_model=None, candidate_ids=[], colors=[])
        summary['reference_colors'] += len(entry['payloads'])
        if entry['match_status'] != 'verified':
            item['result'] = 'needs_review'
            summary['needs_review_models'] += 1
        else:
            summary['verified_models'] += 1
            candidates = matches[(entry['brand'], entry['model_name'])]
            item['candidate_ids'] = [model.pk for model in candidates]
            if len(candidates) != 1:
                item['result'] = 'ambiguous' if candidates else 'unmatched'
                summary[item['result'] + '_models'] += 1
            else:
                model = candidates[0]
                item.update(result='matched', phone_model=model.pk)
                summary['matched_models'] += 1
                existing = {color.code: color for color in model.colors.all()}
                for payload in entry['payloads']:
                    color = existing.get(payload['code'])
                    result = 'existing' if color else ('created' if execute else 'would_create')
                    summary['existing_colors' if color else 'new_colors'] += 1
                    if not color and execute:
                        color = PhoneColor.objects.create(phone_model=model, **payload,
                                                          active=False, is_default=False)
                        audit(request, 'initialize', 'management_api.phonecolor', color,
                              f"参考初始化 {digest[:12]}；新增停用草稿，未绑定资源")
                    item['colors'].append({**payload, 'result': result, 'id': color.pk if color else None})
        items.append(item)
    if execute:
        audit(request, 'initialize', 'management_api.phonecolor', summary=
              f"参考 {digest}；新增 {summary['new_colors']}，已有 {summary['existing_colors']}，"
              f"匹配 {summary['matched_models']}，未匹配 {summary['unmatched_models']}，"
              f"歧义 {summary['ambiguous_models']}，待确认 {summary['needs_review_models']}")
    return {'mode': 'executed' if execute else 'preview', 'reference_sha256': digest,
            'reference_version': reference['version'], 'researched_at': reference['researched_at'],
            'summary': summary, 'items': items}
