# POPOMO V35 用户端迁移对照与交接

## 基准与本轮边界

- 冻结任务：`storefront-v35-migration`，第一组已记录检查点，本轮为开发第三组（账户／AI／编辑器、本机设计及身份分区），待独立测试。整站替换尚未完成。
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
| `customize.html` | 当前 `#choose`、`#choose?design=…`、`#choose?source=photo`，AI `&studio=1` | `simple-app.js` 编辑状态、`phone-templates.js`、`print-export.js`；`GET /api/v1/store/phone-models/` | 第三组接入 V35 编辑工作区与相册入口，复用原裁切、旋转、文字、贴纸、缩放及移动；Next 改为真实机型预览，分别保存本机或进入原结算。无固定蓝色；浏览器与视觉待验。 |
| `works-center.html` | `#designs`、实体 HTML 别名；首页图库、菜单进入 | 现有 `simple-core.js` 六款可编辑设计 + `catalog.js` 标题／分类；`v35-pages.js` | 第二组接入作品卡片、分类、双语搜索、计数、无匹配空态及详情。现有 `GET /api/v1/catalog/` 提供价格／AI，并无公开客户作品接口；不把参考本地发布／点赞当服务端社区。自测见下文，浏览器待验。 |
| `work-detail.html` | `#work?id=…`，兼容参考种子 `popomo-` 前缀、实体别名 | `v35-pages.js`；现有设计 ID → `#choose?design=…` 原编辑模型 | 第二组实现大图、模板说明、返回作品中心、相关推荐和实际编辑入口；未知 ID 显示失效态，不猜其他作品。无伪造点赞／作者／机型库存／本地创建订单。 |
| `my-designs.html` | `#my-designs` 本机设计列表；旧 `#pass` 当前设计／订单保留 | `simple-storage.js` IndexedDB；服务端确认的 customer 身份用于分区 | 第三组增加列表、预览保存成功态、继续编辑、删除及空／加载／错态；按服务端身份分区，无云同步。旧无归属缓存保持原位，仅访客可主动恢复副本，不自动划入账户。Node 自测通过，浏览器待验。 |
| `checkout.html` 结算 | `#checkout` | `order-service.js`；`POST /api/v1/store/orders/`（建单）、`orders/{reference}/checkout/`（渠道结算）；服务端金额与 request_key | 保留待第六组新版结算和单份约束。配送仅草稿，禁止收款／推单。不得迁入参考 quantity 增减和定时付款。 |
| `checkout.html?view=orders` 列表 | `#orders` | `GET /api/v1/store/orders/?page=…`；`ordersPage` | 公共导航已接现有真实订单列表，列表视觉和全部状态待第六组。不能改为 sessionStorage 订单。 |
| `checkout.html` 详情 | 当前 `#pass`、`#payment?order=…` 与列表 `view-order` | `GET orders/{reference}/`、print-files、fulfillment、confirm-print、retry-dispatch；`simple-app.js` | 真实手机门禁保留；新版详情、设备信息、扫码、退款取消、未知结果提示待第六组。出货不自动领取。 |
| `checkout.html` 支付返回 | `#payment?order=…`，保留现有支付 URL 参数 | `payment-state.js`、Stripe / Airwallex 查询与渠道通知 | 保留待第六组；返回页只查询，不能写 paid。待核实／失败／关闭／退款／取消须逐项测试。 |
| `account.html` | `#account`；权益 `#membership` 保留旧深链接 | `customer-account.js`；customer/send-code、verify、customer、credits；`ai-account/` | 第三组采用 V35 双栏故事与玻璃表单，继续使用真实邮箱码、昵称、退出、余额及流水 API；切身份清空私有视图并重载对应分区。OAuth、会员购买及头像交易入口仍不显示。真实浏览器／渠道 mock 验证待验。 |
| `printers.html` | `#printers`、实体别名；带设备参数保留 | `device-info-service.js` / `stationIdentity`；`v35-pages.js` | 第二组展示实际名称、位置、辅助编号、有效机型与库存 ready/empty/updating；失败不展示旧资料为当前资料，无在线承诺。只对当前有效 WGS84 提供现有导航。扫码与刷新沿用真实验证服务，零／单／多订单分流未改。 |
| `print-locations.html` | `#locations`、实体别名、菜单／页脚说明链接 | 现有扫码器、device-info、station-navigation | 第二组独立新版网点页；明确附近搜索未开放，提供扫描设备二维码、当前已核实设备和我的订单入口。没有纽约设备／距离／在线列表。 |
| `how-to.html` | `#how-it-works`、实体别名，`section=steps/save/print` | `v35-pages.js`，公共原生 dialog | 第二组三步教程及操作指引弹窗，连接相册／图库／AI／保存设计／订单／扫码入口；不承诺云同步、公开发布、快递时效或扫码授权。参考没有可迁入的教程视频资源，本轮用书面操作指引，未伪造播放成功。 |
| `about.html` | `#about`、实体别名、`section=our-story` | `v35-pages.js`、`shellInfo` | 第二组双栏品牌页、原参考主图与照片卡片、故事、联系／合作说明弹窗。未核实社媒及联系资料不作为真实服务入口，未开放交易不出现提交表单。 |
| `mobile-preview.html` | 目标 `customize` 别名，保留原 query 和 hash | 现有编辑器路由适配 | 第三组新增实体别名，先原样保留 query/hash 重定向 customize，再由 customize 进入有效编辑器。原参数保留有 Node 自测，真实刷新导航待验。 |

## 公共导航、弹窗、事件与动态状态登记

表格按用户可达状态登记，不能用 HTML 数量替代交互覆盖。

| 能力／事件／状态 | V35 参考行为 | 当前实现／对应契约 | 本轮结果与下一验证 |
| --- | --- | --- | --- |
| 品牌、主导航、移动菜单、页脚 | 首页／作品中心／教程／关于／订单／设计／账户／网点 | `shellHeader`、`shellFooter`、hash 路由 | 第一组外壳保留，第二组作品／教程／关于／网点已接独立页面；页脚网点说明附实际页面链接。原生 dialog Escape、焦点恢复有模拟测试，仍需真实浏览器核对。 |
| 中英文、语言持久化、刷新 | 全站语言、移动按钮、桌面选择 | `simple-i18n.js`、原 `#language` change，URL lang | 本轮新文案双语，保留表单值／details 恢复；新菜单语言按钮委托原处理。不改变原状态和缓存协议。双语长文案／焦点待验。 |
| 联系、合作、AI 说明弹窗 | 联系链接／合作咨询／AI 指引，关闭、Escape | `shellInfo` + `mountShell` 原生 dialog | 本轮实现简明真实说明；无联系资料／合作申请暂未开放。未拷贝参考社交地址作为核实信息。|
| 扇形灵感、上一张／下一张 | 九图、拖拽、按钮、悬停 | 本轮 `data-shell-fan` 改变视觉索引；卡片进入原 AI 编辑入口 | 已接按钮、悬停与键盘链接；**参考拖拽与滚动联动动效待补**，不得以按钮替代宣称全部动效验收。尊重 reduced-motion。 |
| 首页相册上传、忙碌、格式／解码／容量／保存失败 | 文件选择、照片预览弹窗、替换、保存草稿、进高级编辑 | 保留 `openPhotoPicker` / `receivePhoto` / `importPhoto`，保存成功后进 `#choose` | 新视觉主按钮接旧真实上传，不引入第二份草稿协议。第三组上传后进入 V35 编辑工作区，可替换照片；机型确认后打开预览／保存弹窗，本机设计独立列表。忙碌与格式有 Node 自测，真实浏览器上传未验。 |
| 首屏加载、目录失败、重试、无库存／库存更新／无模板 | 加载骨架、空态／报错、机型弹窗 | 原 `loadCatalog`、`loadStockCatalog`、`reload-catalog`、`refresh-models` | 保留原失败关闭策略，不加入静态可售回退。V35 全部加载／空／错样式及浏览器负向待第三／七组。 |
| 首页图库、过滤／计数／卡片 | 作品卡片、详情、目录过滤 | `catalog.js`、`simple-core.js`；`v35-pages.js` | 第二组首页卡片进详情，详情进原编辑器。六款既有有效设计均可达，分类使用既有模板分类，不按视觉猜色；搜索／无匹配／失效详情及转义有自测。 |
| 教程弹窗、FAQ 展开、故事／关于章节 | 教程、视频、字幕、FAQ、故事 | `v35-pages.js`、`shellInfo`、原生 details | 第二组独立教程／故事和书面操作指引弹窗；FAQ 保留。没有可迁入的真实视频，故不显示虚构播放器或字幕；打印、配送和保存说明遵守当前能力。 |
| 编辑步骤、切换确认、机型品牌／搜索／选色 | `data-step`、switch-dialog、phone picker、颜色 | 原机型库存和编辑状态；后续后台颜色目录 | 第三组改为 V35 model-first／编辑工作区，库存与搜索契约不变；颜色仍待第五组，无色跳过，不能固定四种色。 |
| 裁切／缩放／移动／旋转／文字／贴纸／预览 | editor、home preview、saved design | 原 `editor-model`、personalize、artwork-drag、print-export、IndexedDB | 本轮未变业务，相关既有单元自测通过；刷新定位和打印文件真实输出待浏览器及模板断言。 |
| AI 授权／提交／排队／生成／重连／成功／失败／取消／过期 | 参考定时演示 | 原 `ai-service`、ai-renders 和私有结果图 | 第三组接 V35 状态面板，仍用现有服务端任务和轮询；身份失败不提交有自测，禁止计时器假成功。参考首页九图仅为灵感，不作为生成结果；完整浏览器状态待验。 |
| 登录／发码／验证／过期／退出／换号／余额流水 | 任意六位数、OAuth 模拟、avatar、会员 | 原 customer API / ai-account，原私有校验 | 第三组实现双栏账户、真实表单和本机身份分区；无效验证码、退出失败与身份变化清理有自测，浏览器及账单 mock 待验。不复制任意验证码、OAuth timer、假会员。 |
| 本机保存列表／恢复／删除／空态／身份隔离 | 参考 sessionStorage designs | 原 `simple-storage`；身份由服务端确认 | 第三组提供本机列表、恢复、删除、空／加载／错误态和命名空间分区；旧匿名历史草稿保留，仅访客显式恢复副本，不跨账号归属。真实 IndexedDB 与浏览器待验。 |
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
- 第二组已建立 works-center、work-detail、how-to、about、printers、print-locations 六个实体 `.html` 别名，保留原查询参数与章节 hash。第三组另增 customize、my-designs、account、mobile-preview 四个实体别名；checkout 实体别名仍待第六组，不静默把 404 计为成功。`mobile-preview` 必须原样携带 query/hash 交到 customize。

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

## 退款列表契约修复开发交接（2026-11-14，待独立复验）

- 起始 HEAD `a44f691`，分支 `codex/ui-v35-migration`，工作区干净；本轮只修复 QA 发现的退款列表遗漏，不启动下一功能组。Git 检查点仍由 harness 创建。
- 修复前在全新内存测试库实际复现 `test_order_list_reports_refund_status_consistently_with_detail` 失败：详情退款为 `succeeded`，列表没有 `refund`，实际 `None != 'succeeded'`。该 QA 测试及原断言完整保留。
- `StoreOrders.get` 在原有限列表字段上新增 `refund`，复用详情的 `refund_data(order)` 公开序列化；无退款返回 `null`。继续排除照片、快照、设计码、邮箱和访问凭证，不调用带有设计详情／供应商状态的整单序列化。`select_related('refund')` 一次加载关联，列表不逐单查退款、不查询外部渠道或改变退款／订单历史状态。
- 新增 `test_order_list_refunds_are_public_read_only_and_owned_without_per_order_queries`：覆盖 requested／pending／succeeded／failed 和无退款；列表与详情公开退款数据完全一致；保留原订单 `paid`，退款优先级仍由既有前端渲染处理；列表只执行一次数据库查询；不返回客服原因或渠道 ID；前后订单与退款记录不变；其他浏览器看不到订单／退款，无访问键拒绝读取。

| 开发自测 | 结果与限制 |
| --- | --- |
| 后端相关模块 | 通过 Django `call_command('test', …, interactive=False)` 执行 `management_api.test_orders`、`test_refunds`、`test_free_orders`、`test_fulfillment`、`test_stripe`、`test_airwallex`；81 项中 80 通过、1 条既有条件跳过。原 QA 回归与新增列表契约测试均通过。 |
| 隔离方式 | 进程中将默认数据库配置覆盖为全新 SQLite `:memory:`，媒体目录使用 `TemporaryDirectory`，启动前生成临时 Django／加密密钥并清除 PostgreSQL 选择环境，供应商开关关闭；测试期间 `socket.socket.connect` 被阻断。未读取／复制用户数据库、旧调试副本、旧凭证或客户照片。测试库及临时目录随结束清理，未改默认部署配置。 |
| 未执行的并发断言 | 既有 `ConcurrentRefundTests.test_two_admin_submissions_create_only_one_remote_refund` 要求 PostgreSQL 行锁，由原 `skipUnless` 在 SQLite 上跳过；本轮未修改或新增跳过逻辑，不能据此声称 PostgreSQL 并发已验证。 |
| 前端 | `npm test` 216/216、`node --test frontend/tests/ui-v35.test.mjs` 17/17，均无跳过；既有退款状态优先级、列表／设计详情／收据渲染断言保留。属于 Node 开发自测，没有实际浏览器证据。 |
| 差异与 gates | `git diff --check` 通过。未改模型，无迁移；全部固定 gates 仍交 harness。本轮未创建缺失的颜色测试或端到端脚本，既有缺口和第三至第七组范围全部保留。 |

交测试员在隔离浏览器复验同一订单的列表／详情／支付收据退款文案：已退款不再显示 Paid，待核实／处理中／失败及无退款分别正确，刷新不改变历史金额／状态、不产生渠道调用，其他浏览器不可见。390/1440 视觉与 320px 主流程仍未验证。本轮没有部署、真实收退款、供应商调用或硬件操作；修复可测试不表示整站通过。

## 第三组开发交接（2026-11-14，待独立测试）

- 起始 HEAD `8798044b3030c710bca5c4ff7e138085c4940b5f`，分支仍为 `codex/ui-v35-migration`，工作区干净；只读参考 HEAD 仍为冻结的 `5501bedb720d3e7552428b0dc75174973e87934c`，无工作区差异。未自行暂存、提交、切换分支或改 harness；检查点交执行器记录。
- `v35-workspace.css` 为账户、编辑器、AI 状态页、全屏编辑／风格弹窗及本机设计提供 V35 紫色、字体、玻璃面板、桌面左右工作区及手机堆叠样式；账户增加故事区，保留真实邮箱码、昵称、余额和流水表单。CSS 适配 760／360px；**没有逐页浏览器截图或人工视觉通过证据**，不能由 CSS 存在推出视觉一致。
- 相册仍调用 `simple-upload.js` 真实导入与解码，机型仍来自原库存和模板目录；没有静态可售回退。编辑器保留原有图层、文字、贴纸、旋转、缩放、移动、裁切、风格选择和全屏编辑的事件、数据结构及 `print-export.js`；没有改 AI 计费、数量或模板打印尺寸。
- `design-form` 先刷新库存、验证模板，再打开 `v35-designs.js` 原生预览 dialog。预览和本机保存不建订单；保存成功态在 IndexedDB 提交后显示，提供「查看我的设计」。只有用户选择「确认订单」才写独立结算草稿，仍须原服务端结算流程。再次进入结算前检查模板版本；没有在预览执行付款、推单或开印。
- 视觉业务适配：参考首页上传预览与高级编辑合入当前单一编辑模型；自动相册草稿可在未选机型时保留，**机型预览／保存列表项需要先选择可用机型**，避免以通用假机型预览代替真实模板。参考保存后「立即打印」改为「确认订单」，实际打印继续在真实订单页受门禁控制。AI 生成保留独立服务端任务状态页，不以参考定时器推进成功。
- 新增 `#my-designs` 列表（导航的「我的设计」进入此处），支持空／加载／读取错误、合成测试覆盖的保存／重开／继续编辑／删除。保存的是经过既有 pass 校验的完整设计快照及冻结预览模板；内置模板与供应商模板分开处理，恢复不携带订单／打印授权。旧 `#pass` 仍保留当前设计与订单入口，`#orders` 和支付深链接未移除。
- `design-workspace.js` 仅用当前 `ai-account/` 返回的已核实 customer ID 或已核实访客身份，给编辑状态、原图草稿、结算草稿、AI 缓存／任务和本机设计加命名空间。缓存不能确定登录、额度、到账或打印权限；服务端不可达或身份失效时清空当前私有视图并锁定本机工作区，不删除已提交的数据。身份变化后重载对应分区；本机访客草稿不会自动转给新登录账户，页面说明无云同步。
- 原无归属 `popomo-simple-v1`、`draft-photo`、旧 AI 缓存均保持原位。访客在本机设计页可主动恢复旧编辑草稿的**验证后副本**，不复制旧身份、AI 任务、付款或订单授权；已登录账户不提供该入口。原 `print-orders-v1` 仍沿用浏览器订单访问契约，服务器订单权限未修改；换身份后订单列表、详情的实际服务端访问隔离还需浏览器复核。
- 回到窗口或恢复可见时重新查询服务端身份；等待核实时阻止提交，成功的同身份读取不重建 DOM，避免原生文件选择器返回焦点导致 input 被移除、丢失上传。身份变化／失败时移除当前照片、设计列表、AI 结果、订单视图和流水；晚到的读取／排队写入／AI 结果被锁定工作区拒绝。退出请求失败也清空私有视图，不假称退出成功。AI 提交及建单前额外复核当前身份。
- 新增 `customize.html`、`my-designs.html`、`account.html`、`mobile-preview.html`，使用原 `v35-page-entry.js`。mobile-preview 首跳完整保留原 query/hash 到 customize；语言、设备、设计及章节参数继续传入有效应用。`checkout.html` 别名、新结算视觉与单份协议仍属于第六组。

| 开发自测 | 本轮证据与限制 |
| --- | --- |
| `npm test` | 216/216 通过，无跳过。保留全部既有账户、AI、库存、图层、模板导出、订单及付款状态断言；只运行本地 Node 测试，没有外部业务调用。 |
| `node --test frontend/tests/ui-v35.test.mjs` | 30/30 通过，无跳过。保留此前 18 项，新增 12 项覆盖命名空间隔离、未核实身份、旧缓存不自动归属、晚到读取和排队写入、精确图层／照片／模板保存与重开、幂等本机保存、删除、存储失败、非法照片拒绝、列表／预览双语状态与转义、四个实体别名，以及实际 app 事件的预览→本机保存→结算草稿、恢复／身份变化清理／退出失败／无效验证码／AI 身份失败不提交。 |
| 语法与差异 | 受影响 JS 用 `node --check` 检查，`git diff --check` 通过。Node VM 执行原 app 函数／事件处理器，非重写一套模拟成功逻辑；存储适配用合成内存数据，**未验证真实 IndexedDB 浏览器事务或实际图片解码**。 |
| 浏览器与最终打印 | 本轮未启动浏览器或 HTTP 服务；此前权限失败记录仍为历史记录，没有在本轮重复探测。390／1440 逐页对照、320 溢出、原生 dialog 焦点、相册文件选择／拖放／全屏、刷新定位、真实模板像素导出和身份跨标签切换均交测试员在隔离环境验证。 |
| 完整 gates | 后端／后台未改，未运行其 gates。`test_phone_colors.py` 及 `test-ui-v35-e2e.mjs` 仍待第四／第七组，harness 最近对应 gate 的缺失模块失败仍未关闭；没有空测试、占位脚本或删减断言。 |

本轮未操作任何现有数据库、客户图片、凭证、外部 AI、供应商、真实收退款、硬件或终端仓库；未推送、部署。新增入口可按 `npm start` → `http://127.0.0.1:4173/#choose`、`/#account`、`/#my-designs` 复现，但本轮没有常驻监听或可访问运行证据。下一阶段需特别验证：本机草稿刷新／删除、访客旧草稿副本、同身份重新登录恢复、换号与失效清理、上传窗口返回焦点、多标签晚到结果、AI 全生命周期 mock，以及新预览进入原结算时不重复建单。初始 IndexedDB 全面不可用的启动反馈仍需浏览器覆盖，不能以单次写入失败测试替代。

## 第三组启动存储故障修复（2026-11-14，待独立复验）

- QA 的 `ui-v35-startup.test.mjs` 原始失败断言保留；首次 `privateUpdate` 抛出存储错误不再导致未处理的初始化 Promise 拒绝。`simple-app.js` 的启动函数同时捕获订单缓存读取、结算草稿读取及后续 AI 缓存迁移失败，在安装业务监听、设备入站分流和定时轮询前停止，不以空缓存继续业务。
- `v35-startup.js` 显示中英文可恢复错误页（`role=alert`），说明允许网站存储后重新加载、不要清除既有本机数据。原生按钮自动获得焦点，只有点击才重新加载；使用原 URL／查询参数／hash 和浏览器会话，不清库、不修改身份、不自动重发业务写操作。修复没有更改默认部署配置或任何数据库。
- 开发自测：`npm test` **216/216**；`node --test frontend/tests/ui-v35.test.mjs frontend/tests/ui-v35-startup.test.mjs` **37/37**（原 V35 30 项、启动 7 项），无跳过。启动用 Node VM 执行实际 app 源码、mock 所有服务端读取，覆盖身份缓存／订单缓存／结算草稿／迁移以及身份未知时订单缓存故障，断言中英文错误状态、焦点、显式重载及没有业务事件／轮询。未修改冻结 gate、原 V35 验收测试或 harness。
- 这组证据属于开发自测，**不是真实浏览器或独立 QA 通过**。测试员需禁用 IndexedDB 后从首页及编辑深链接进入，核对错误页、键盘按钮和 320／390／1440px 布局；恢复存储后点击重新加载，验证原链接、正常初始化、已有设计恢复和身份隔离。不得通过清空浏览器数据制造恢复成功。
- 颜色与端到端脚本缺失、单份订单、整站视觉／业务验收及全部 gates 的缺口继续保留。本轮只交付这一修复组，没有浏览器启动／部署／真机证据，检查点交 harness 创建。

## 本地预览与后续交接

```sh
npm start
# 默认 http://127.0.0.1:4173/ ，仍由 frontend/server.mjs 提供 frontend/storefront
# 后端按项目原有说明另启；不要为预览初始化／修改既有数据。
```

此地址为可复现启动地址；本轮未常驻启动预览服务，不声称已部署或当前有进程监听。API 默认代理 `127.0.0.1:8000`；真实业务验收必须在第七组新建的隔离数据库／媒体／端口并阻断外部调用，不能使用用户旧数据库或旧 direct_debug 副本。

剩余顺序保持产品规划：第三组交独立测试（前两组浏览器／视觉缺口继续保留）；第四组后台颜色；第五组初始化与目录色块；第六组单份结算／订单／设备兼容；第七组隔离全链和三个指定测试的完整覆盖。独立 QA、产品逐项复核及全部 gates 均未完成。检查点版本号由 harness 后续记录，不能把提交当作验收。
