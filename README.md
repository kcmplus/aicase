# POPOMO · 用户端与管理后台

图片已支持 WebP 多尺寸预览、懒加载及后台上传自动优化；原图独立保留。生成与维护方式见 [图片性能说明](docs/image-performance.md)。

项目已拆分为前端和 Python 后端两个模块。管理后台与 API 已部署到测试服务器：https://aicase.dinglh.cn/admin/ 。用户端已接通后台价格、AI 次数、风格和一对多案例；后台保存后刷新用户端即可生效。

```text
frontend/
  storefront/       用户端：选机型、设计编辑、照片、AI 演示、设计码
  admin/            Vue 3 + Element Plus 管理界面
  tests/            用户端回归测试
  scripts/          素材与历史检查工具
  server.mjs        本地用户端预览服务
backend/
  config/           Django 配置与接口路由
  management_api/   数据模型、权限、接口、迁移、初始化数据、测试
  manage.py
  requirements.txt  锁定的 Python 依赖
  .env.example      部署环境变量模板
  README.md
```

## 本地运行

用户端保持无需安装依赖即可运行。后端使用 Python 3.11+（本机验证为 3.14，服务器为 3.11），管理界面使用 Node.js 22.12+。

首次安装：

```sh
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/python backend/manage.py migrate
backend/.venv/bin/python backend/manage.py seed_catalog
backend/.venv/bin/python backend/manage.py createsuperuser
npm --prefix frontend/admin ci
```

分别在三个终端启动：

```sh
npm start          # 用户端 http://127.0.0.1:4173/
npm run backend    # Python API http://127.0.0.1:8000/
npm run admin      # 管理后台 http://127.0.0.1:5173/admin/
```

当前工作机已初始化本地数据库和 `admin` 超级管理员。随机初始密码保存在 `backend/.local-admin.txt`，仅本机拥有者可读，不纳入版本管理。测试服务器有独立的 `admin` 账号，随机密码在 `backend/.test-server-admin.txt`（仅本机拥有者可读，不纳入版本管理）。其他环境须自行创建管理员，无内置默认密码。

## 当前后台功能

- 数据概览：仅统计当前账号有权限查看的数据；没有伪造订单和收入。
- 品牌 / 机型：两级归类、搜索、分页、启用停用、排序、打印校准标记。
- Collection 图库 / 图案素材：配置编辑、图层 JSON、版权说明、图片上传。
- AI 风格 / AI 案例：风格描述与样片；每个案例管理一张原图及多个风格效果，支持上传、排序和停用。
- 价格套餐：打印价、月费、月度次数、首次体验次数。每种类型只能启用一个套餐。
- 管理员 / 角色：登录、退出、改密、角色分配、账号停用，超级管理员管理授权。
- 订单：用户端下单自动入库，查看设计与照片快照、金额、状态和客服备注；支持状态筛选。支付与打印仍为测试流程。
- 操作日志：后台登录、登出、内容变更、角色与账号操作、上传；不能通过管理 API 修改或删除。

用户端原功能完整保留，108 项规则测试、36 项后台测试通过。后台采用真实数据库和 API，不使用前端假数据。

**已接通价格与 AI 案例。** 用户端启动时读取 `/api/v1/catalog/`（v2），不缓存价格与案例；后台保存后刷新用户端生效。当前测试站打印 $9.00，AI $5.99/月、15 次，首次体验 1 次。机型、Collection 图库和图案仍使用静态目录，草稿保存在浏览器；新订单及确认的设计保存在服务端，旧本地订单保留兼容读取。已确认订单价格与 AI 样片保留快照；订阅当期额度不被配置修改覆盖，下次续期采用新配置。接口不可用时显示提示并暂停新订单，不回退到旧价格。确认订单时保存设计照片，不在编辑时上传。真实账号注册、订阅支付、AI 任务队列、机器认证和打印协议尚未接入。

## 下单流程（2026-10-24）

选机型与设计 → 确认测试支付 → 服务端生成订单 → 查看 / 保存二维码 → 机器演示 → 打印 / 待取货 / 已完成。前台“ My orders ”查看本浏览器全部服务端订单；后台“打印订单”查看详情。未开印时可修改设计或取消，修改后旧码失效、原金额保留；开印后锁定。重复提交采用同一个请求键，网络错误不会生成本地成功假象。

订单访问由浏览器随机访问密钥保护，服务端仅保存摘要；请求密钥不放在二维码、URL 或审计日志中。清除浏览器站点数据会失去顾客端访问权限，后台仍可查阅。尚无跨设备账号找回。私有照片保存在订单快照中，不暴露到公开图库。测试支付不会扣款，机器操作不会执行实际生产。

## 检查与构建

```sh
npm test
npm run test:backend
npm run build:admin
backend/.venv/bin/python backend/manage.py check
backend/.venv/bin/python backend/manage.py makemigrations --check --dry-run
```

管理界面构建输出 `frontend/admin/dist/`。用户端发布源改为 `frontend/storefront/`，**不要上传整个项目、数据库、凭据或 `.venv`**。根目录 `server.mjs` 保留为旧启动入口兼容层。

详见 [后端说明](backend/README.md)、[架构与权限](docs/backend-architecture.md)、[用户端说明](frontend/README.md)、[后续部署模板](deploy/fullstack/README.md)。
