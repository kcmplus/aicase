# 手机机身颜色参考资料（待审阅）

研究日期：2026-11-14。范围严格对应新 UI `dist/flow-assets/data.json` 中的 50 款：Apple 23、Samsung 20、Xiaomi 7。机型名保留原样，未改业务代码、未导入数据库、未生成或下载变体打印图。

共 44 款具有明确来源范围的颜色参考，6 款因版本歧义标为 `needs_review` 并保留空颜色列表；正式参考颜色共 218 条。

## 使用边界

- 这是手机机身配色研究，不是供应商壳体颜色、可售 SKU、库存、打印材料或模板适配清单。
- `verified` 仅表示在所列官方页面核对到相应型号/地区的颜色，不代表已通过真机或生产验收，也不代表所有地区当前仍有售。
- `rgb` 保存红、绿、蓝三个 0–255 整数通道，是人工选取的近似显示色，全部不是官方 RGB / Pantone 或测量结果；同名颜色跨代可能不同。金属、珠光、玻璃、渐变与多色边框无法由单色块准确表达。不得用其生成打印图或替代真实预览素材。
- 英文保留来源配色名；中文通常是展示译名，不保证与各销售地区的营销译名一致。Xiaomi 14 Pro 的来源为中文，英文仅工作译名。
- 本轮仅准备供用户审阅的任务输入资料。确认并运行 harness 前不导入；将来导入也只能新增停用草稿，不能自动启用、覆盖人工配置，或把 `verified` 映射成可售。
- 启用前需确认销售地区、网络版与实体型号编号，并逐色检查对应底图/overlay、遮罩、机型映射及有效库存。颜色资料不能替代这些检查。

## 颜色值格式（2026-11-14 用户补充）

颜色不是一段文字，而是 RGB 三通道数值。例如石墨色的近似显示值：`{"r":86,"g":87,"b":84}`。初始化文件所有颜色已采用 `rgb` 对象；中英文名称仅辅助识别，稳定编码用作标识。前台绘制色块，后台支持取色器及 R/G/B 输入。每个通道必须是 0–255 整数；HEX 可换算展示，不另存第二份颜色值。RGB 不用于生成或替代真实机身预览素材。

## 初始化与无颜色规则（2026-11-14 用户补充）

`backend/management_api/seed/phone-color-reference.json` 同时作为首份初始化数据源，内含明确的 `initialization_policy`。本轮已准备数据和 harness 任务，尚未运行初始化或修改用户数据库。

- 后台提供「初始化基础颜色」，先展示匹配统计，再给现有且精确匹配的机型新增停用颜色草稿。44 款、218 条为参考数据量，实际导入量取决于已有机型匹配情况；其余 6 款待确认，不猜配色。
- 重复初始化只补缺失颜色，不覆盖名称、色块、资源、启用状态、排序或默认项等人工修改，不自动新建机型。
- 颜色没有设置，或没有任何已启用且预览资源有效的颜色时，用户端跳过颜色选项；仍使用该机型原有有效预览资源继续设计，不要求用户补选颜色。
- 有配置才显示该机型的可用颜色；切换机型要清除不适用的草稿颜色，不沿用全局四种演示色或默认蓝色。历史已付订单快照保持原样。
- 参考色块不等于真实预览资源，因此首份初始化数据默认停用；后台补齐对应资源并核验启用后才成为可选颜色。这不影响无颜色机型的原有流程。
- 最新总任务为 `harness/tasks/storefront-v35-migration.json`：在 aicase 中整体替换新版用户端并接通后台颜色配置；popomo-ui 仅作为只读设计来源。此前两个独立任务仅保留为历史草案，不再作为本轮入口。

## 逐型号来源与范围

所有下列正式颜色均核对了实际打开的官方页面正文/颜色选择器，未仅依赖搜索摘要。Apple 个别技术规格页遇到限流时，使用已成功打开的官方机型识别页中该型号的明确 Colors 段落；不把失败页列为证据。

| UI 机型 | 来源区域 / 网络 | 状态 | 颜色（英文名） | 官方来源 |
|---|---|---|---|---|
| iPhone 13 Pro | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Graphite、Gold、Silver、Sierra Blue、Alpine Green | [iPhone 13 Pro — Technical Specifications — Apple Support](https://support.apple.com/en-us/111871)<br>[Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 17 Pro | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Silver、Cosmic Orange、Deep Blue | [iPhone 17 Pro — Technical Specifications — Apple Support](https://support.apple.com/en-us/125090)<br>[Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 17 Pro Max | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Silver、Cosmic Orange、Deep Blue | [iPhone 17 Pro Max — Technical Specifications — Apple Support](https://support.apple.com/en-us/125091)<br>[Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 11 Pro | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 4G LTE | verified | Silver、Space Gray、Gold、Midnight Green | [Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 11 | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 4G LTE | verified | Black、Green、Yellow、Purple、(PRODUCT)RED、White | [iPhone 11 — Technical Specifications — Apple Support](https://support.apple.com/en-us/111865)<br>[Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 15 Plus | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Black、Blue、Green、Yellow、Pink | [iPhone 15 Plus — Technical Specifications — Apple Support](https://support.apple.com/en-us/111830)<br>[Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 15 Pro Max | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Black Titanium、White Titanium、Blue Titanium、Natural Titanium | [Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 16 Plus | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Black、White、Pink、Teal、Ultramarine | [Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 16 Pro Max | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Black Titanium、White Titanium、Natural Titanium、Desert Titanium | [iPhone 16 Pro Max — Technical Specifications — Apple Support](https://support.apple.com/en-us/121032)<br>[Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 14 | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Midnight、Starlight、(PRODUCT)RED、Blue、Purple、Yellow | [Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 14 Pro | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Space Black、Silver、Gold、Deep Purple | [iPhone 14 Pro — Technical Specifications — Apple Support](https://support.apple.com/en-us/111849)<br>[Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 14 Pro Max | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Space Black、Silver、Gold、Deep Purple | [Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 12 Pro | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Silver、Graphite、Gold、Pacific Blue | [iPhone 12 Pro — Technical Specifications — Apple Support](https://support.apple.com/en-us/111875)<br>[Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 13 | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | (PRODUCT)RED、Starlight、Midnight、Blue、Pink、Green | [iPhone 13 — Technical Specifications — Apple Support](https://support.apple.com/en-us/111872)<br>[Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 13 Pro Max | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Graphite、Gold、Silver、Sierra Blue、Alpine Green | [iPhone 13 Pro Max — Technical Specifications — Apple Support](https://support.apple.com/en-us/111870)<br>[Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 12 | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Black、White、(PRODUCT)RED、Green、Blue、Purple | [iPhone 12 — Technical Specifications — Apple Support](https://support.apple.com/en-us/111876)<br>[Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 12 Mini | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Black、White、(PRODUCT)RED、Green、Blue、Purple | [Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| Samsung A56 | 英国 / 5G | verified | Awesome Lightgrey、Awesome Graphite、Awesome Olive、Awesome Pink | [Samsung UK — Galaxy A56 5G / A36 5G launch](https://news.samsung.com/uk/samsung-marks-a-step-forward-with-ai-for-everyone-by-introducing-new-galaxy-a56-5g-galaxy-a36-5g-and-galaxy-a26-5g) |
| Samsung A36 | 英国 / 5G | verified | Awesome Lavender、Awesome Black、Awesome White、Awesome Lime | [Samsung UK — Galaxy A56 5G / A36 5G launch](https://news.samsung.com/uk/samsung-marks-a-step-forward-with-ai-for-everyone-by-introducing-new-galaxy-a56-5g-galaxy-a36-5g-and-galaxy-a26-5g) |
| Samsung A16 | 未确定；已核对菲律宾资料 / 未确定（4G LTE / 5G） | needs_review | 待版本确认，未填入正式列表 | [Samsung Philippines — Galaxy A16 5G and LTE launch](https://news.samsung.com/ph/elevating-everyday-with-the-new-samsung-galaxy-a16) |
| Samsung A55 | 英国 / 5G | verified | Awesome Ice Blue、Awesome Lemon、Awesome Lilac、Awesome Navy | [Samsung UK — Galaxy A55 5G / A35 5G launch](https://news.samsung.com/uk/galaxy-a55-5g-and-galaxy-a35-5g-awesome-innovations-and-security-engineered-for-everyone) |
| Samsung S21 | 爱尔兰 / 5G | verified | Phantom Violet、Phantom Grey、Phantom White、Phantom Pink | [Samsung Ireland — Galaxy S21 5G specifications](https://www.samsung.com/ie/smartphones/galaxy-s21-5g/specs/) |
| Samsung A05S | 爱尔兰 / 4G LTE | verified | Light Green、Silver、Black | [Samsung Ireland — Galaxy A05s SM-A057G](https://www.samsung.com/ie/business/smartphones/galaxy-a/galaxy-a05s-black-64gb-sm-a057gzkueub/) |
| Samsung A14 | 未确定；已核对西班牙 LTE 与拉美 5G / 未确定（4G LTE / 5G） | needs_review | 待版本确认，未填入正式列表 | [Samsung Spain — Galaxy A14 LTE SM-A145R](https://www.samsung.com/es/business/smartphones/galaxy-a/galaxy-a14-sm-a145rzkveub/)<br>[Samsung Latin America — Galaxy A14 5G launch](https://news.samsung.com/latin/samsung-presenta-galaxy-a14-5g-disponible-en-america-latina-en-febrero) |
| Samsung A35 | 英国 / 5G | verified | Awesome Ice Blue、Awesome Lemon、Awesome Lilac、Awesome Navy | [Samsung UK — Galaxy A55 5G / A35 5G launch](https://news.samsung.com/uk/galaxy-a55-5g-and-galaxy-a35-5g-awesome-innovations-and-security-engineered-for-everyone) |
| Samsung A52 | 未确定；已核对德国资料 / 未确定（4G LTE / 5G） | needs_review | 待版本确认，未填入正式列表 | [Samsung Germany — Galaxy A52 / A52 5G selector](https://www.samsung.com/de/smartphones/galaxy-a/galaxy-a52-5g/buy/) |
| Samsung A15 | 未确定；已核对英国资料 / 未确定（4G LTE / 5G） | needs_review | 待版本确认，未填入正式列表 | [Samsung UK — Galaxy A15 SM-A155F](https://www.samsung.com/uk/business/smartphones/galaxy-a/galaxy-a15-yellow-128gb-sm-a155fzydeub/)<br>[Samsung UK — Galaxy A15 5G SM-A156B](https://www.samsung.com/uk/business/smartphones/galaxy-a/galaxy-a15-5g-yellow-128gb-sm-a156bzydeub/) |
| Samsung S25+ | 美国 / 5G | verified | Navy、Icyblue、Silver Shadow、Mint、Blueblack、Coralred、Pinkgold | [Samsung US — Galaxy S25 & S25+ features and colors](https://www.samsung.com/us/smartphones/galaxy-s25/) |
| Samsung S24+ | 海湾地区英文支持页 / 5G | verified | Marble Gray、Onyx Black、Cobalt Violet、Amber Yellow、Jade Green、Sandstone Orange、Sapphire Blue | [Samsung Gulf — Galaxy S24 Colors & Availability](https://www.samsung.com/ae/support/mobile-devices/how-many-and-what-colors-are-available-on-the-market-for-the-s24-device/) |
| Samsung S24 FE | 爱尔兰 / 5G | verified | Blue、Graphite、Mint、Yellow | [Samsung Ireland — Galaxy S24 FE SM-S721B](https://www.samsung.com/ie/business/smartphones/galaxy-s/galaxy-s24-fe-graphite-128gb-sm-s721bzkdeub/) |
| Samsung S24 Ultra | 海湾地区英文支持页 / 5G | verified | Titanium Gray、Titanium Black、Titanium Violet、Titanium Yellow、Titanium Green、Titanium Orange、Titanium Blue | [Samsung Gulf — Galaxy S24 Colors & Availability](https://www.samsung.com/ae/support/mobile-devices/how-many-and-what-colors-are-available-on-the-market-for-the-s24-device/) |
| Samsung S22 | 新加坡 / 5G | verified | Phantom White、Phantom Black、Green、Graphite、Bora Purple、Violet、Sky Blue、Pink Gold、Cream | [Samsung Singapore — Galaxy S22 5G SM-S901E](https://www.samsung.com/sg/business/smartphones/galaxy-s/galaxy-s22-for-business-sm-s901-sm-s901ezvgxsp/buy/) |
| Samsung S22 Ultra | 加拿大 / 5G | verified | Burgundy、Green、Phantom White、Phantom Black、Graphite、Sky Blue、Red | [Samsung Canada — Galaxy S22 Ultra](https://www.samsung.com/ca/business/smartphones/galaxy-s22-ultra/) |
| Samsung S23 | 全球发布资料；专属色按市场供应 / 5G | verified | Phantom Black、Cream、Green、Lavender、Graphite、Lime | [Samsung Global Newsroom — Galaxy S23 series global launch](https://news.samsung.com/global/samsung-announces-global-launch-of-the-galaxy-s23-series) |
| Samsung S23+ | 全球发布资料；专属色按市场供应 / 5G | verified | Phantom Black、Cream、Green、Lavender、Graphite、Lime | [Samsung Global Newsroom — Galaxy S23 series global launch](https://news.samsung.com/global/samsung-announces-global-launch-of-the-galaxy-s23-series) |
| Samsung S23 Ultra | 全球发布资料；专属色按市场供应 / 5G | verified | Phantom Black、Cream、Green、Lavender、Graphite、Lime、Sky Blue、Red | [Samsung Global Newsroom — Galaxy S23 series global launch](https://news.samsung.com/global/samsung-announces-global-launch-of-the-galaxy-s23-series) |
| Redmi A3 | 国际版 / 4G LTE | verified | Midnight Black、Forest Green、Star Blue | [Redmi A3 — Xiaomi Global specifications](https://www.mi.com/global/product/redmi-a3/specs/) |
| Redmi 14C | 未确定；已核对国际 4G 与印度 5G / 未确定（4G LTE / 5G） | needs_review | 待版本确认，未填入正式列表 | [Redmi 14C — Xiaomi Global specifications](https://www.mi.com/global/product/redmi-14-c/specs/)<br>[Redmi 14C 5G — Xiaomi India specifications](https://www.mi.com/in/product/redmi-14c-5g/specs/) |
| Xiaomi 14T Pro | 国际版 / 5G | verified | Titan Black、Titan Blue、Titan Gray | [Xiaomi 14T Pro — Xiaomi Global specifications](https://www.mi.com/global/product/xiaomi-14t-pro/specs/) |
| Xiaomi 14 Pro | 中国大陆 / 5G | verified | Black、White、Rock Green、Titanium Special Edition、Elegant Gray、Lava Orange、Meteor Blue、Gulf Blue、Olive Green | [小米商城官方机型与配置清单（Xiaomi 14 Pro 各版本）](https://www.mi.com/article/detail/9daf2be668bb.html) |
| Xiaomi 12 | 国际版 / 5G | verified | Gray、Blue、Purple | [Xiaomi 12 — Xiaomi Global specifications](https://www.mi.com/global/product/xiaomi-12/specs/) |
| Redmi Note12 Pro+ | 未确定；已核对国际 5G 资料 / 候选 5G，待型号确认 | needs_review | 待版本确认，未填入正式列表 | [Redmi Note 12 Pro+ 5G — Xiaomi Global specifications](https://www.mi.com/global/product/redmi-note-12-pro-plus-5g/specs/) |
| Redmi 13-4G | 国际版 / 4G LTE | verified | Midnight Black、Sandy Gold、Pearl Pink、Ocean Blue | [Redmi 13 — Xiaomi Global specifications](https://www.mi.com/global/product/redmi-13/specs/) |
| iPhone 16 Pro | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Black Titanium、White Titanium、Natural Titanium、Desert Titanium | [iPhone 16 Pro — Technical Specifications — Apple Support](https://support.apple.com/en-us/121031)<br>[Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 16 | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Black、White、Pink、Teal、Ultramarine | [Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 15 Pro | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Black Titanium、White Titanium、Blue Titanium、Natural Titanium | [iPhone 15 Pro — Technical Specifications — Apple Support](https://support.apple.com/en-us/111829)<br>[Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 15 | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Black、Blue、Green、Yellow、Pink | [iPhone 15 — Technical Specifications — Apple Support](https://support.apple.com/en-us/111831)<br>[Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| Samsung S24 | 海湾地区英文支持页 / 5G | verified | Marble Gray、Onyx Black、Cobalt Violet、Amber Yellow、Jade Green、Sandstone Orange、Sapphire Blue | [Samsung Gulf — Galaxy S24 Colors & Availability](https://www.samsung.com/ae/support/mobile-devices/how-many-and-what-colors-are-available-on-the-market-for-the-s24-device/) |
| iPhone 17 | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Black、White、Mist Blue、Sage、Lavender | [iPhone 17 — Technical Specifications — Apple Support](https://support.apple.com/en-us/125089)<br>[Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |
| iPhone 16e | Apple 美国英文技术规格/机型识别页；颜色参考，不承诺当地在售 / 5G | verified | Black、White | [Identify your iPhone model — Apple Support](https://support.apple.com/en-us/108044) |

## 必须先解决的型号歧义

| UI 机型 | 已核对证据与待确认事项 |
|---|---|
| Samsung A16 | UI 未标 LTE/5G 或 SM 型号。菲律宾 LTE 为 Black/Grey/Light Green；5G 为 Blue Black/Gold，不能拼成同一列表。需确认设备版本、销售区域及模板适配后整理正式颜色。 |
| Samsung A14 | UI 未标 SM-A145 / SM-A146。西班牙 LTE 资料为 Black/Light Green/Silver；拉美 5G 发布为 Black/Silver/Dark Red/Light Green。两地区仅作歧义证据，不合并。 |
| Samsung A52 | 官方选择器区分 Galaxy A52、A52 5G 与 4G/5G，并列 Awesome Black/Blue/White/Violet。UI 未给型号编号，不把共用选择器等同模板适配确认；不包含 A52s。 |
| Samsung A15 | 英国两版均列 Blue Black/Blue/Yellow，但 UI 未确定 SM-A155 / SM-A156；颜色相同不能证明模板或外形兼容，正式列表留空。 |
| Redmi 14C | 国际 4G 为 Midnight Black/Sage Green/Dreamy Purple/Starry Blue；印度 5G 为 Stargaze Black/Starlight Blue/Stardust Purple。UI 未标网络版，同尺寸不能证明同模板，正式颜色留空。 |
| Redmi Note12 Pro+ | 候选官方名称为 Redmi Note 12 Pro+ 5G，国际配色 Polar White/Midnight Black/Sky Blue。UI 缺少 5G 与销售区域，须确认是否该版本；不混用 Pro（非 Plus）、中国特别版或其他地区命名。 |

## 特殊版本、地区与证据处理

- Xiaomi 14 Pro 官方清单确有 9 个颜色/版本名称，但钛金属特别版和 5 个限量定制色不是普通版本的随意换色。需在任务中决定分别建版本或限制适配；本参考文件不宣称可共用同一模板。来源为小米官方配置清单，产品参数页本次正文未呈现颜色，未依赖该空正文推断。
- Samsung S22 的 Bora Purple 与 Violet 是不同名称，参考采用新加坡同一选择器中的 9 色。S22 Ultra 单独采用加拿大 7 色，不把普通版颜色复制过去。
- Samsung S23 / S23+ 的 Sky Blue 与 Red 未收录；全球官方发布明确只列为 Ultra 的专属色。搜索曾出现把系列颜色泛化为所有机型的支持页，本文件采用逐型号区分明确的全球发布资料。
- Samsung S24 FE 采用爱尔兰选择器与正文确认的 Blue / Graphite / Mint / Yellow，不把其他地区营销图片说明中的 Gray 自动补入。
- Samsung A05s、A35/A55、A36/A56 均限定表中地区。未把不同地区的配色合并成无区域的全集。
- Xiaomi 12 采用国际版三色；Redmi 13-4G 已明确网络版，才匹配国际 Redmi 13 规格。

## 后续任务验收输入

1. 让审阅者先确定 6 个歧义型号的实体型号编号、4G/5G 与目标市场；确认前保持空正式列表。
2. 确定特别版、在线专属色、已停产色是否需要作为后台停用候选；不以官方曾上市推断供应商可供货。
3. 逐个机型/颜色配置真实预览素材及遮罩，再由独立产品验收确认。不得批量给已有中性 overlay 染色后声称与真机一致。
4. harness 实施时保留人工修改，只新增缺失的停用草稿，并记录本文件版本、研究日期、区域和来源。
5. 本资料整理与结构核对不替代 Astra 最终产品验收。

## 测试环境初始化记录（2026-11-16）

经用户明确授权，已在 `aicase.chunpat.cc` 测试环境执行现有参考初始化流程。执行前颜色记录为 0；44 个机型精确匹配，新增 218 条 RGB 颜色草稿，6 个待确认参考机型跳过，不新增机型或覆盖人工配置。再次预览待新增为 0。参考文件摘要为 `ed674e58fed4969f7f1d037655002f6e677e19132be3fff59cd4c68cbe3056b0`。

记录保留在测试服务器 `/var/lib/aicase-dev/backups/rgb-init-20261116T075623Z/`，含初始化前颜色快照及新增记录 ID；后台审计保留本次操作。初始化数据均为停用草稿，未绑定／核验预览资源，未因此对前台开放。`iPhone 18 Pro` 不在本份参考资料中，未生成该机型颜色。本次只初始化测试数据，没有发布代码、发起付款或打印。

## RGB 色块与预览素材分离（2026-11-16）

用户进一步要求前台显示已初始化的 RGB。颜色启用不再依赖覆盖图／遮罩：合法 RGB 且已启用的机型颜色可直接显示与选择，普通／磁吸款共用该机型的 RGB 选项；无配置时仍跳过。不自动为缺少参考资料的机型编造配色。

可选预览素材仍须经过原有路径、尺寸、内容哈希、归属和人工核验检查，且匹配当前款式模板才用于预览。没有可用素材时返回 `previewMode=rgb, resource=null`，只提供色块及颜色摘要，继续使用基础手机壳效果图，不假称已经生成准确机身配色效果。图片缺失／失效不会导致合法 RGB 选项消失，也不能改变库存、商品或打印资格。

RGB 选色提交 `code`、`version=0` 和三通道值；订单服务验证机型归属、启用状态与当前 RGB，拒绝过期或伪造选择，由服务端冻结名称和 RGB。历史带素材版本的选色格式保持兼容，已付订单快照不重算，打印导出仍使用原打印遮罩与原设计图。
