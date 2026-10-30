# Dev 自动构建与部署

目标环境：`https://aicase.chunpat.cc`，服务器 `177.3.42.128`，SSH `root:22`。
与原测试站 `aicase.dinglh.cn` 使用不同服务器、数据库、密钥和上传目录。

## 日常使用

- 推送到 `dev`：测试 → 构建 → 备份 → 数据库迁移 → 发布 → 检查在线服务。
- PR 合并到 `dev`：由合并产生的 push 触发同一流程，只部署一次。
- PR 尚未合并：只检查和构建，不读取部署密钥，不部署。
- `main` 的普通推送不部署 dev。
- 手动重试：仓库 **Actions → Dev · build and deploy → Run workflow → 选择 dev**。
- 每次发布保留构建包 7 天；连续发布串行执行，不中断已开始的迁移。
- 旧提交的运行不能覆盖当前 dev 分支的新版本。需要回退时，将修复或 revert 提交推送到 dev。

工作流：[`dev.yml`](../../.github/workflows/dev.yml)。触发方式遵循 [GitHub push / pull_request 事件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)。

## GitHub 配置

仓库 **Settings → Environments → dev**：部署分支限制为 `dev`，配置以下 Environment secrets。

| 名称 | 内容 | 用途 |
| --- | --- | --- |
| `DEV_SSH_PRIVATE_KEY` | 专用于此 dev 主机的完整 SSH 私钥 | Actions 登录服务器 |
| `DEV_SSH_KNOWN_HOSTS` | 已核验的服务器 SSH 主机公钥记录 | 校验服务器身份 |

仓库 **Settings → Secrets and variables → Actions → Variables**：

| 名称 | 值 | 用途 |
| --- | --- | --- |
| `DEV_DEPLOY_ENABLED` | `true` | 开启构建成功后的部署；设为 `false` 暂停部署，测试构建仍执行 |

`DEV_DEPLOY_ENABLED` 必须是 **Repository variable**，不能只放在 Environment variables 中；作业开始前就需要判断这个开关。主机、端口、用户名、域名已写在工作流和服务器模板中，不必再填一套变量。

OpenAI Key、数据库密码、Django 密钥不进入 GitHub 构建包。应用配置留在服务器 `/etc/aicase-dev/backend.env`；OpenAI 凭据在 dev 后台「AI 生图配置」中独立设置。本地的 Key 和数据库不会自动复制到 dev。

有关环境权限和密钥，参见 [GitHub 环境配置](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)。

## 服务器结构

| 项目 | 位置 |
| --- | --- |
| 代码发布 | `/opt/aicase-dev/releases/<运行号>-<重试号>-<commit>/` |
| 当前版本 | `/opt/aicase-dev/current` 软链接 |
| 后端服务 | `aicase-dev.service`，仅监听 `127.0.0.1:18011` |
| 图片清理 | `aicase-dev-ai-cleanup.timer`，部署时自动启用，每小时清理到期生成图片，保留任务与费用 |
| 后端配置 | `/etc/aicase-dev/backend.env`，仅 root 可读 |
| 数据库 | PostgreSQL 17，数据库和用户均为 `aicase_dev` |
| 上传文件 | `/var/lib/aicase-dev/media` |
| 发布前备份 | `/var/lib/aicase-dev/backups/<发布编号>/` |
| 宝塔 Nginx 配置 | `/www/server/panel/vhost/nginx/aicase-dev.conf` |
| HTTPS 证书 | `/etc/letsencrypt/live/aicase.chunpat.cc/` |

服务器使用 Debian 13 / Python 3.13。Actions 使用 Python 3.13、PostgreSQL 17 和 Node.js 22。
初始化脚本是 [`bootstrap.sh`](bootstrap.sh)，适用于这台使用宝塔 Nginx 的 Debian 主机。它安装必要依赖、创建独立服务用户和数据库、生成配置密钥、申请 HTTPS 证书并开启续期。通常只执行一次；日常发布由 [`deploy.sh`](deploy.sh) 完成，不重新初始化服务器。

首次发布导入默认目录、AI 案例和供应商提供的两个手机底图。后续发布保留后台管理的数据，不重新覆盖目录或密码。dev 是独立数据库，管理员通过以下命令创建：

```sh
sudo -i
set -a
source /etc/aicase-dev/backend.env
set +a
runuser -u aicase-dev -- /opt/aicase-dev/current/.venv/bin/python /opt/aicase-dev/current/backend/manage.py createsuperuser
```

## 发布与故障处理

发布先安装新版本依赖，不影响当前版本。切换前进入短暂维护状态，等待已有 AI 任务完成（最多 5 分钟）；仍有任务时本次发布退出，旧版本继续服务。暂停服务后备份数据库、上传文件和配置，再迁移、切换版本并检查 API。发布后的公网检查同时覆盖用户端相关入口和后台。

健康检查失败会尝试恢复上一版代码；**不会自动反向迁移或覆盖数据库**。数据库结构变更应保持与上一版兼容。首次部署失败时保留维护状态，避免展示半初始化站点。

```sh
# 服务状态与日志
systemctl status aicase-dev
journalctl -u aicase-dev -n 100 --no-pager

# 当前版本
cat /opt/aicase-dev/current/VERSION

# Nginx 修改后先检查再重载
nginx -t && nginx -s reload

# 查看续期任务
systemctl status certbot.timer

# AI 图片到期清理（发布维护期间跳过）
systemctl status aicase-dev-ai-cleanup.timer
journalctl -u aicase-dev-ai-cleanup -n 50 --no-pager
```

备份中含数据库和加密密钥，只保存在服务器 root 可读目录。当前不自动删除历史发布和备份；需定期检查磁盘，确认可用备份后再清理。重新执行失败运行会使用新的重试编号。

设备端地址示例：`https://aicase.chunpat.cc/device.html?lang=en-US&station=DEV-01`。当前设备排队仍是浏览器演示，尚未接入真实跨设备队列与厂商打印接口；部署不会改变这一点。
