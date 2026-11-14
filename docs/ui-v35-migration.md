# POPOMO V35 用户端迁移对照与交接

## 基准与本轮边界

- 冻结任务：`storefront-v35-migration`，本轮为开发第一组（公共外壳、首页、导航、迁移登记），待独立测试。整站替换尚未完成。
- 2026-11-14 开始核对：本仓库分支 `codex/ui-v35-migration`，起始 HEAD `d5725f326f84b80c4aff7386930ac1a76d606fc1`，工作区干净。Git 检查点由 harness 创建，开发没有暂存、提交或切换分支。
- 只读参考 `../popomo-ui/dist`，HEAD 为 `5501bedb720d3e7552428b0dc75174973e87934c`，与冻结基准一致，无工作区差异；共 12 个 HTML。未修改参考仓库、历史 `sites/` 或终端仓库。
- 有效入口仍是 `frontend/storefront/index.html` → `simple-app.js`，新公共展示在 `v35-shell.js` / `v35-shell.css`；复用原业务服务，未引入参考版模拟订单、身份和付款脚本。
- `assets/v35/` 为该提交的 DM Sans 字体、背景、教程封面、AI 封面与九张灵感静态图；仅作公共设计示例，不含客户图片，不宣称是实际生成结果或可售机型。
- 状态用语：**本轮实现**仅表示代码已接入且完成所列开发自测；**保留待迁移**表示旧业务页面还在正常入口，不表示新版验收通过；**待实现**必须在后续功能组完成，不能把主流程改称未开放。

## 参考页面与有效入口

下表逐一列出全部参考 HTML。路径以 `frontend/storefront/` 为根；所有未列浏览器证据的项均未完成浏览器验证。

| 参考页面 | 当前／目标用户入口 | 后端契约及实现位置 | 本轮处理、差异与证据 |
| --- | --- | --- | --- |
| `index.html` | `/`、`#home`；相册主按钮、图库次入口、AI 入口 | 上传 `simple-upload.js`；库存 `stock-catalog.js`；价格 `runtime-catalog.js`；设备入口 `station-entry.js` | 本轮实现 V35 紫色背景、字体、玻璃导航、扇形灵感、故事区、图库区、AI 引导、FAQ、现行教程。复用 `home-photo` / `receivePhoto`，真实业务服务没有替换成参考模拟。证据：`ui-v35.test.mjs` 5 项；浏览器待验。 |
| `customize.html` | 当前 `#choose`、`#choose?design=…`、`#choose?source=photo`，AI `&studio=1` | `simple-app.js` 编辑状态、`phone-templates.js`、`print-export.js`；`GET /api/v1/store/phone-models/` | 保留待第三组迁移。机型、底图、图层、裁切、旋转、文字、贴纸、预览均需保留；不能照搬默认蓝色。 |
| `works-center.html` | 当前首页 `#designs`；目标作品中心页、过滤和作品详情 | `catalog.js`、`runtime-catalog.js`；`GET /api/v1/catalog/` | 首页实际图库入口保留，当前图库卡片进入真实编辑。作品中心独立 V35 页、过滤、动态状态待第二组。 |
| `work-detail.html` | 目标作品详情；当前图库卡片 `#choose?design=…` | 现有 `catalog.js`、有效作品模型；不能使用参考本地社交身份模拟 | 待第二组建立详情页和返回链路；使用作品设计入口必须接原编辑模型。点赞、分享等按现有实际能力逐项接入，不伪造服务端成功。 |
| `my-designs.html` | 当前 `#pass` 为当前已保存设计；目标我的设计列表／详情 | `simple-storage.js` IndexedDB；服务端确认的 customer 身份用于分区 | 当前保存与订单详情保留，完整本机设计列表、恢复、删除、身份隔离待第三组。文案必须说明本机保存，无云同步承诺。旧无归属缓存不自动归入账户。 |
| `checkout.html` 结算 | `#checkout` | `order-service.js`；`POST /api/v1/store/orders/`（建单）、`orders/{reference}/checkout/`（渠道结算）；服务端金额与 request_key | 保留待第六组新版结算和单份约束。配送仅草稿，禁止收款／推单。不得迁入参考 quantity 增减和定时付款。 |
| `checkout.html?view=orders` 列表 | `#orders` | `GET /api/v1/store/orders/?page=…`；`ordersPage` | 公共导航已接现有真实订单列表，列表视觉和全部状态待第六组。不能改为 sessionStorage 订单。 |
| `checkout.html` 详情 | 当前 `#pass`、`#payment?order=…` 与列表 `view-order` | `GET orders/{reference}/`、print-files、fulfillment、confirm-print、retry-dispatch；`simple-app.js` | 真实手机门禁保留；新版详情、设备信息、扫码、退款取消、未知结果提示待第六组。出货不自动领取。 |
| `checkout.html` 支付返回 | `#payment?order=…`，保留现有支付 URL 参数 | `payment-state.js`、Stripe / Airwallex 查询与渠道通知 | 保留待第六组；返回页只查询，不能写 paid。待核实／失败／关闭／退款／取消须逐项测试。 |
| `account.html` | `#account`；权益 `#membership` 保留旧深链接 | `customer-account.js`；customer/send-code、verify、customer、credits；`ai-account/` | 公共账户入口接现有 API 页面，V35 表单、退出／失效／余额流水待第三组。未接 OAuth、会员购买、头像修改不出现可提交入口；本轮未复制参考模拟实现。 |
| `printers.html` | 目标已核实设备详情；现有带 `device_id` / `shop_id` 的根入口、订单设备区及 `device.html` | `device-info-service.js`、`station-entry.js`、`stationIdentity`；实际设备数据 | 保留原入站验证／零单单单多单路由，首页无订单分流时展示现有设备资料。专页视觉和旧演示入口只读化待第二／六组。 |
| `print-locations.html` | 当前菜单／页脚「打印网点」说明弹窗；目标独立网点页 | 设备详情／`station-navigation.js`，仅已确认 WGS84 可导航 | 产品已决定附近搜索未开放。当前弹窗明确说明和扫描设备屏二维码指引，无纽约假设备、距离或在线承诺。新版网点页和可操作扫码入口待第二组。 |
| `how-to.html` | 当前 `#how-it-works`（首页教程）；目标独立教程及 `#steps` 等锚点 | 当前 `homePresentation`；无后端写入 | 本轮首页教程改为照片→订单确认→手机扫描设备二维码并确认推单／立即打印。独立 V35 教程／视频弹窗待第二组，禁止保存设计二维码说明和虚假配送时效。 |
| `about.html` | 当前导航「关于 POPOMO」说明弹窗；目标独立关于页／故事锚点 | `shellInfo`，无后端写入 | 当前仅真实品牌说明和回首页入口；整页内容／故事／社交入口待第二组。联系资料暂未提供，不编造联系方式。 |
| `mobile-preview.html` | 目标 `customize` 别名，保留原 query 和 hash | 现有编辑器路由适配 | 待兼容组实现，尚无该实体文件或别名，不报告为已支持。 |

## 公共导航、弹窗、事件与动态状态登记

表格按用户可达状态登记，不能用 HTML 数量替代交互覆盖。

| 能力／事件／状态 | V35 参考行为 | 当前实现／对应契约 | 本轮结果与下一验证 |
| --- | --- | --- | --- |
| 品牌、主导航、移动菜单、页脚 | 首页／作品中心／教程子菜单／AI 说明／关于及合作／订单／设计／账户 | `shellHeader`、`shellFooter`、原 hash 路由 | 本轮实现，保留可用旧入口；未迁独立页临时使用明确说明或首页章节，不标为整页完成。移动菜单原生 dialog，Escape、焦点圈定、关闭恢复需浏览器核对。 |
| 中英文、语言持久化、刷新 | 全站语言、移动按钮、桌面选择 | `simple-i18n.js`、原 `#language` change，URL lang | 本轮新文案双语，保留表单值／details 恢复；新菜单语言按钮委托原处理。不改变原状态和缓存协议。双语长文案／焦点待验。 |
| 联系、合作、AI 说明弹窗 | 联系链接／合作咨询／AI 指引，关闭、Escape | `shellInfo` + `mountShell` 原生 dialog | 本轮实现简明真实说明；无联系资料／合作申请暂未开放。未拷贝参考社交地址作为核实信息。|
| 扇形灵感、上一张／下一张 | 九图、拖拽、按钮、悬停 | 本轮 `data-shell-fan` 改变视觉索引；卡片进入原 AI 编辑入口 | 已接按钮、悬停与键盘链接；**参考拖拽与滚动联动动效待补**，不得以按钮替代宣称全部动效验收。尊重 reduced-motion。 |
| 首页相册上传、忙碌、格式／解码／容量／保存失败 | 文件选择、照片预览弹窗、替换、保存草稿、进高级编辑 | 保留 `openPhotoPicker` / `receivePhoto` / `importPhoto`，保存成功后进 `#choose` | 新视觉主按钮接旧真实上传，不引入第二份草稿协议。上传后沿用原编辑页；V35 预览弹窗、替换与草稿视图待第三组。忙碌禁用与格式通过开发测试，真实浏览器上传未验。 |
| 首屏加载、目录失败、重试、无库存／库存更新／无模板 | 加载骨架、空态／报错、机型弹窗 | 原 `loadCatalog`、`loadStockCatalog`、`reload-catalog`、`refresh-models` | 保留原失败关闭策略，不加入静态可售回退。V35 全部加载／空／错样式及浏览器负向待第三／七组。 |
| 首页图库、过滤／计数／卡片 | all、色彩、简约、治愈，作品卡片 | 原目录与 `data-start-design`，跳 `#choose?design=…` | 保留真实图库卡片，入口／相册互不替代。过滤／独立详情／无匹配空态待第二组。 |
| 教程弹窗、FAQ 展开、故事／关于章节 | 教程视频播放、字幕、三个 FAQ、故事锚点 | 本轮首页 `#how-it-works` 和原生 details | FAQ 双语、教程无过时业务承诺。独立教程、视频、字幕待第二组，不声称已全部迁移。 |
| 编辑步骤、切换确认、机型品牌／搜索／选色 | `data-step`、switch-dialog、phone picker、颜色 | 原机型库存和编辑状态；后续后台颜色目录 | 本轮保留原 editor／model-first 弹窗，待第三／五组改视觉；无色必须跳过，不能固定四种色。 |
| 裁切／缩放／移动／旋转／文字／贴纸／预览 | editor、home preview、saved design | 原 `editor-model`、personalize、artwork-drag、print-export、IndexedDB | 本轮未变业务，相关既有单元自测通过；刷新定位和打印文件真实输出待浏览器及模板断言。 |
| AI 授权／提交／排队／生成／重连／成功／失败／取消／过期 | 参考定时演示 | 原 `ai-service`、ai-renders 和私有结果图 | 原服务保留，第三组迁视觉；负向禁止计时器假成功。参考首页九图明确仅灵感示例，不作为生成结果。 |
| 登录／发码／验证／过期／退出／换号／余额流水 | 任意六位数、OAuth 模拟、avatar、会员 | 原 customer API / ai-account，原私有校验 | 第三组待迁并隔离本机设计；不复制任意验证码、OAuth timer、假会员。 |
| 本机保存列表／恢复／删除／空态／身份隔离 | 参考 sessionStorage designs | 原 `simple-storage`；身份由服务端确认 | 第三组待补列表与分区；旧匿名历史草稿保留，不跨账号归属。 |
| 结算份数、价格、配送、创建／返回／刷新 | quantity 1–20，本地订单／付款模拟 | 原 checkout / orders，request_key / revision | 第六组固定新单一份、拒绝绕过；历史已付快照保留。现有规则继续执行，尚未新增单份后端契约。 |
| 订单筛选／分页／空态／加载／失败／详情 | 参考本地 order-store | 原 orders GET / orderRequest / paymentState | 现有导航可达，待第六组视觉和断言；不得新增重复创建重试。 |
| 设备二维码入口零／单／多单、无效／离线／错误 | 参考假设备／附近位置 | 原 `station-entry`、device-info、scope 校验 | 本轮未改路由和服务；相关既有单元通过，浏览器分流及真实资料展示待第二／六组。保留订单原目标设备。 |
| 手机推单／立即打印／退款取消／重复／未知超时 | 参考本地打印／完成按钮 | 原 fulfillment、confirm-print、retry-dispatch | 原服务门禁保留，第六组迁 UI；旧 `#kiosk` / device demo 深链接待只读化，不能照旧宣称生产打印。 |
| 打印覆盖图与颜色、历史订单快照 | 参考默认蓝色／静态 variants | 供应商绑定模板、未来颜色资源版本冻结 | 后台模型、权限／CSRF、审计、资源上传解码、初始化、公开链路均未实现，待第四／五组。 |

## 现有可达功能与深链接保留清单

- 现有 `#home`、`#designs`、`#how-it-works` 仍定位首页及章节；`#choose?design=…`、`source=photo`、`fresh=1`、`studio=1` 参数解析保留。主相册选择成功后进入原编辑器，保留校验和私有草稿。
- `#account`、`#ai`、`#membership`、`#checkout`、`#orders`、`#payment?order=…`、`#pass`、`#kiosk?code=…` 的原 navigate 和 render 业务没有删除。旧演示 kiosk 本轮从公共页脚移除，但旧深链接尚需后续替换为只读说明，不能作为真打印。
- `device_id` / `shop_id` 顶层／hash query、入站设备核实、读取当前用户订单和零／单／多单路由沿用原代码。`device.html` 未改，不代表终端迁移或验收。
- 原图导入与存储、AI 私有结果、账户邮箱码／退出／修改昵称／余额流水、订单分页／详情、Stripe／Airwallex 支付、退款、配送草稿、设备扫码／文件准备／推单／手机立即打印／重查等原功能保持原业务入口；未迁移页面不作整站通过结论。
- 所有实体 `.html` 新版别名和参数兼容尚待后续，不静默把 404 计为成功。`mobile-preview` 必须原样携带 query/hash 交到 customize。

## 开发自测与验证缺口

本轮只做开发自测，不是独立 QA，也不是产品验收。

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

## 本地预览与后续交接

```sh
npm start
# 默认 http://127.0.0.1:4173/ ，仍由 frontend/server.mjs 提供 frontend/storefront
# 后端按项目原有说明另启；不要为预览初始化／修改既有数据。
```

此地址为可复现启动地址；本轮未常驻启动预览服务，不声称已部署或当前有进程监听。API 默认代理 `127.0.0.1:8000`；真实业务验收必须在第七组新建的隔离数据库／媒体／端口并阻断外部调用，不能使用用户旧数据库或旧 direct_debug 副本。

剩余顺序保持产品规划：第二组作品／教程／关于／设备及公共弹窗；第三组账户／AI／编辑／本机设计；第四组后台颜色；第五组初始化与目录色块；第六组单份结算／订单／设备兼容；第七组隔离全链和三个指定测试的完整覆盖。独立 QA、产品逐项复核及全部 gates 均未完成。检查点版本号由 harness 后续记录，不能把提交当作验收。
