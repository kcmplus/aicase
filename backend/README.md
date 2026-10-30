# Python 后端

Django 5.2 LTS + Django REST Framework 3.16。完整版本锁定于 `requirements.txt`，上游更新范围在 `requirements.in`。开发 SQLite，部署可切换 PostgreSQL。所有时间使用带时区字段。

从项目根目录执行：

```sh
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/python backend/manage.py migrate
backend/.venv/bin/python backend/manage.py seed_catalog
backend/.venv/bin/python backend/manage.py createsuperuser
npm run backend
```

配置通过进程环境传入，`.env` 不会自动加载。开发默认仅允许 localhost / 127.0.0.1，监听回环地址。开发 SECRET_KEY 自动生成到 `.local-secret`，不可提交。生产必须设置 `DJANGO_DEBUG=0`、独立的 SECRET_KEY、ALLOWED_HOSTS 和 CSRF_TRUSTED_ORIGINS；使用服务管理器加载 `.env`。如设置 `POSTGRES_DB`，还必须提供相应数据库用户和密码。

`seed_catalog` 导入现有 6 个设计、24 个素材、5 个机型、2 个品牌、3 个 AI 风格、4 组原图案例及 12 个效果、2 个套餐。再次运行不会覆盖已有记录与角色权限。已有二维码的 `legacy_index` 不可由 API 修改；关联旧二维码的机型名称和设计标识不可改写，也不能删除，可以停用。`print_ready` 默认 false，防止将示意壳型当作已校准的打印模板。

## 接口

- `GET /api/health/`：服务健康状态。
- `GET /api/v1/auth/csrf/`：获得 CSRF token。
- `POST /api/v1/auth/login/`：登录并更新 CSRF token。
- `GET /api/v1/auth/session/`：当前管理员、角色、权限。
- `DELETE /api/v1/auth/session/`：退出登录。
- `POST /api/v1/auth/password/`：凭当前密码修改本人密码。
- `GET /api/v1/admin/dashboard/`：按权限过滤的统计。
- `/api/v1/admin/brands/`、`phone-models/`、`designs/`、`graphics/`、`ai-styles/`、`ai-examples/`、`plans/`：CRUD，支持 search、page、ordering；目录数据支持 active，机型支持 brand。
- `/api/v1/admin/users/`：账号查询、新增、编辑、停用。不提供删除账号或提升超级管理员接口。
- `/api/v1/admin/roles/`：角色和模型权限。角色仍有关联账号时不可删除。
- `GET /api/v1/admin/permissions/`：权限清单。
- `GET/PATCH /api/v1/admin/ai-service/`：仅超级管理员查看及更新生图服务配置；不回传完整密钥。PATCH 要求 `revision`，支持 `provider: openai/ai778`，两家分别保存模型与加密 Key；空密钥保留当前服务商已有值，`clear_api_key: true` 显式清除。升级执行迁移 `0011_ai_relay_provider`，见 [配置说明](../docs/ai-service-config.md)。
- `POST /api/v1/admin/ai-service/check/`：检查已保存密钥是否可读取所选模型信息；要求 `revision`，每用户每进程每分钟最多 6 次，不生成图片。
- `POST /api/v1/admin/uploads/`：multipart file。10 MB / 2000 万像素上限，仅 JPG / PNG / WebP，解码后转 PNG、删除元数据、最长边 2400，生成随机文件名。不是生产原图存储服务。
- `/api/v1/admin/orders/`：分页、搜索、status 筛选；详情含私有设计快照，列表不含图像。PATCH 仅更新客服 notes。
- `GET /api/v1/admin/audit-logs/`：只读审计日志。
- `GET /api/v1/catalog/`：公开启用目录，排除隐藏品牌下机型，不返回 AI 私有提示词或管理身份信息。v2 增加 `ai_examples`，只返回启用案例与启用风格的效果；用户端读取价格、次数、风格和案例。

所有管理员 API 均需有效 staff 会话。Session Cookie 为 HttpOnly；写操作要求 CSRF，生产 Secure Cookie。使用同源反向代理，不开放通配 CORS。列表 GET 也要求对应 view 权限。账号/角色写操作额外要求超级管理员身份，即便普通角色具有 auth.change_user 等权限也不能授权。权限变更下一次请求生效。菜单和按钮只是辅助，授权判断在后端执行。

登录限流为每 IP 每分钟 10 次（DRF 内存缓存，单进程）。部署模板另有 Nginx 共享登录限流；多实例部署需要共享缓存/网关与更完整登录保护。测试环境已按该代理方案部署，数据库与 Gunicorn 只监听回环地址。

图片上传目录 `media/` 属于公开图库素材，不用于私有用户照片。暂不自动清理未引用文件，避免误删。审计记录保存操作者、动作、对象和字段名，不保存密码、请求正文或订单图像；日志不可由 API 改写，但数据库管理员仍可操作底层库，尚未做外部防篡改归档。

运行 `npm run test:backend` 验证权限、会话/CSRF、限流、CRUD、引用保护、种子幂等、图片校验、订单只读状态及审计。测试使用临时数据库和临时上传目录。

## 测试环境运行情况

管理后台：https://aicase.dinglh.cn/admin/ 。Python 3.11 + Gunicorn + PostgreSQL 16，运行配置、备份与回滚见 `../deploy/test-server/README.md`。`DJANGO_MEDIA_ROOT` 指向独立的 `/var/lib/aicase/media`，上传文件和目录显式设置公开素材所需的只读权限，不依赖服务进程 umask。部署环境不会读取本地 SQLite 或本地管理员密码。

## 案例与价格同步

案例与提示词现在合并在 `/admin/ai-prompts`。`ai-examples` 每个 `results` 项支持 `prompt`（完整提示词，最多 8000 字符）和可空 `phone_model`；管理响应返回机型名称。案例 PATCH 可提交 `revision` 做并发冲突检查。旧客户端省略新字段时保留同风格的已有值；显式 `prompt: ''` / `phone_model: null` 才清除。公开目录不返回提示词或内部机型关联。迁移 0006 后运行 `seed_ai_recipes` 可导入三组新样片并一次性补全未改图的旧案例提示词；不会覆盖已管理内容。详见 `../docs/ai-case-recipes.md`。

`ai-examples` 的 `results` 是风格 ID 与效果图路径的列表，在同一事务内保存。每例需 1–30 个不同风格；删除被案例引用的风格会返回 409，可改为停用。案例上传受 `aiexample` 新增/修改权限约束。已有角色授权不会由初始化命令自动扩大；非超级管理员需要在角色管理中授予 AI 案例权限，并授予查看 AI 风格以选择效果。

同一套餐类型最多有一个启用记录，数据库与 API 均校验。初始化只新增缺失案例，保留已修改原图、已移除效果、价格与角色授权。升级执行迁移与 `seed_catalog`；不要覆盖服务器数据库。

## 服务端测试订单（2026-10-24）

迁移 `0003` 增加浏览器归属摘要、唯一请求键、订单版本、演示设备与付款模式，保留历史订单。

- `GET /api/v1/store/orders/?page=1`：本浏览器订单列表，每页 20 条，不返回设计照片或邮箱。
- `POST /api/v1/store/orders/`：`request_key`（UUID）、`accepted`、`expected_amount`、可选 `customer_email`、`snapshot`。服务端读取启用打印套餐定价；价格改变返回 409。测试支付确认后状态为 paid，mode 明确为 demo；不会调用收款。
- `GET /api/v1/store/orders/<reference>/`：详情，含订单快照。
- `PATCH /api/v1/store/orders/<reference>/`：`revision`、`accepted`、新 `snapshot`，仅确认后未开印时可修改，需新设计码，保留金额。
- `POST /api/v1/store/orders/<reference>/actions/`：`revision`、当前 `code`、`action`，start 时增加 `station_id`。支持 start → ready → collect，未开印时支持 cancel；仅测试订单。

所有顾客接口都要求 `X-Order-Key`（浏览器随机生成的 64 位十六进制访问密钥），独立于管理员会话。服务端存 SHA-256 摘要，只返回当前密钥所属订单，其他浏览器返回 404。此密钥不通过 URL / 日志 / 二维码传输。接口拒绝缓存，不开放跨域访问；匿名 Cookie 不承担授权，因此写接口不使用会话 CSRF。频率限制每 IP 每进程每分钟 60 次；多实例需要共享限流。

订单创建使用数据库唯一请求键与套餐行锁避免重复；修订、状态流转在订单行锁下校验版本，重复请求不重复推进。同一笔订单的金额与设计快照独立保存。静态编辑器当前支持的机型 / 设计必须仍启用。快照仅接受声明式字段、受限图层和有效图片，最多 300 万字符的图片 data URL / 400 万像素；照片仅在授权订单详情中读取，不保存到公开 media。当前是压缩预览快照，不能视为生产打印文件。

顾客访问依赖本浏览器持有的密钥，没有账号找回与跨设备扫码授权。旧 IndexedDB 演示订单不会自动导入；新下单失败不会回退本地“已付款”。

## Stripe 手机壳支付

后台 `/admin/stripe` 可配置开关、测试/正式环境、用户端网站地址和两组 Secret Key / Webhook 签名密钥。默认关闭，旧演示流程保留。开启后壳单先创建为待付款，只有通过 Stripe 签名与金额校验的 Webhook 才确认到账。配置权限仅超级管理员，密钥使用现有 `AI_CONFIG_ENCRYPTION_KEY` 加密。

- `GET/PATCH /api/v1/admin/stripe/`：安全配置读取与更新，PATCH 要求 `revision`；密钥留空保留，`test/live: {clear: true}` 显式清除。
- `GET /api/v1/store/payment-config/`：公开付款方式、环境与可用状态，不含密钥。
- `POST /api/v1/store/orders/`：增加 `payment_provider`（`demo/stripe`）、`payment_mode`（`demo/test/live`），与当前配置不符返回 409；Stripe 订单状态初始为 `pending`。
- `POST /api/v1/store/orders/<reference>/checkout/`：验证浏览器归属，返回该订单的托管付款链接，重复请求保持同一 Session。
- `POST /api/v1/payments/stripe/webhook/`：验证原始请求签名并幂等更新订单。

迁移和账号注册后的配置、测试方法及边界见 [Stripe 接入说明](../docs/stripe-payments.md)。
