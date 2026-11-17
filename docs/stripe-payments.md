# 手机壳 Stripe 支付

实现范围是当前首页使用的 `simple-app.js` 手机壳订单。使用 Stripe 托管 Checkout，一次购买一个手机壳，USD 定价，信用卡付款。AI 订阅、历史展示站购物车、真实打印设备和物流不在此接入范围。后台整单原路退款参见 [退款操作](payment-refunds.md)。

## 注册账号后配置

1. 安装新增后端依赖并执行迁移：
   ```sh
   backend/.venv/bin/pip install -r backend/requirements.txt
   backend/.venv/bin/python backend/manage.py migrate
   npm run build:admin
   ```
2. 超级管理员打开后台 **支付配置 → Stripe**（`/admin/payments/stripe`）。默认关闭，保留已有演示订单流程。
3. 填写顾客访问的用户端根地址，例如 `https://shop.example.com/`。必须与顾客使用的网站一致，浏览器订单访问密钥保存在该站点。本机测试可用 `http://localhost:4173/`。
4. 从 Stripe 测试环境复制 Secret Key（`sk_test_…`）；在 Stripe Workbench → Webhooks 创建当前账号的事件接收地址：
   ```text
   https://shop.example.com/api/v1/payments/stripe/webhook/
   ```
5. 订阅以下事件，填写该接收地址的 Webhook 签名密钥（`whsec_…`）：
   - `checkout.session.completed`
   - `checkout.session.async_payment_succeeded`
   - `checkout.session.async_payment_failed`
   - `checkout.session.expired`
   - `refund.created`
   - `refund.updated`
   - `refund.failed`
6. 选择测试环境，启用并保存。前台确认壳单会跳转 Stripe；测试后返回并等待订单显示已付款。
7. 账号可正式收款后，另填正式环境 `sk_live_…` 和正式 Webhook 签名密钥，再选择正式收款保存。测试与正式配置分开保存。托管 Checkout 不需要 Publishable Key、预建 Product 或 Price。

价格读取后台「价格与套餐」中的启用单次打印套餐，至少 USD 0.50。创建订单时由服务端核价、冻结金额，禁用自动换币，不接受客户端传来的付款成功状态。

本机转发示例（Stripe CLI 登录到你的测试账号后）：

```sh
stripe listen --events checkout.session.completed,checkout.session.async_payment_succeeded,checkout.session.async_payment_failed,checkout.session.expired,refund.created,refund.updated,refund.failed --forward-to localhost:8000/api/v1/payments/stripe/webhook/
```

使用 CLI 输出的签名密钥填写后台测试配置，再通过网站创建一笔订单。CLI 通用示例事件不含本网站订单标识，不能代替完整下单测试。

## 订单行为

- 前台先创建 `pending` 订单，再为该订单申请 Checkout URL；返回或关闭收银台不标记已付款。
- 成功返回页轮询本网站订单约 30 秒，之后可手动刷新；「我的订单」可继续未完成付款。
- 一个订单固定一个 Checkout Session 和幂等键；网络超时重试不会重新创建订单或换一个收款请求。订单创建 24 小时后链接失效，须创建新订单；未拿到 Session 的旧订单在最后 30 分钟停止重试创建。
- 验证 Stripe 原始请求签名、订单引用、Session、币种、总金额、测试/正式环境及 `payment_status=paid` 后才记账。重复或乱序通知不会重复到账或让已付款订单倒退。
- 开关和模式仅影响新订单。旧订单保留加密付款凭据快照与返回地址，切换配置不会串用新模式。撤销旧 Stripe API Key 可能使该 Key 下尚未创建 Checkout 的订单无法继续；旧签名密钥用于验证原订单通知。
- Stripe 订单设计创建后锁定。订单详情显示 Stripe Session、PaymentIntent 与付款时间。Stripe 正式与测试订单均不能进入原有模拟打印、取消退款流程；实际履约需另行接入。
- 订单归属继续使用 `X-Order-Key`，不是登录账号。不要清除浏览器站点数据；不同设备或域名不能自动恢复订单。未增加跨设备订单找回。

## 密钥与部署

复用已有 `AI_CONFIG_ENCRYPTION_KEY`（Fernet 主密钥）加密支付配置及订单的凭据快照。开发环境自动使用现有本机密钥，生产需通过环境提供主密钥并与数据库一起安全备份；不要替换或丢失它。Stripe Secret Key 和签名密钥在后台录入，API 不返回明文，也不写入审计正文。

后端升级需要安装 Stripe SDK 及迁移 `0009`，前台静态文件和后台构建需一起更新。回调路径必须公开转发到 Django，保留请求原始字节和 `Stripe-Signature` 请求头；不要对这个端点添加管理员登录或会话 CSRF。服务端需能访问 `api.stripe.com:443`。

目前本地通过模拟 Stripe API 响应、真实 SDK 签名验证和页面检查验证；未配置真实账号，尚未完成 Stripe Sandbox 端到端付款验收。上线前应验证：测试成功付款、收银台返回、刷新重试、Webhook 重发、卡片拒绝、Session 过期、正式与测试配置隔离。

参考：[Stripe Checkout Session](https://docs.stripe.com/api/checkout/sessions/create)、[幂等请求](https://docs.stripe.com/api/idempotent_requests)、[Webhook 验签](https://docs.stripe.com/events/manage-webhook-endpoints#signature-errors)。

## 与 Airwallex 共存

启用 Stripe 会原子关闭 Airwallex 的新订单开关；启用 Airwallex 反之。已有订单保留原渠道和环境，不跟随配置切换。两个渠道都关闭时才使用原有演示付款。详见 [Airwallex 接入说明](airwallex-payments.md)。
