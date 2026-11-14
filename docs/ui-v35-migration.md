# POPOMO V35 用户端迁移对照与交接

## 基准与本轮边界

- 冻结任务：`storefront-v35-migration`，第一组已记录检查点，本轮为开发第二组（作品／详情、教程、关于、设备展示与公共弹窗），待独立测试。整站替换尚未完成。
- 2026-11-14 开始核对：本仓库分支 `codex/ui-v35-migration`，起始 HEAD `d5725f326f84b80c4aff7386930ac1a76d606fc1`，工作区干净。Git 检查点由 harness 创建，开发没有暂存、提交或切换分支。
- 只读参考 `../popomo-ui/dist`，HEAD 为 `5501bedb720d3e7552428b0dc75174973e87934c`，与冻结基准一致，无工作区差异；共 12 个 HTML。未修改参考仓库、历史 `sites/` 或终端仓库。
- 有效入口仍是 `frontend/storefront/index.html` → `simple-app.js`，新公共展示在 `v35-shell.js` / `v35-shell.css`、`v35-pages.js` / `v35-pages.css`；复用原业务服务，未引入参考版模拟订单、身份和付款脚本。
- `assets/v35/` 为该提交的 DM Sans 字体、背景、教程封面、AI 封面与九张灵感静态图；第二组另从同一基准 `assets/pet.png` 转为 900px 内 WebP，用于关于页照片示例；仅作公共设计示例，不含客户图片，不宣称是实际生成结果或可售机型。
- 状态用语：**本轮实现**仅表示代码已接入且完成所列开发自测；**保留待迁移**表示旧业务页面还在正常入口，不表示新版验收通过；**待实现**必须在后续功能组完成，不能把主流程改称未开放。

## 参考页面与有效入口

下表逐一列出全部参考 HTML。路径以 `frontend/storefront/` 为根；所有未列浏览器证据的项均未完成浏览器验证。

| 参考页面 | 当前／目标用户入口 | 后端契约及实现位置 | 本轮处理、差异与证据 |
| --- | --- | --- | --- |
| `index.html` | `/`、`#home`；相册主按钮、图库次入口、AI 入口 | 上传 `simple-upload.js`；库存 `stock-catalog.js`；价格 `runtime-catalog.js`；设备入口 `station-entry.js` | 本轮实现 V35 紫色背景、字体、玻璃导航、扇形灵感、故事区、图库区、AI 引导、FAQ、现行教程。复用 `home-photo` / `receivePhoto`，真实业务服务没有替换成参考模拟。证据：`ui-v35.test.mjs` 5 项；浏览器待验。 |
| `customize.html` | 当前 `#choose`、`#choose?design=…`、`#choose?source=photo`，AI `&studio=1` | `simple-app.js` 编辑状态、`phone-templates.js`、`print-export.js`；`GET /api/v1/store/phone-models/` | 保留待第三组迁移。机型、底图、图层、裁切、旋转、文字、贴纸、预览均需保留；不能照搬默认蓝色。 |
| `works-center.html` | `#designs`、实体 HTML 别名；首页图库、菜单进入 | 现有 `simple-core.js` 六款可编辑设计 + `catalog.js` 标题／分类；`v35-pages.js` | 第二组接入作品卡片、分类、双语搜索、计数、无匹配空态及详情。现有 `GET /api/v1/catalog/` 提供价格／AI，并无公开客户作品接口；不把参考本地发布／点赞当服务端社区。自测见下文，浏览器待验。 |
| `work-detail.html` | `#work?id=…`，兼容参考种子 `popomo-` 前缀、实体别名 | `v35-pages.js`；现有设计 ID → `#choose?design=…` 原编辑模型 | 第二组实现大图、模板说明、返回作品中心、相关推荐和实际编辑入口；未知 ID 显示失效态，不猜其他作品。无伪造点赞／作者／机型库存／本地创建订单。 |
| `my-designs.html` | 当前 `#pass` 为当前已保存设计；目标我的设计列表／详情 | `simple-storage.js` IndexedDB；服务端确认的 customer 身份用于分区 | 当前保存与订单详情保留，完整本机设计列表、恢复、删除、身份隔离待第三组。文案必须说明本机保存，无云同步承诺。旧无归属缓存不自动归入账户。 |
| `checkout.html` 结算 | `#checkout` | `order-service.js`；`POST /api/v1/store/orders/`（建单）、`orders/{reference}/checkout/`（渠道结算）；服务端金额与 request_key | 保留待第六组新版结算和单份约束。配送仅草稿，禁止收款／推单。不得迁入参考 quantity 增减和定时付款。 |
| `checkout.html?view=orders` 列表 | `#orders` | `GET /api/v1/store/orders/?page=…`；`ordersPage` | 公共导航已接现有真实订单列表，列表视觉和全部状态待第六组。不能改为 sessionStorage 订单。 |
| `checkout.html` 详情 | 当前 `#pass`、`#payment?order=…` 与列表 `view-order` | `GET orders/{reference}/`、print-files、fulfillment、confirm-print、retry-dispatch；`simple-app.js` | 真实手机门禁保留；新版详情、设备信息、扫码、退款取消、未知结果提示待第六组。出货不自动领取。 |
| `checkout.html` 支付返回 | `#payment?order=…`，保留现有支付 URL 参数 | `payment-state.js`、Stripe / Airwallex 查询与渠道通知 | 保留待第六组；返回页只查询，不能写 paid。待核实／失败／关闭／退款／取消须逐项测试。 |
| `account.html` | `#account`；权益 `#membership` 保留旧深链接 | `customer-account.js`；customer/send-code、verify、customer、credits；`ai-account/` | 公共账户入口接现有 API 页面，V35 表单、退出／失效／余额流水待第三组。未接 OAuth、会员购买、头像修改不出现可提交入口；本轮未复制参考模拟实现。 |
| `printers.html` | `#printers`、实体别名；带设备参数保留 | `device-info-service.js` / `stationIdentity`；`v35-pages.js` | 第二组展示实际名称、位置、辅助编号、有效机型与库存 ready/empty/updating；失败不展示旧资料为当前资料，无在线承诺。只对当前有效 WGS84 提供现有导航。扫码与刷新沿用真实验证服务，零／单／多订单分流未改。 |
| `print-locations.html` | `#locations`、实体别名、菜单／页脚说明链接 | 现有扫码器、device-info、station-navigation | 第二组独立新版网点页；明确附近搜索未开放，提供扫描设备二维码、当前已核实设备和我的订单入口。没有纽约设备／距离／在线列表。 |
| `how-to.html` | `#how-it-works`、实体别名，`section=steps/save/print` | `v35-pages.js`，公共原生 dialog | 第二组三步教程及操作指引弹窗，连接相册／图库／AI／保存设计／订单／扫码入口；不承诺云同步、公开发布、快递时效或扫码授权。参考没有可迁入的教程视频资源，本轮用书面操作指引，未伪造播放成功。 |
| `about.html` | `#about`、实体别名、`section=our-story` | `v35-pages.js`、`shellInfo` | 第二组双栏品牌页、原参考主图与照片卡片、故事、联系／合作说明弹窗。未核实社媒及联系资料不作为真实服务入口，未开放交易不出现提交表单。 |
| `mobile-preview.html` | 目标 `customize` 别名，保留原 query 和 hash | 现有编辑器路由适配 | 待兼容组实现，尚无该实体文件或别名，不报告为已支持。 |

## 公共导航、弹窗、事件与动态状态登记

表格按用户可达状态登记，不能用 HTML 数量替代交互覆盖。

| 能力／事件／状态 | V35 参考行为 | 当前实现／对应契约 | 本轮结果与下一验证 |
| --- | --- | --- | --- |
| 品牌、主导航、移动菜单、页脚 | 首页／作品中心／教程／关于／订单／设计／账户／网点 | `shellHeader`、`shellFooter`、hash 路由 | 第一组外壳保留，第二组作品／教程／关于／网点已接独立页面；页脚网点说明附实际页面链接。原生 dialog Escape、焦点恢复有模拟测试，仍需真实浏览器核对。 |
| 中英文、语言持久化、刷新 | 全站语言、移动按钮、桌面选择 | `simple-i18n.js`、原 `#language` change，URL lang | 本轮新文案双语，保留表单值／details 恢复；新菜单语言按钮委托原处理。不改变原状态和缓存协议。双语长文案／焦点待验。 |
| 联系、合作、AI 说明弹窗 | 联系链接／合作咨询／AI 指引，关闭、Escape | `shellInfo` + `mountShell` 原生 dialog | 本轮实现简明真实说明；无联系资料／合作申请暂未开放。未拷贝参考社交地址作为核实信息。|
| 扇形灵感、上一张／下一张 | 九图、拖拽、按钮、悬停 | 本轮 `data-shell-fan` 改变视觉索引；卡片进入原 AI 编辑入口 | 已接按钮、悬停与键盘链接；**参考拖拽与滚动联动动效待补**，不得以按钮替代宣称全部动效验收。尊重 reduced-motion。 |
| 首页相册上传、忙碌、格式／解码／容量／保存失败 | 文件选择、照片预览弹窗、替换、保存草稿、进高级编辑 | 保留 `openPhotoPicker` / `receivePhoto` / `importPhoto`，保存成功后进 `#choose` | 新视觉主按钮接旧真实上传，不引入第二份草稿协议。上传后沿用原编辑页；V35 预览弹窗、替换与草稿视图待第三组。忙碌禁用与格式通过开发测试，真实浏览器上传未验。 |
| 首屏加载、目录失败、重试、无库存／库存更新／无模板 | 加载骨架、空态／报错、机型弹窗 | 原 `loadCatalog`、`loadStockCatalog`、`reload-catalog`、`refresh-models` | 保留原失败关闭策略，不加入静态可售回退。V35 全部加载／空／错样式及浏览器负向待第三／七组。 |
| 首页图库、过滤／计数／卡片 | 作品卡片、详情、目录过滤 | `catalog.js`、`simple-core.js`；`v35-pages.js` | 第二组首页卡片进详情，详情进原编辑器。六款既有有效设计均可达，分类使用既有模板分类，不按视觉猜色；搜索／无匹配／失效详情及转义有自测。 |
| 教程弹窗、FAQ 展开、故事／关于章节 | 教程、视频、字幕、FAQ、故事 | `v35-pages.js`、`shellInfo`、原生 details | 第二组独立教程／故事和书面操作指引弹窗；FAQ 保留。没有可迁入的真实视频，故不显示虚构播放器或字幕；打印、配送和保存说明遵守当前能力。 |
| 编辑步骤、切换确认、机型品牌／搜索／选色 | `data-step`、switch-dialog、phone picker、颜色 | 原机型库存和编辑状态；后续后台颜色目录 | 本轮保留原 editor／model-first 弹窗，待第三／五组改视觉；无色必须跳过，不能固定四种色。 |
| 裁切／缩放／移动／旋转／文字／贴纸／预览 | editor、home preview、saved design | 原 `editor-model`、personalize、artwork-drag、print-export、IndexedDB | 本轮未变业务，相关既有单元自测通过；刷新定位和打印文件真实输出待浏览器及模板断言。 |
| AI 授权／提交／排队／生成／重连／成功／失败／取消／过期 | 参考定时演示 | 原 `ai-service`、ai-renders 和私有结果图 | 原服务保留，第三组迁视觉；负向禁止计时器假成功。参考首页九图明确仅灵感示例，不作为生成结果。 |
| 登录／发码／验证／过期／退出／换号／余额流水 | 任意六位数、OAuth 模拟、avatar、会员 | 原 customer API / ai-account，原私有校验 | 第三组待迁并隔离本机设计；不复制任意验证码、OAuth timer、假会员。 |
| 本机保存列表／恢复／删除／空态／身份隔离 | 参考 sessionStorage designs | 原 `simple-storage`；身份由服务端确认 | 第三组待补列表与分区；旧匿名历史草稿保留，不跨账号归属。 |
| 结算份数、价格、配送、创建／返回／刷新 | quantity 1–20，本地订单／付款模拟 | 原 checkout / orders，request_key / revision | 第六组固定新单一份、拒绝绕过；历史已付快照保留。现有规则继续执行，尚未新增单份后端契约。 |
| 订单筛选／分页／空态／加载／失败／详情 | 参考本地 order-store | 原 orders GET / orderRequest / paymentState | 现有导航可达，待第六组视觉和断言；不得新增重复创建重试。 |
| 设备二维码入口零／单／多单、无效／离线／错误 | 参考假设备／附近位置 | 原 `station-entry`、device-info、scope 校验 | 本轮未改路由和服务；相关既有单元通过，浏览器分流及真实资料展示待第二／六组。保留订单原目标设备。 |
| 手机推单／立即打印／退款取消／重复／未知超时 | 参考本地打印／完成按钮 | 原 fulfillment、confirm-print、retry-dispatch | 服务端门禁保留，第六组迁订单 UI；第二组 `#kiosk` 只读化并删除手工 start/ready/collect 事件，`device.html` 无真实身份参数时转只读说明，有身份时保留现有只读设备页，不加载旧演示 app。 |
| 打印覆盖图与颜色、历史订单快照 | 参考默认蓝色／静态 variants | 供应商绑定模板、未来颜色资源版本冻结 | 后台模型、权限／CSRF、审计、资源上传解码、初始化、公开链路均未实现，待第四／五组。 |

## 现有可达功能与深链接保留清单

- `#home` 仍为首页；`#designs`、`#how-it-works` 在第二组改为独立作品中心和教程页；`#choose?design=…`、`source=photo`、`fresh=1`、`studio=1` 参数解析保留。主相册选择成功后进入原编辑器，保留校验和私有草稿。
- `#account`、`#ai`、`#membership`、`#checkout`、`#orders`、`#payment?order=…`、`#pass`、`#kiosk?code=…` 保留可达。第二组将 kiosk 替换为只读设备指引，code 不再触发解析或本地打印；真实订单的付款／确认门禁保持原服务。
- `device_id` / `shop_id` 顶层／hash query、入站设备核实、读取当前用户订单和零／单／多单路由沿用原代码。`device.html` 带真实身份时保留现有只读资料入口，无身份的旧演示 URL 转入新版只读指引；不代表独立终端迁移或验收。
- 原图导入与存储、AI 私有结果、账户邮箱码／退出／修改昵称／余额流水、订单分页／详情、Stripe／Airwallex 支付、退款、配送草稿、设备扫码／文件准备／推单／手机立即打印／重查等原功能保持原业务入口；未迁移页面不作整站通过结论。
- 第二组已建立 works-center、work-detail、how-to、about、printers、print-locations 六个实体 `.html` 别名，保留原查询参数与章节 hash。customize、my-designs、checkout、account 及 mobile-preview 仍待后续，不静默把 404 计为成功。`mobile-preview` 必须原样携带 query/hash 交到 customize。

## 第一组开发自测与验证缺口（历史记录）

以下保留第一组证据，不替代第二组本轮验证；均为开发自测，不是独立 QA 或产品验收。

| 命令／检查 | 结果与限制 |
| --- | --- |
| `npm test` | 2026-11-14：216/216 通过，无跳过；包括原机型库存、设备分流、账户、AI、支付状态与订单服务等单元回归。不是完整浏览器链路。 |
| `node --test frontend/tests/ui-v35.test.mjs` | 5/5 通过，无跳过：相册优先与真实 handler、上传忙碌、双语／旧导航目标、现行教程／不虚构授权、本地资产存在及有效入口。仅第一组覆盖，后续必须扩展全部冻结范围。 |
| `node --check frontend/storefront/simple-app.js` / `v35-shell.js` | 通过语法检查。 |
| `git diff --check` | 无空白错误（交接前复核）。 |
| 独立无头浏览器启动探测 | 本机 Playwright 启动隔离临时 profile 的 Chrome 被当前权限环境中止，SIGABRT，日志含 kill EPERM。未请求额外权限、未使用个人浏览器会话、未绕过限制；没有产生浏览器截图或操作通过证据。 |
| 390 / 1440 逐页对照、320 主流程 | **未验证**。本轮必须交独立测试核对首页、移动菜单焦点、语言长文案、上传后真实跳转、资源加载及 overflow。后续各页仍待迁移。 |
| 其余冻结 gates | 本轮未运行 backend-contracts、migration-consistency、admin-build、whole-site-browser；未修改后端／后台。`test_phone_colors.py`、`test-ui-v35-e2e.mjs` 仍待后续功能组创建；不可把本轮两项通过当作所有 gates 通过。 |

没有读取、复制或初始化数据库、旧 direct_debug 凭证／会话，没有外部供应商、付费 AI、支付／退款或硬件调用，没有部署／推送。

## 第二组开发交接（2026-11-14，待独立测试）

- 起始 HEAD `fdfe8934340674d88010051d9f1aec053ce366d9`，分支仍为 `codex/ui-v35-migration`，开始工作区干净；参考仍是冻结基准，无差异。未自行执行 Git 暂存、提交或切分支。
- 新增 `v35-pages.js` / `v35-pages.css` 承载作品、详情、教程、关于、网点／设备及只读权益；六个实体 HTML 经 `v35-page-entry.js` 保留查询和章节参数进入有效应用，不更换服务端订单／身份／库存契约。
- 作品继续使用既有可编辑目录，首页卡片→详情→原编辑器；没有新增社区发布服务。参考的本地点赞、客户公开作品、假机型及直接创建本地订单未接入，不能宣称真实社区能力已实现。后续个人设计保持服务端身份隔离要求。
- 设备只读展示当前成功核实的数据；错误时不把缓存当已核实。无色／无库存不会在设备页虚构可售项。设备扫码按钮使用既有相机／粘贴链接与 `loadDeviceInfo`，不授权打印、不修改订单目标；本轮浏览器扫码未验。
- 参考版布局适配：作品保留紫色玻璃三列卡片／两列窄屏、大图左右分栏；教程保留三步双栏与小屏堆叠；关于保留参考主图、照片卡片和故事双栏；网点保留紫色面板风格，假位置列表改为未开放说明与已核实设备。视觉一致性仍须逐页人工截图核对，当前 CSS 不构成验收证据。
- 旧 `#membership` 仍读取实际已登录额度，显示账户与流水链接；会员购买未开放，页面不再提供演示订阅或续费按钮。未修改 AI 服务端计费／次数规则，未新增 OAuth 或头像保存表单。
- 教程不要求保存设计二维码、不承诺配送时效、云同步或公开作品发布。原参考没有视频文件，本轮提供文字指引弹窗；视频／字幕没有伪造为已实现。
- 语言参数兼容参考 `lang=zh/en`，保留原参数并解析为现有 `zh-CN/en-US`；新增页面双语渲染，不翻译作品画面或输入值。

| 开发自测 | 本轮结果与限制 |
| --- | --- |
| `npm test` | 216/216 通过，无跳过；保留既有全部断言。交接前重新执行，未触及真实渠道。 |
| `node --test frontend/tests/ui-v35.test.mjs` | 14/14 通过，无跳过；保留原 6 项并补 8 项：目录过滤／搜索／空态／转义、详情与编辑 ID、双语教程边界、真实设备数据与 WGS84、错误／空／更新／忙碌、权益只读、6 个别名参数、应用路由与旧演示移除。属于开发单元自测，不是独立 QA。 |
| 语法、素材与差异 | 新增 JS 及受影响入口语法检查；测试实际确认引用素材存在；`git diff --check` 无空白错误。 |
| 本地 HTTP 探测 | 尝试用随机独立端口且 API 指向不可用端口启动静态服务；监听探测即返回 `listen EPERM 127.0.0.1`，服务未启动，没有发出业务请求。未绕过隔离或申请提升权限。 |
| 浏览器与视觉 | 未取得 HTTP、浏览器操作或截图证据。390/1440 逐页对照、320 溢出、弹窗焦点、相机、导航和刷新恢复交测试员在可运行隔离环境验证。 |
| 全量 gates | 仍交 harness；已知 `test_phone_colors.py`、`test-ui-v35-e2e.mjs` 尚待后续功能组，前轮相关 gates 失败没有掩盖或删除。后端／后台本轮未改，未创建数据库。 |

本轮本地代码交测试，不代表部署、真机、整站通过。可复现入口仍为 `npm start` → `http://127.0.0.1:4173/`；新增 `/#designs`、`/#work?id=bloom`、`/#how-it-works`、`/#about`、`/#locations`、`/#printers` 与六个 HTML 别名。本轮环境不能监听，因此没有常驻服务或当前可访问地址的运行证据。

## 第二组 QA 回归修复开发交接（2026-11-14，待独立复验）

- 起始 HEAD `10e730b`，工作区干净；本轮只处理 QA 发现的订单状态渲染回归，不启动第三组。Git 检查点仍交 harness，不自行暂存、提交或切换分支。
- 修复前运行 `node --test frontend/tests/ui-v35.test.mjs`，复现 14 通过、1 失败，非空订单列表抛出 `ReferenceError: orderStatus is not defined`。第二组移除旧设备演示页面时误删了共用函数；`ordersPage`、`passPage`、`providerOrderPage`（包括订单收据）均仍引用该函数。
- 在 `simple-app.js` 恢复迁移前的原有 `orderStatus(status, refund)` 映射；订单状态、退款优先级、历史已完成／已领取映射保持原语义。没有改写服务端状态、金额或快照，没有修改付款／打印门禁及重试行为。
- 原 QA 非空服务端订单断言保持不变。新增开发测试覆盖待付款／已付／打印中／待取／历史完成／领取／取消／未知状态，以及退款待核实／处理中／成功／失败／未知状态；用合成不可变快照实际执行设计详情及 Stripe、Airwallex、free_test 支付页与收据渲染，检查状态转义、支付回跳不确认到账、退款和关闭状态不显示付款按钮，渲染不修改订单。
- 修复后开发自测：`npm test` **216/216**、`node --test frontend/tests/ui-v35.test.mjs` **17/17**，均无跳过；`node --check frontend/storefront/simple-app.js` 和 `git diff --check` 通过。这些是本地 Node 渲染／单元自测，未取得浏览器或视觉证据，不是独立 QA。
- 本轮没有启动本地服务、读取或修改数据库、调用外部业务、部署或真机操作。既有浏览器权限问题没有在本轮重新验证。交测试员在隔离环境复验 `#orders` 非空列表、`#pass`、`#payment?order=…`、支付返回和退款收据，并继续保留 390/1440 视觉对照与 320px 主流程验证缺口。
- 第三至第七组和全部整站验收范围仍保留。上轮 harness 的 `backend-contracts` 缺 `test_phone_colors.py`、`whole-site-browser` 缺 `test-ui-v35-e2e.mjs` 失败未在本轮修复；本轮不为消除缺失模块错误而建立空测试或占位脚本。全部冻结 gates、独立 QA 与产品复核仍待后续。

## 本地预览与后续交接

```sh
npm start
# 默认 http://127.0.0.1:4173/ ，仍由 frontend/server.mjs 提供 frontend/storefront
# 后端按项目原有说明另启；不要为预览初始化／修改既有数据。
```

此地址为可复现启动地址；本轮未常驻启动预览服务，不声称已部署或当前有进程监听。API 默认代理 `127.0.0.1:8000`；真实业务验收必须在第七组新建的隔离数据库／媒体／端口并阻断外部调用，不能使用用户旧数据库或旧 direct_debug 副本。

剩余顺序保持产品规划：第二组交独立测试（未有浏览器／视觉通过证据）；第三组账户／AI／编辑／本机设计；第四组后台颜色；第五组初始化与目录色块；第六组单份结算／订单／设备兼容；第七组隔离全链和三个指定测试的完整覆盖。独立 QA、产品逐项复核及全部 gates 均未完成。检查点版本号由 harness 后续记录，不能把提交当作验收。
