"""Derive provisional print interiors from the supplied case overlays.

Run after placing the original vendor PNGs in assets/phone-templates. The
connected interior excludes opaque cameras/frame and disconnected outer corners.
This is a template-derived mask, NOT a manufacturer-approved bleed definition.
"""
from collections import deque
from pathlib import Path
import json
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / 'frontend/storefront'


def interior_mask(image):
    width, height = image.size
    alpha = image.getchannel('A').tobytes()
    inside = bytearray(width * height)
    start = (height // 2) * width + width // 2
    if alpha[start] >= 250:
        raise ValueError('Template center is not transparent; supply a print mask.')
    queue = deque([start])
    inside[start] = 255
    while queue:
        i = queue.popleft()
        x = i % width
        for j in (i-width if i >= width else -1,
                  i+width if i+width < len(alpha) else -1,
                  i-1 if x else -1, i+1 if x < width-1 else -1):
            if j >= 0 and not inside[j] and alpha[j] < 250:
                inside[j] = 255
                queue.append(j)
    if any(inside[x] or inside[(height-1)*width+x] for x in range(width)) or any(
        inside[y*width] or inside[y*width+width-1] for y in range(height)
    ):
        raise ValueError('Interior leaks to the canvas edge; supply a print mask.')
    return Image.frombytes('L', image.size, bytes(inside))


def preview_overlay(image):
    # Remove only exterior white/translucent pixels connected to the canvas
    # boundary. Keep the supplied camera, frame and internal shading intact.
    width, height = image.size
    pixels = list(image.getdata())
    outside = bytearray(width * height)
    queue = deque()
    def add(i):
        r, g, b, a = pixels[i]
        if not outside[i] and (a < 250 or min(r, g, b) > 240):
            outside[i] = 1
            queue.append(i)
    for x in range(width):
        add(x); add((height-1)*width+x)
    for y in range(height):
        add(y*width); add(y*width+width-1)
    while queue:
        i=queue.popleft(); x=i % width
        for j in (i-width if i >= width else -1,
                  i+width if i+width < len(pixels) else -1,
                  i-1 if x else -1, i+1 if x < width-1 else -1):
            if j >= 0:
                add(j)
    result=image.copy()
    result.putdata([(*p[:3], 0) if outside[i] else p for i, p in enumerate(pixels)])
    return result


if __name__ == '__main__':
    templates = json.loads((ROOT / 'assets/phone-templates/templates.json').read_text())
    for template in templates:
        source = Image.open(ROOT / template['overlay'].lstrip('/')).convert('RGBA')
        assert source.size == (template['sourceWidth'], template['sourceHeight'])
        size = (template['printWidth'], template['printHeight'])
        alpha = interior_mask(source).resize(size, Image.Resampling.LANCZOS)
        mask = Image.new('RGBA', size, 'white')
        mask.putalpha(alpha)
        mask.save(ROOT / template['mask'].lstrip('/'), dpi=(300, 300), optimize=True)
        preview_overlay(source).save(ROOT / template['previewOverlay'].lstrip('/'), optimize=True)
        print(template['id'], size, alpha.getbbox())
