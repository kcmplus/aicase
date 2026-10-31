# Production：手动发布 main

生产地址：`https://popomo.chunpat.cc`，服务器 `2.25.179.110`，SSH `root:22`。
服务器为 Debian 12 / Python 3.11 / PostgreSQL 17；数据库、媒体、密钥均独立于 dev。

## GitHub 发布

1. 将审核通过的代码合入 `main`。
2. 打开 **Actions → Prod · manual deploy main → Run workflow**，分支选择 **main**。
3. 等待检查、构建、备份、迁移、上线和 HTTPS 检查全部成功。

合并或推送 `main` **不会自动上线**。面向 main 的 PR 只测试和构建，不接触生产 secrets。
手动选择其他分支会失败；发布前还会检查 main 最新提交，拒绝旧运行覆盖新代码。
工作流按生产环境串行，服务器同时用文件锁避免手工发布和定时备份冲突。

GitHub **Settings → Environments → prod**：

| 配置 | 值 |
| --- | --- |
| Deployment branches and tags | Selected branches，只有 `main`，不允许 tag |
| Environment secret `SSH_PRIVATE_KEY` | 已授权访问生产主机的 SSH 私钥 |
| Environment secret `SSH_KNOWN_HOSTS` | 经验证的 `2.25.179.110` SSH 主机密钥 |

不需要配置 `PROD_DEPLOY_ENABLED` 或其他变量。主机和域名已固定在工作流中。
SSH 使用严格主机密钥校验。服务端配置和业务密钥不上传 GitHub，也不进入构建包。

## 首次准备服务器

先将 `popomo.chunpat.cc` 的 A 记录指向 `2.25.179.110`，移除不适用的 AAAA 记录。
将 `deploy/prod/` 中的脚本和模板复制到服务器私有目录，以 root 执行：

```bash
bash bootstrap.sh --prepare-only
# DNS 生效后：
bash bootstrap.sh
```

脚本从 PostgreSQL 官方 PGDG 仓库安装 17，创建 `aicase_prod` 数据库及普通同名角色，
生成独立密钥和服务配置，添加单独的宝塔 Nginx 配置，并申请/自动续期 HTTPS 证书。
已有站点配置不被覆盖。数据库只需监听本机，不需要向公网开放 5432。
重复运行保留已有数据库、密码和密钥；首次发布前新域名处于维护状态。

第一次成功发布后创建网站管理员（交互输入，密码不写进命令历史）：

```bash
sudo -i
set -a
source /etc/aicase-prod/backend.env
set +a
runuser -u aicase-prod -- /opt/aicase-prod/current/.venv/bin/python \
  /opt/aicase-prod/current/backend/manage.py createsuperuser
```

在生产后台独立配置邮件、AI 和支付服务。不会从 dev 复制订单、用户、密码或支付密钥。
首次发布只导入项目自带目录、AI 样式及手机底图；后续发布保留后台数据。

## 文件及服务

| 内容 | 位置 |
| --- | --- |
| 发布目录 / 当前版本 | `/opt/aicase-prod/releases/` / `/opt/aicase-prod/current` |
| API | `aicase-prod.service`，`127.0.0.1:18012` |
| 数据库 | PostgreSQL 17，`127.0.0.1:5432`，`aicase_prod` |
| 私有环境配置 | `/etc/aicase-prod/backend.env`，root-only 600 |
| 上传图片 | `/var/lib/aicase-prod/media/` |
| Nginx 站点 | `/www/server/panel/vhost/nginx/aicase-prod.conf` |
| HTTPS 证书 | `/etc/letsencrypt/live/popomo.chunpat.cc/` |
| AI 图片清理 | `aicase-prod-ai-cleanup.timer`，每小时 |
| 发布前备份 | `/var/lib/aicase-prod/backups/<运行号>-<重试号>-<提交>/` |
| 每日备份 | `/var/lib/aicase-prod/daily-backups/<UTC时间>/` |

每日备份在首次发布成功后启用，北京时间 04:40 左右执行，保留至少 14 天。
包含数据库 custom dump、媒体文件和私有环境配置；仅成功备份后清理过期每日快照。
发布前备份不自动删除。备份与线上数据在同一台机器，需另行配置异地副本以防主机故障。
每日在线备份的数据库具有一致性快照，媒体文件在备份期间仍可能变化；发布前备份则在维护期停 API 后执行。

可在宝塔「计划任务 → Shell 脚本」以 root 手动调用以下命令，也可通过宝塔「文件」下载备份：

```bash
/usr/local/sbin/aicase-prod-backup
```

systemd 已安排每日执行，无需再添加重复的宝塔定时任务。文件不会自动登记到宝塔 PgSQL 备份列表。
`pg_restore --list` 仅检查备份目录可读，不等同于完整恢复演练；`.dump` 使用 `pg_restore` 恢复。

## 发布失败与恢复

发布先准备新版本，再进入维护模式，等待 AI 任务结束（最多 5 分钟），停 API 后备份。
备份失败不会执行迁移。迁移完成后原子切换代码，检查健康接口和目录接口，成功后恢复访问。
新版本失败时尝试切回旧代码；**不自动反向迁移或覆盖数据库**。
数据库变更需兼容上一版代码；旧版本也无法健康运行时保留维护模式，并在日志中提示处理。
首次发布失败保留维护模式。公网检查失败会让工作流失败，需要检查 DNS/TLS/Nginx；它不会触发数据库恢复。

```bash
systemctl status aicase-prod
journalctl -u aicase-prod -n 100 --no-pager
journalctl -u aicase-prod-backup -n 50 --no-pager
systemctl list-timers aicase-prod-backup.timer aicase-prod-ai-cleanup.timer
cat /opt/aicase-prod/current/VERSION
nginx -t
```

回退通常通过在 main 创建 revert/修复提交后重新手动发布完成。保留的发布目录和备份用于事故恢复；
恢复数据库前应先停止写入并保留当前数据，不直接对在线数据库执行覆盖恢复。
