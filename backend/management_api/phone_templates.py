"""Trusted template revisions shared with the local storefront renderer."""
import json
from pathlib import Path

ASSET_ROOT = Path(__file__).resolve().parents[2] / 'frontend/storefront'
PHONE_TEMPLATES = json.loads((ASSET_ROOT / 'assets/phone-templates/templates.json').read_text())


def template_for(model, template_id=None):
    return next((t for t in reversed(PHONE_TEMPLATES) if t['model'] == model and
                 (template_id is None or t['id'] == template_id)), None)
