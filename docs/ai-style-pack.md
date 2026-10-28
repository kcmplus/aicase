# 八组 AI 风格提示词与案例

来源：用户提供的《手机壳制作skill.zip》共 14 张参考板。以下从第 3、4、5、6、7、12、13、14 张中提炼视觉特征，并重新编写英文提示词。

每种风格提供一份可复用英文模板、一张实际生成样片，以及保存在后台的完整案例提示词。样片使用项目已有的合成人像、宠物、情侣与旅行原图，由内置 imagegen 生成。厚涂微景观经过两步生成，完整步骤已保留。

用户端默认英文，可切换中文。后台操作仍为中文，生图提示词保持英文且不会通过公开目录下发。

| 风格 | 英文名称 | 参考图 | 案例 |
| --- | --- | --- | --- |
| 复古星星拼贴 | Pop star collage | 3.png | 雏菊女孩 · 星星拼贴 |
| 复古唱片封面 | Vintage record sleeve | 4.png | 海边女孩 · 复古唱片 |
| 银色压印浮雕 | Silver relief | 5.png | 雏菊女孩 · 银色浮雕 |
| 手刻版画明信片 | Carved postcard | 6.png | 山湖旅行 · 手刻版画 |
| 厚涂立体微景观 | Painted miniature | 7.png | 山湖旅行 · 厚涂微景观 |
| 宠物波普贴纸 | Pet pop stickers | 12.png | 金毛伙伴 · 波普贴纸 |
| 油画棒宠物肖像 | Oil pastel companion | 13.png | 金毛伙伴 · 油画棒 |
| 几何剪纸拼贴 | Geometric paper cut | 14.png | 海岸合照 · 几何剪纸 |

## 使用方法

在「AI 管理 → 案例」点击效果图，可以查看或复制本案例完整提示词；在「风格与提示词」中编辑风格，可通过模板下拉框填入以下通用提示词。换用自己的照片时，保留身份、数量和机型构图规则，并补充实际主体特征。

本批样片为约 1:2.08 的竖版构图预览，上方预留背景以方便镜头区域适配。具体生产前须使用实际壳型刀模；银色、浮雕与厚涂均为画面模拟质感，普通平面打印不会产生这些材料和触感。

共用原图的案例继续归入同组。导入后，默认种子共有 4 组原图、23 个效果。旧案例、手动编辑的提示词、停用状态及已删除的效果保持原样。

## 1. 复古星星拼贴 · Pop star collage

黑白人物剪贴、纸边与明亮星芒，形成复古杂志拼贴。

案例：海边人像转为黑白剪贴与彩色星芒。

[原图](../frontend/storefront/assets/ai-styles/original.png) · [生成效果](../frontend/storefront/assets/ai-style-pack/star-collage.png)

可复用英文提示词：

```text
Transform the input photo into a retro magazine star collage. Keep the main subject as a recognizable high-contrast black-and-white photographic cutout with fine halftone texture and a slightly irregular white paper edge. Layer it over vivid pink paper with a few red and cream starbursts, subtle newsprint grain and small torn-paper accents. Stars belong behind the subject and must not cover the face. Use one main cutout, not a grid or a repeated portrait. Keep the composition playful, graphic and tactile; do not invent magazine headlines.

Subject preservation: Use the input photo as the identity reference. Preserve the subjects' identity, count, age, recognizable features, expression, pose, clothing and important accessories, unless the style explicitly calls for repeated cutouts of the SAME subject. Do not invent another person or substitute an animal breed.
Composition: Follow the target phone model's actual print template when provided. Keep important subjects outside camera cutouts and trim areas; resize or reposition the whole subject and extend the background naturally. Do not stretch or crop through faces, ears, hands or paws.
Output: One continuous flat artwork, full bleed, with no phone or case mockup, camera lenses, cutout holes, rounded device frame, measurement guides, watermark, logo or invented text. Any metallic or raised texture is an illustrated visual effect, not a claim about the printed material.
```

## 2. 复古唱片封面 · Vintage record sleeve

双色人像、褪色油墨与唱片纸套磨损质感。

案例：同一张人像转为无文字复古唱片封面。

[原图](../frontend/storefront/assets/ai-styles/original.png) · [生成效果](../frontend/storefront/assets/ai-style-pack/vinyl-sleeve.png)

可复用英文提示词：

```text
Transform the input photo into a vintage independent record-sleeve artwork. Use an intimate recognizable photographic portrait, deep midnight-blue and warm ivory duotone, soft film grain, slightly faded print density, tiny paper scratches and gentle edge wear. Keep facial detail legible and the mood calm and nostalgic. Integrate the image into the paper surface with restrained halftone texture, not a glossy digital filter. Render a single continuous design with no actual record, disc, plastic sleeve, artist name, album title, warning label or typography.

Subject preservation: Use the input photo as the identity reference. Preserve the subjects' identity, count, age, recognizable features, expression, pose, clothing and important accessories, unless the style explicitly calls for repeated cutouts of the SAME subject. Do not invent another person or substitute an animal breed.
Composition: Follow the target phone model's actual print template when provided. Keep important subjects outside camera cutouts and trim areas; resize or reposition the whole subject and extend the background naturally. Do not stretch or crop through faces, ears, hands or paws.
Output: One continuous flat artwork, full bleed, with no phone or case mockup, camera lenses, cutout holes, rounded device frame, measurement guides, watermark, logo or invented text. Any metallic or raised texture is an illustrated visual effect, not a claim about the printed material.
```

## 3. 银色压印浮雕 · Silver relief

将照片转为拉丝银色浅浮雕，保留可辨认的人像轮廓。

案例：原有人像与雏菊的银色浅浮雕效果。

[原图](../frontend/storefront/assets/ai-styles/original.png) · [生成效果](../frontend/storefront/assets/ai-style-pack/silver-relief.png)

可复用英文提示词：

```text
Translate the input photo into a convincing embossed silver-foil bas-relief illustration. Treat the entire artwork as one continuous sheet of satin silver: raised contours for the subject, shallow recessed fine details, delicate brushed-metal grain and restrained soft wrinkles around the background. Use directional light from the upper right to reveal relief with readable highlights and shadows, without clipped white glare. Preserve facial likeness through sculpted planes and silhouette. Keep it monochrome silver, with no color photograph pasted on top, no jewelry object, no lettering and no chrome liquid distortion. The result is a flat image depicting metal, not a fabricated metal object.

Subject preservation: Use the input photo as the identity reference. Preserve the subjects' identity, count, age, recognizable features, expression, pose, clothing and important accessories, unless the style explicitly calls for repeated cutouts of the SAME subject. Do not invent another person or substitute an animal breed.
Composition: Follow the target phone model's actual print template when provided. Keep important subjects outside camera cutouts and trim areas; resize or reposition the whole subject and extend the background naturally. Do not stretch or crop through faces, ears, hands or paws.
Output: One continuous flat artwork, full bleed, with no phone or case mockup, camera lenses, cutout holes, rounded device frame, measurement guides, watermark, logo or invented text. Any metallic or raised texture is an illustrated visual effect, not a claim about the printed material.
```

## 4. 手刻版画明信片 · Carved postcard

手刻线条、套色油墨与纸纹，把旅行风景变成版画。

案例：山峰、红色小屋与木船的套色版画。

[原图](../frontend/storefront/assets/ai-styles/travel-original.png) · [生成效果](../frontend/storefront/assets/ai-style-pack/block-print.png)

可复用英文提示词：

```text
Reinterpret the input scene as a hand-carved linocut and woodblock print. Use confident carved contour lines, small directional hatching, solid ink shapes, subtle registration offsets and visibly textured ivory paper. Limit the palette to deep indigo, lake blue, sage green, warm cream and small rust-red accents. Simplify detail into readable printed shapes while preserving the scene's major geometry and spatial relationships. Make the carving and ink coverage visibly handmade, not smooth vector clip art. The paper texture must continue to the canvas edges; no postcard border, postage stamp frame, caption or lettering.

Subject preservation: Use the input photo as the identity reference. Preserve the subjects' identity, count, age, recognizable features, expression, pose, clothing and important accessories, unless the style explicitly calls for repeated cutouts of the SAME subject. Do not invent another person or substitute an animal breed.
Composition: Follow the target phone model's actual print template when provided. Keep important subjects outside camera cutouts and trim areas; resize or reposition the whole subject and extend the background naturally. Do not stretch or crop through faces, ears, hands or paws.
Output: One continuous flat artwork, full bleed, with no phone or case mockup, camera lenses, cutout holes, rounded device frame, measurement guides, watermark, logo or invented text. Any metallic or raised texture is an illustrated visual effect, not a claim about the printed material.
```

## 5. 厚涂立体微景观 · Painted miniature

用厚重颜料、刮刀肌理和柔和阴影构成立体小世界。

案例：将同一片山湖转为颜料堆叠的微景观。

[原图](../frontend/storefront/assets/ai-styles/travel-original.png) · [生成效果](../frontend/storefront/assets/ai-style-pack/impasto-miniature.png)

可复用英文提示词：

```text
Transform the input scene into a premium miniature landscape made from thick oil-paint impasto. Model terrain, buildings, vegetation and water with tactile palette-knife ridges, raised painted edges and visible brushwork. Use a gently elevated three-quarter viewpoint while retaining the major left-to-right relationships and recognizable landmarks. Show believable small-scale depth with soft studio-like light and delicate contact shadows; it should feel sculpted from paint, not made from plastic toys. Make the miniature a compact raised terrain relief seen from an elevated 35-degree angle, with softly tapered paint edges and subtle contact shadows on a continuous cream and pale-blue painted backdrop. Keep the entire tiny world visible and its key landmarks recognizable. No display pedestal, tabletop, frame, typography or duplicate photo panel.

Subject preservation: Use the input photo as the identity reference. Preserve the subjects' identity, count, age, recognizable features, expression, pose, clothing and important accessories, unless the style explicitly calls for repeated cutouts of the SAME subject. Do not invent another person or substitute an animal breed.
Composition: Follow the target phone model's actual print template when provided. Keep important subjects outside camera cutouts and trim areas; resize or reposition the whole subject and extend the background naturally. Do not stretch or crop through faces, ears, hands or paws.
Output: One continuous flat artwork, full bleed, with no phone or case mockup, camera lenses, cutout holes, rounded device frame, measurement guides, watermark, logo or invented text. Any metallic or raised texture is an illustrated visual effect, not a claim about the printed material.
```

## 6. 宠物波普贴纸 · Pet pop stickers

同一只宠物的照片贴纸搭配波点、星星与鲜明色块。

案例：同一只金毛与红领巾的波普贴纸拼贴。

[原图](../frontend/storefront/assets/ai-styles/pets-original.png) · [生成效果](../frontend/storefront/assets/ai-style-pack/pet-pop-stickers.png)

可复用英文提示词：

```text
Create a playful 1990s-inspired pet photo-sticker collage. Use the SAME pet from the input as every sticker: one large central portrait and four smaller cutouts of that pet's face or upper body. Repetition is intentional; do not introduce a different animal. Preserve photoreal fur, markings, eye color and the original accessory, surrounded by uneven white sticker edges. Layer these over cobalt blue and bubblegum pink paper, small sunny yellow dots, hand-drawn stars and a few simple squiggles. Keep the central face clear and visually dominant. No costumes, invented hats, invented names, dates, biography labels, words or speech bubbles.

Subject preservation: Use the input photo as the identity reference. Preserve the subjects' identity, count, age, recognizable features, expression, pose, clothing and important accessories, unless the style explicitly calls for repeated cutouts of the SAME subject. Do not invent another person or substitute an animal breed.
Composition: Follow the target phone model's actual print template when provided. Keep important subjects outside camera cutouts and trim areas; resize or reposition the whole subject and extend the background naturally. Do not stretch or crop through faces, ears, hands or paws.
Output: One continuous flat artwork, full bleed, with no phone or case mockup, camera lenses, cutout holes, rounded device frame, measurement guides, watermark, logo or invented text. Any metallic or raised texture is an illustrated visual effect, not a claim about the printed material.
```

## 7. 油画棒宠物肖像 · Oil pastel companion

柔软蜡质笔触与叠色颗粒，绘出温暖的宠物肖像。

案例：用油画棒颗粒与柔软笔触描绘同一只金毛。

[原图](../frontend/storefront/assets/ai-styles/pets-original.png) · [生成效果](../frontend/storefront/assets/ai-style-pack/oil-pastel-pet.png)

可复用英文提示词：

```text
Transform the pet photo into one charming oil-pastel portrait on toothy paper. Build fluffy fur from short broken waxy strokes, layered warm colors, visible paper flecks and a few softly smudged edges. Keep bright expressive eyes and a recognizable muzzle, with accurate coat colors and accessories. Use broad muted pastel shapes for the original setting, warm cream highlights and restrained sage, peach and pale-blue accents. The surface should clearly show wax-crayon pigment and layered color, not watercolor washes, smooth digital airbrush or heavy black cartoon outlines. Render ONE pet, not a nine-panel grid or a collection of different animals.

Subject preservation: Use the input photo as the identity reference. Preserve the subjects' identity, count, age, recognizable features, expression, pose, clothing and important accessories, unless the style explicitly calls for repeated cutouts of the SAME subject. Do not invent another person or substitute an animal breed.
Composition: Follow the target phone model's actual print template when provided. Keep important subjects outside camera cutouts and trim areas; resize or reposition the whole subject and extend the background naturally. Do not stretch or crop through faces, ears, hands or paws.
Output: One continuous flat artwork, full bleed, with no phone or case mockup, camera lenses, cutout holes, rounded device frame, measurement guides, watermark, logo or invented text. Any metallic or raised texture is an illustrated visual effect, not a claim about the printed material.
```

## 8. 几何剪纸拼贴 · Geometric paper cut

几何纸片、剪裁边缘与印刷肌理，把合照变为鲜明图形。

案例：以层叠几何纸片重构情侣与海岸。

[原图](../frontend/storefront/assets/ai-styles/couples-original.png) · [生成效果](../frontend/storefront/assets/ai-style-pack/geometric-paper.png)

可复用英文提示词：

```text
Rebuild the input photo as a modern geometric cut-paper collage. Use carefully layered angular and curved paper shapes, hand-cut edges, subtle paper grain and small print-registration imperfections. Preserve recognizable silhouettes, expressions, clothing colors and key facial cues through simplified shapes, without turning the subjects into anonymous symbols. Use a restrained palette sampled from the photo with ivory, dark ink and one lively accent; let the background scenery become broad interlocking shapes. Add fine drawn accents only where they clarify form. Keep it a flat editorial artwork, with no typography, poster headings, text fragments or extra subjects.

Subject preservation: Use the input photo as the identity reference. Preserve the subjects' identity, count, age, recognizable features, expression, pose, clothing and important accessories, unless the style explicitly calls for repeated cutouts of the SAME subject. Do not invent another person or substitute an animal breed.
Composition: Follow the target phone model's actual print template when provided. Keep important subjects outside camera cutouts and trim areas; resize or reposition the whole subject and extend the background naturally. Do not stretch or crop through faces, ears, hands or paws.
Output: One continuous flat artwork, full bleed, with no phone or case mockup, camera lenses, cutout holes, rounded device frame, measurement guides, watermark, logo or invented text. Any metallic or raised texture is an illustrated visual effect, not a claim about the printed material.
```

## 完整记录与导入

通用模板及每张案例实际使用的英文提示词，统一保存于 [ai-style-pack.json](../backend/management_api/seed/ai-style-pack.json)。后台模板也直接读取同一份通用提示词，避免两处内容不一致。

在已初始化基础目录和旧案例的环境中执行：

```bash
backend/.venv/bin/python backend/manage.py seed_ai_style_pack
```

命令导入前检查原图、效果图与关联机型是否存在，只新增缺失记录，支持重复执行。所有生成图片在 `frontend/storefront/assets/ai-style-pack/`，轻量预览由 `npm run images:build` 生成。
