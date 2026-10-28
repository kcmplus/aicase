# AI 管理与双语展示

后台入口：`/admin/ai-prompts`。案例、风格与英文提示词、机型适配集中在三个页签。旧案例入口与旧风格入口分别跳转到对应页签。每个效果保存 `style`、`image_path`、`phone_model` 和 `prompt`（最多 8000 字符）；案例提示词是独立保存的生成记录，修改通用模板不会覆盖它。点击「从风格与机型填入」可以将当前通用规则复制到草稿，再自行调整并保存。

案例关联机型不会裁切图片，也不会修改机型的打印校准状态。新增样片以 iPhone 15 Pro 的窄长比例和左上镜头避让为构图试验；生成输出为 870 × 1808，不能替代厂家实际壳型刀模。使用内置 imagegen 生成，未调用后台保存的 OpenAI Key。原图来自项目已有的合成照片，不是用户上传的私人照片。

迁移 `0006_example_prompts` 增加效果提示词、机型关联和案例版本号。执行 `python manage.py seed_ai_recipes` 导入 3 个新风格、3 个案例，并为未改图的旧样片补全 12 份已有生成记录。导入只新增缺失案例，保留现有图片、提示词、停用状态、已删除效果与权限。旧样片补全有一次性审计标记，后续手动清空不会被再次填回。部署前备份数据库。

案例更新支持 `revision` 防止覆盖其他管理员的新修改；兼容旧客户端的请求，嵌套效果未提交提示词/机型字段时保留同风格的原值。提交空字符串或 null 才显式清除。公众接口只返回案例图片和风格标识，不公开提示词或内部机型关联。

## 本次新增案例

PNG 保留完整输出，页面使用 320 / 640 / 870 宽度的 WebP 及懒加载；三个原图共约 9.31 MB，最大预览共约 1.16 MB。

### 宠物手绘 · 镜头避让

原图：`frontend/storefront/assets/ai-styles/pets-original.png`

效果图：`frontend/storefront/assets/ai-recipes/pet-gouache.png`

模式：内置 imagegen / style-transfer。关联：iPhone 15 Pro。

完整提示词（山湖案例包含实际执行的两步生成）：

```text
Use case: style-transfer. Input image 1 is the edit target: the golden retriever photograph. Create ONE flat full-bleed phone-case artwork, narrow portrait width:height 70.6:146.6 (approximately 1:2.0765). Transform the same golden retriever into a warm whimsical gouache and crayon illustration, expressive irregular dark outlines, bold soft color blocks, paper grain and tiny meadow flowers. Preserve one dog, golden floppy ears, smiling face, seated pose, both front paws and the red patterned triangular bandana. Recompose the WHOLE dog down and slightly right: its entire head starts below y=40%, face near x=55%, y=50%, full dog inside x=14–88%, y=40–91%. Fill the upper-left x=0–68%, y=0–35% with low-detail pale blue sky and cream clouds only, reserved for an iPhone 15 Pro camera region. Keep alpine mountains, meadow and lake recognizable but simplified, and naturally extend the scenery around the smaller dog. Keep all essential details at least 8% from the edges. No stretching or simple center cropping. Continuous artwork to all four edges. Output flat art only: no phone, camera lenses, camera holes, outline, rounded corners, guides, labels, text, logos, watermark, panels or padding. This composition is a visual study, not a certified manufacturing dieline.
```

### 情侣拼贴 · 海岸记忆

原图：`frontend/storefront/assets/ai-styles/couples-original.png`

效果图：`frontend/storefront/assets/ai-recipes/couple-scrapbook.png`

模式：内置 imagegen / style-transfer。关联：iPhone 15 Pro。

完整提示词（山湖案例包含实际执行的两步生成）：

```text
Use case: style-transfer and compositing. Input image 1 is the edit target: the photograph of two fictional adults on the coast. Create ONE premium travel-scrapbook phone-case flat artwork, narrow portrait width:height 70.6:146.6 (about 1:2.0765). Preserve both adult identities, smiles, black bob haircut and rust sweater on woman, short brown hair and sage shirt on man, shoulder-to-shoulder pose. Retain real photographic texture inside a main gently tilted paper photo print placed in the LOWER TWO THIRDS: both heads entirely below y=42%, both faces near x=40–62%, y=54%, all important portrait details inside x=14–87%, y=42–88%. Surround this main intact couple photo with 4 to 6 small paper snippets using only the same blue sea, coastal cliffs and sky, warm ivory textured paper and a little translucent beige tape. Do not split or cut through faces, do not duplicate either person in the snippets. Upper-left x=0–68%, y=0–35% must be quiet warm ivory paper with faint pale-blue seaside texture and NO people or important details, reserved for an iPhone 15 Pro camera area. Subtle tactile paper shadows, airy cream and coastal blue palette, tasteful editorial balance. Keep continuous background to all four edges; essential details at least 8% from edges. No added people, writing, letters, logos, stickers with text, watermarks, phone body, camera, holes, border, guides or device mockup. Flat art only. This is a camera-aware visual study, not a calibrated printing template.
```

### 山湖水彩 · 旅行留白

原图：`frontend/storefront/assets/ai-styles/travel-original.png`

效果图：`frontend/storefront/assets/ai-recipes/lake-watercolor.png`

模式：内置 imagegen / style-transfer。关联：iPhone 15 Pro。

完整提示词（山湖案例包含实际执行的两步生成）：

```text
【第一步：以案例原图为输入】
Use case: style-transfer. Input image 1 is the edit target: the alpine lake photograph. Create ONE luminous watercolor and fine colored-pencil phone-case flat artwork. Narrow portrait width:height 70.6:146.6 (approximately 1:2.0765). Preserve the recognizable mountain silhouettes, blue alpine lake, evergreen forest, one small RED cabin on the RIGHT shore and one red wooden rowboat on the LOWER LEFT. Transparent watercolor washes, subtle paper grain, delicate pencil edges, luminous turquoise reflections, dusty sage trees and clear soft blue sky. Recompose for iPhone 15 Pro: main mountain peaks below y=38%, cabin around x=72%, y=58%, boat around x=32%, y=79%; all key objects inside x=12–88%, y=38–90%. Upper-left x=0–68%, y=0–35% must contain only airy low-detail pale sky and faint clouds, no key mountain peak or cabin, reserved for camera clearance. Naturally extend the scenery, do not stretch or merely center-crop. Full-bleed continuous painted backdrop to every edge, no opaque border. No people, extra boats, extra buildings, text, letters, logos, watermark, phone, camera lenses or holes, guides, measurements, device mockup or split panels. Output only the flat artwork. This is a composition study, not a certified manufacturing dieline.

【第二步：以第一步结果为输入，调整构图】
Use case: precise-object-edit. Edit target is the supplied completed watercolor alpine lake artwork. Keep the same narrow 70.6:146.6 aspect ratio, watercolor texture, blue and sage colors, one red cabin on the right and one red wooden rowboat at lower left. Change ONLY the vertical composition: lower and slightly reduce the entire mountain/forest/lake scene so that the HIGHEST MOUNTAIN PEAK begins at y=40% of the image height, never above y=38%. The entire top 38% must be uninterrupted pale blue sky with delicate clouds, especially the upper left 68% width; no mountains or trees may enter that upper band. Cabin around x=74%, y=62%, boat x=32%, y=81%, key details inside the inner 10% margin. Preserve natural landscape perspective and continuous background. Do not add new buildings, boats, text, phone, device borders, camera lenses, holes, watermark, guides or empty bands. Output one flat full-bleed phone-case composition study, not a device mockup or calibrated dieline.
```

## 验证

64 项后台测试、111 项前台测试和后台生产构建通过。新增测试覆盖案例提示词读写、公开接口脱敏、旧客户端字段保留、显式清空、长度及关联校验、并发版本冲突、权限和种子重复执行。浏览器验证旧地址跳转、三个页签、搜索、原图/效果对比、未保存提醒和提示词保存/刷新保留。

## 英文优先与统一效果展示（2026-10-27）

用户端和后台均按原图路径归组，左侧显示一次原图，右侧并排展示所有关联案例的 AI 效果。当前种子共 4 组原图、15 个效果。点击效果保留原始案例与风格组合，不合并或改写数据库记录；后台点图打开对应案例的效果编辑器，组内仍可单独管理各案例。后台保持中文操作界面。用户端默认英文，页头可切换中文；语言保存在 `popomo-language`，也支持 `?lang=en-US` / `?lang=zh-CN`。切换语言不会改变设计、照片、机型、生成额度、订单金额或表单填写。

`AIStyle.name/description` 与 `AIExample.name/subject` 为默认英文内容，新增可选 `name_zh/description_zh/subject_zh`。中文缺省时回退默认内容。案例完整提示词、内置通用模板和组合标题统一英文，仍不向公开目录暴露。已有渲染保存双语名称快照，保留已确认样片与订单的原始数据。

部署前备份数据库并执行迁移 `0007_ai_catalog_languages`。迁移仅将原始种子中的中文名称、说明和提示词转换为英文，并保留对应中文名称/说明；不覆盖已修改字段、清空的提示词或更换图片的生成记录。新环境仍运行 `seed_catalog` 与 `seed_ai_recipes`。无需重生成图片。


## 参考图提炼风格包（2026-10-27）

另新增 8 类英文风格模板及对应样片，原图仍归入同样的 4 组；默认目录增加至 23 个效果。完整说明、英文模板与素材链接见 [八组风格提示词与案例](ai-style-pack.md)。使用 `seed_ai_style_pack` 独立导入，保留旧种子命令行为和所有已管理内容。
