# 后端直连调试

用本地 Django 后端连接手机 H5 和 `aicase-terminal` 设备页，跳过供应商 API、WebSocket、Tauri 和私有核心包。订单、模板绑定、上传图片、访问权和手机确认走实际业务代码；打印机、机械臂、出货是模拟，不控制硬件。

## 一条命令启动

两个仓库放在同一父目录，安装各自原有依赖，`aicase/backend/.venv` 和本地 `backend/db.sqlite3` 必须存在，数据库内需有设备机型及完整模板，`backend/media` 保留相应素材。

在 **aicase-terminal 根目录** 执行：

```sh
npm run dev:direct
```

默认设备 `789`、商家 `351`，来自之前真机调试的设备资料。不同路径或设备可指定：

```sh
npm run dev:direct -- --backend-dir /path/to/aicase --device-id 401 --shop-id 146
```

启动器会显示：

- 设备页：`http://127.0.0.1:4182/direct.html?lang=zh-CN`
- 手机页：自动选择本机局域网 IP 的 `4174` 端口，带设备和商家参数；也显示在设备二维码内。
- 后端仅监听 `127.0.0.1:8001`，与原来的 `8000` 后端分开。

电脑与手机连接同一个局域网。多网卡时可以用 `--h5-origin http://正确的电脑IP:4174` 指定。不要扫到线上 `aicase.chunpat.cc`：线上站点使用另一套数据库，不会把订单推给这个本地调试进程。

## 实际操作

1. 保持设备页打开，手机扫码。
2. 选择机型、照片，确认 0 元联调订单。
3. 后端接收实际设计图片和订单，设备页约 2 秒后显示等待确认的订单。
4. 手机点击“立即打印”。模拟器依次处理已确认的订单，约 20 秒模拟打印、5 秒模拟出货。
5. 两个页面刷新后仍读取已保存的订单和模拟状态。右上角“设备状态”可勾选调试日志；原生硬件状态保持未知。

模拟完成不会将 `PrintOrder` 改成已打印、已领取，不扣真实库存，也不会记录供应商付款成功。手机页明确显示“完成（仅模拟）”。设备页原有状态展示由顶部的模拟说明限定。

## 数据与隔离

- 首次启动使用 SQLite backup 将本地数据库复制到 `backend/.direct-debug.sqlite3`；迁移及打印价格改为 0 只作用于副本。之后启动沿用该副本，不重复覆盖。
- 模板、机型、库存来自副本，仅选定设备可售；调试中不检查库存快照的 15 分钟过期时间，也不调用供应商刷新库存。库存不是实时库存。
- `config.direct_debug` 单独启用调试功能。常规 `config.settings` 默认关闭，线上部署不读取这个本地开关。
- 新绑定订单保存 `transport=direct_debug`；历史供应商订单保持 `supplier`。模拟订单即使关闭调试模式也不会回退为供应商推单、查单或付款。
- 只接收服务端创建的 `free_test` 零金额、自取、已免付确认且无有效退款订单；在线结账在此模式下禁用。
- `/api/v1/debug-terminal/poll/` 是有权限的 POST，接收待模拟订单并更新模拟状态。关闭设备页会停止更新，重新打开后按已记录的开始时间计算进度。预览图片同样校验权限，不公开打印原图。
- 随机凭证保存在忽略提交的 `backend/.local-direct-debug-token`，仅由本机 Vite 代理加入请求，不写入浏览器代码或二维码。
- 原来的 `/api/v1/terminal/*` 继续返回 410。

按 Ctrl+C 停止所有调试进程。后台 Python 代码改动后重新运行命令。单独准备或运行后端可在 `aicase` 根目录执行 `npm run backend:direct -- --check` 或 `npm run backend:direct`；该命令本身不会启动手机和设备页面。

这是本地可运行版本；不代表已部署到测试站，也不代表真机打印验收。

## V35 自动化隔离配置基础（开发交付，非完整浏览器入口）

`config.direct_debug` 新增显式 `DIRECT_DEBUG_ISOLATED=1` 分支。默认未设置时，上述既有调试启动行为不变。V35 自动化不得使用旧的 `backend:direct` 启动器复制用户数据库，必须由后续浏览器启动器创建全新临时目录和合成数据。

隔离分支在导入基础 settings 前检查以下参数，缺失或不合法即停止，不回退本地凭证：

| 参数 | 要求 |
| --- | --- |
| `DJANGO_DEBUG` | 显式 `1` |
| `DIRECT_DEBUG_ISOLATED_ROOT` | 用 `tempfile.mkdtemp(prefix='aicase-v35-')` 新建的绝对路径；父子进程保持相同 `TMPDIR` |
| `DJANGO_SECRET_KEY`、`DIRECT_DEBUG_TOKEN` | 每轮生成至少 32 字符的随机值，不打印或提交 |
| `AI_CONFIG_ENCRYPTION_KEY` | 每轮生成 32 字节随机值的 URL-safe Base64 |
| `DIRECT_DEBUG_DEVICE_ID` | 合成设备的正整数 ID |
| `DIRECT_DEBUG_API_PORT` | 独立 1024–65535 端口，排除 8000/8001 |
| `DIRECT_DEBUG_H5_ORIGIN` | `http://127.0.0.1:独立端口`，与 API 不同，排除 4173/4174/5173，不带路径或认证信息 |

数据库固定为临时目录的 `db.sqlite3`，媒体和静态输出分别为 `media/`、`static/`。不接受 PostgreSQL 环境选择、软链接或硬链接。配置允许同一轮迁移和服务进程复用临时数据库；**新建目录、端口占用检查、按 API 端口启动服务以及 finally 清理仍由启动器负责**，配置本身不证明目录内容是新数据，也不替代端口绑定参数。

此模式关闭供应商推单和放行，邮件使用内存后端，并阻断当前 Python 进程的 socket 连接、UDP 发送及非本地 DNS 解析。它不构成操作系统沙箱，不约束子进程或浏览器；浏览器外网阻断和外部渠道 mock 仍须由后续 E2E 脚本实现。不能以此启用真实渠道。

2026-11-14 修复 QA 发现的 UDP `sendmsg` 遗漏：平台提供该方法时一并拦截，防止携带目标地址绕过 `connect/sendto`。保留 QA 原断言，隔离配置开发自测 9/9 通过、无跳过（`/tmp/v35-sendmsg-selftest.log`），待独立复验；未证明实际端口监听或浏览器外网隔离。

开发自测命令（不读取现有数据库或本地凭证）：在 `backend/` 执行 `.venv/bin/python -m unittest management_api.test_direct_debug_isolation -v`。测试创建临时目录、合成密钥和全新 SQLite，执行真实迁移和健康接口请求，结束后清理。本子组未提供常驻预览服务或整站浏览器证据。

## 第七组服务启动器子组（2026-11-14，端口权限阻塞，未验收）

新增 `scripts/v35_runtime.py`：每次分配独立 loopback 端口、新建 `aicase-v35-*` 临时目录、生成合成凭证，以环境白名单启动迁移、Django 和有效 storefront；检查首页及代理健康接口。上下文退出、启动失败和命令行 Ctrl+C/SIGTERM 走子进程终止及临时文件清理。不复制用户数据库，不读取旧调试凭证，不启动浏览器。当前仅迁移空库，**尚无合成业务设备、图片、订单夹具**，因此不提供可下单演示。

在具有本地监听权限的执行环境中，待测试命令：

```sh
backend/.venv/bin/python scripts/v35_runtime.py --check
backend/.venv/bin/python scripts/v35_runtime.py
backend/.venv/bin/python -m unittest discover -s scripts -p test_v35_runtime.py -v
```

默认端口随机；启动成功才输出 API 和 storefront 的实际地址（JSON），不输出凭证。可用 `--api-port` 和 `--h5-port` 指定独立非默认端口；占用时失败，不终止其他服务。常驻模式退出后删除空库、日志及媒体目录。后续 E2E 可复用 `IsolatedRuntime` 上下文管理器，但必须另行实现浏览器外网阻断、合成业务夹具和 DirectPoll 操作；本入口不构成系统或浏览器沙箱，不能用于真实业务。

本轮起点 `f2b0200b01b09dd2168b0f61bc05c16ef41fb749`，工作区原本干净；参考仍为 `5501bedb720d3e7552428b0dc75174973e87934c`（12 个 HTML）。启动器生命周期开发测试 **5 项均 ERROR**：当前沙箱对 `socket.bind(('127.0.0.1', ...))` 返回 `PermissionError: [Errno 1] Operation not permitted`，尚未启动服务或执行 HTTP 验证。日志 `/tmp/v35-runtime-selftest.log`。没有跳过或弱化断言；语法检查通过，但不能替代实际监听和清理验证。需要有监听权限的测试环境复验成功、占用端口、启动中断、业务体异常、Ctrl+C/SIGTERM 及残留进程/文件。当前不得声称提供了可访问预览地址。

`scripts/test-ui-v35-e2e.mjs` 仍未交付，固定浏览器 gate 缺口、旧单安全替换、完整视觉和业务验收均保留。未部署、未真机验证；检查点由 harness 管理。
