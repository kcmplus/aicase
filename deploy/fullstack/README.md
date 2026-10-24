# 前后端部署模板

测试环境已部署独立前后端。实际路径、运行服务、验证和回滚见 `../test-server/README.md`；本目录仍保留通用模板，不能不经核对直接覆盖现有配置。

建议同域路径：

- `/` → 原用户端 `frontend/storefront/`
- `/admin/` → 管理界面 `frontend/admin/dist/`
- `/api/` → 回环地址上的 Gunicorn / Django
- `/media/` → 持久的公开图库上传目录

每次前端发布都构建并打包两个前端目录，后台代码、`.env`、数据库和 `.venv` 均在 Web root 之外。不能把整个项目根目录作为 Nginx root。PostgreSQL、上传目录和审计数据独立持久化，升级前备份。创建独立服务账号，Gunicorn 不以 root 运行。

`nginx.locations.conf.example` 只包含待合并的 location；应保留现有 TLS、ACME 和 HTTP 跳转配置。路径都是模板，需替换实际发布根目录。`aicase-backend.service.example` 供 systemd 使用，实际已应用配置位于 `test-server-applied/`，其中端口与通用模板不同。

发布步骤：安装锁定依赖 → 管理后台构建 → 数据库备份 → migrate → 首次 seed_catalog → 首次 createsuperuser → 检查配置 → 启动后端 → 核验匿名不能读写管理接口 → 原子切换前端发布 → HTTPS 核验与后台角色冒烟。之后新增目录配置也不会自动接入用户端，仍须完成客户端数据源改造。

登录 Nginx 限流 zone 放在 http 作用域，跨 worker 生效。生产前端和 API 同源，保留 Host 并由代理覆盖 X-Forwarded-Proto。启用 DJANGO_TRUST_PROXY 仅适用于该可信代理。直接公网访问 Gunicorn 端口应禁止。
