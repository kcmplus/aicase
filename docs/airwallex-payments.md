# Airwallex 手机壳支付

接入用户端 `simple-app.js` 的一次性手机壳订单，复用现有订单和 USD 定价。采用 PaymentIntent + Airwallex.js 托管收银台，卡号和 3DS 验证由 Airwallex 处理。Stripe 保留；当前每次启用一个渠道用于新订单，不提供顾客同时选择两个渠道的界面。

## 配置与本地联调

1. 运行 `backend/.venv/bin/python backend/manage.py migrate`，构建后台 `npm run build:admin`，启动前后端。
2. 超级管理员进入 `/admin/payments/airwallex`（侧栏「支付配置」→ Airwallex）。默认关闭，不会自行发起扣款。
3. 在 Airwallex Sandbox 账号激活 Payments 及至少一种支持 USD 的付款方式。Developer → API keys 获取 Client ID、API Key，按最小权限允许创建和查询 PaymentIntent。
4. 填写顾客访问的 **HTTPS 网站根地址**，无子路径、查询参数或 hash。开发时使用 HTTPS 测试域名，将同一域名的 `/api/` 转发到本地后端，配置 `DJANGO_ALLOWED_HOSTS` 和 `DJANGO_CSRF_TRUSTED_ORIGINS`。从这个 HTTPS 域名开始下单，不能在 `127.0.0.1` 下单再返回另一个域名：浏览器订单访问凭据按域名保存。
5. Developer → Webhooks 新建公网 HTTPS 接收地址 `https://你的域名/api/v1/payments/airwallex/webhook/`，订阅 `payment_intent.succeeded`、`payment_intent.cancelled`，将该订阅的签名密钥填入相同环境。事件使用 `name`、`data.object` 结构，正式启用前核对所选 API 版本的样例；不接受测试请求头传入的签名密钥。
6. 保存并启用 Sandbox 测试配置。此操作原子关闭 Stripe 的新订单开关，旧 Stripe 订单不变。两渠道都关闭时沿用项目原有演示付款。
7. 在用户端完成测试订单，检查后台「打印订单」中的渠道、PaymentIntent 编号和付款时间，再配置独立的正式环境凭据。

凭据沿用项目 `AI_CONFIG_ENCRYPTION_KEY` 加密存储机制，生产环境必须稳定配置并安全备份该密钥。GET 配置只返回末四位，不回显凭据；保存时留空表示保留，勾选清除才清除。测试和正式环境不会互用 API Token。

保存配置只检查完整性，不代表 Airwallex 商户权限、收款能力或密钥已经通过在线验证。不要将真实密钥提交到仓库、测试脚本或日志。

## 接口

| 接口 | 用途 |
| --- | --- |
| `GET/PATCH /api/v1/admin/airwallex/` | 超级管理员配置，写入需 CSRF 和 revision |
| `GET /api/v1/store/payment-config/` | 当前新订单渠道、环境、配置是否齐全 |
| `POST /api/v1/store/orders/` | `payment_provider=airwallex`、`payment_mode=test/live`，按服务端价格创建待付款订单 |
| `POST /api/v1/store/orders/{reference}/checkout/` | 校验浏览器所有权；创建或复用 PaymentIntent，返回短期收银台参数 |
| `POST /api/v1/payments/airwallex/webhook/` | Airwallex 签名通知，成功处理返回 200 |

后端使用 Sandbox `https://api.sandbox.airwallex.com` 或正式 `https://api.airwallex.com`，登录获取 Token 后创建 `/api/v1/pa/payment_intents/create`。前端仅在付款时加载官方 `https://static.airwallex.com/components/sdk/v1/index.js`，调用 `payments.redirectToCheckout()`。如果部署有 CSP，请按 Airwallex 官方域名要求配置放行。

订单的 `client_secret` 只在该订单的受保护收银台响应中短暂返回，不放入订单列表、日志或浏览器持久化设计数据。用户原图、打印图和订单访问密钥不会发给支付渠道。

## 状态与重试

- 金额、币种、商户订单号、返回地址由后台确定，前端金额只用于确认价格未变化；当前产品最低在线支付金额为 USD 0.50。
- 新订单冻结渠道、环境、凭据和返回地址；后台切换渠道或替换凭据不改变旧单。旧凭据若在 Airwallex 被撤销，需要另行处理这些待付款单；更换 webhook 签名密钥前应结清/核对旧单。
- 同一订单始终使用同一个 UUID `request_id`。已取得 PaymentIntent 时查询并复用；创建响应丢失后重试相同请求；收到 `duplicate_request` 时按商户订单号找回原 Intent。未取得 Intent 的订单超过本地 23 小时创建期限后停止创建，先核对是否已有付款，不自动生成第二笔 Intent。
- 返回页面、SDK 成功返回和浏览器的 `result=success` 都不能修改付款状态。回调验证原始请求体的 HMAC-SHA256（毫秒时间戳 + 请求体），校验 5 分钟时间窗口、金额、币种、订单关联及 Intent 编号，再使用该订单原账号和环境查询真实状态。
- 只有服务端查到 `SUCCEEDED` 且 `captured_amount` 等于订单全额才标为已付款。处理中、风控审核、待捕获、单次付款失败均不会发放打印权限；单次失败可在同一 Intent 下重试。`CANCELLED` 只关闭未付款单。重复/乱序回调不会重复记账或将已付款单降级。
- 回调依赖查询 Airwallex API；查询失败返回 503，等待平台重试。生产环境监控回调失败、长期 pending 和重试积压；手工补发 webhook 以平台当前签名为准。
- 当前没有自动定时查单补偿；用户刷新只查询本地订单状态。回调长期失败需在 Airwallex 管理台核对并重新投递，不能依据前端返回页手工猜测到账。
- 已付款订单不能走模拟退款、修改设计或演示打印。真实打印下发、退款、拒付处理、AI 订阅支付仍属于后续范围。

## 上线前验收

已加入自动化接口/前端测试；测试中模拟 Airwallex 响应，并非商户 Sandbox 实际交易。配置真实 Sandbox 凭据后仍须执行：

- 成功付款、失败后重试、3DS、关闭收银台后继续付款；确认支付方式是否自动捕获。
- HTTPS 返回同一站点后可查看原订单，异步成功回调最终置为已付款。
- 重复回调、延迟/乱序、断网重试、错误签名和金额不匹配；核对实际只存在一个 Intent。
- 渠道切换及测试/正式环境隔离；旧单继续按原渠道支付。
- 生产账号激活、正式付款方式及最小额、回调订阅版本、签名密钥轮换方案、监控和对账。

官方依据：[首次支付接入](https://www.airwallex.com/docs/payments/get-started/quickstart)、[PaymentIntents API](https://www.airwallex.com/docs/api/payments/payment_intents)、[回调验签](https://www.airwallex.com/docs/developer-tools/webhooks/listen-for-webhook-events)。

## dev 测试站

本次测试域名为 `https://aicase.chunpat.cc`。

- 顾客入口：`https://aicase.chunpat.cc/`
- 后台配置：`https://aicase.chunpat.cc/admin/payments/airwallex`
- 网站根地址：`https://aicase.chunpat.cc/`
- Airwallex 通知链接：`https://aicase.chunpat.cc/api/v1/payments/airwallex/webhook/`
- 事件：`payment_intent.succeeded`、`payment_intent.cancelled`。

dev 的数据库及加密密钥独立；部署不复制本机保存的支付凭据，也不自动启用正式收款。需要在服务器后台填写正式账号凭据、该通知链接的签名密钥及网站地址，再启用。

C 端确认页显示当前支付渠道和测试/正式模式。下单后显示打开收银台进度，失败可在同一订单继续付款；从收银台成功返回后仅显示“确认付款中”，等待后台状态，不显示重复付款按钮。待付款页面自动查询本地订单约 30 秒，超时或异常可手动刷新，已付状态及后续打印状态继续显示订单凭证。“我的订单”提供待付款单的继续支付入口。
