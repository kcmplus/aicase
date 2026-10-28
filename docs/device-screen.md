# 设备端竖屏页面

独立入口：`/device.html`。顾客在手机上设计并完成订单，到设备输入设计码、确认机型和图案后打印。设备页不提供重新编辑或二次收款。

## 当前可体验的范围

本地预览：[设备端英文页面](http://127.0.0.1:4175/device.html?lang=en-US&station=DEMO-02)。`lang=zh-CN` 可直接进入中文，页面右上角也可切换。

默认 `mode=demo`：独立示例数据，可体验加入队列、叫号、确认、16 秒模拟打印及取件。点击页脚“演示：加入一单”可连续加入不同订单，触屏输入设计码也会入队，不能越过队首开印。不会调用真实打印机或修改手机端订单。两款示例：

| 机型 | 设计码 |
| --- | --- |
| iPhone 17 / Bloom | `POP-C-1717171717171717` |
| iPhone 16e / Off Script | `POP-C-1616161616161616` |

同一个设备编号、同一浏览器标签页内，完成的示例订单也不能再次打印。点击“演示：加入一单”会创建新的模拟订单。页面全程标注“队列演示 · 手机推单尚未接入”。这不是服务器队列，手机扫码后还不能跨设备推单。

**尚未接入真实设备查单、库存、打印与出货服务。** 现有顾客订单接口要求原浏览器的 `X-Order-Key`；本次没有取消这一验证，也没有把顾客密钥传给设备。正式跨设备打印需要后端增加经过设备身份认证的专用服务。

## 嵌入及配置

设备 WebView 加载 `/device.html?mode=connected&station=KIOSK-01`。没有完整接入适配器时，页面显示“设备尚未连接”，不会自动降级为模拟打印。

设备宿主需在 `device-app.js` 加载前，注入配置和版本为 2 的队列适配器。可以由同域本地文件提供，也可以由设备 WebView 宿主注入。生产凭据应放在设备服务或宿主中，不能写进网页源码或链接。

```js
window.POPOMO_DEVICE_CONFIG = {
  mode: 'connected',
  stationId: 'KIOSK-01',
  storefrontUrl: 'https://YOUR_SHOP_DOMAIN/?lang=en-US',
};
window.POPOMO_DEVICE_ADAPTER = {
  version: 2,
  async connect({stationId}) { /* 返回 Station */ },
  async getQueue({stationId}) { /* 返回 Queue；由我们的服务器维护 */ },
  async enqueue({stationId, code}) { /* 设计码入队后返回 Queue */ },
  async defer({stationId, code}) { /* 队首让下一位先来，返回 Queue */ },
  async lookup({stationId, code}) { /* 返回 Order */ },
  async start({stationId, code, orderId, revision, idempotencyKey}) { /* 返回 Job */ },
  async getJob({stationId, jobId}) { /* 返回 Job */ },
  async collect({stationId, jobId}) { /* 返回完成后的 Job */ },
};
```

这些方法是前端接入约定，不是已实现的 HTTP 地址。可返回值或 Promise；默认等待 15 秒后提示连接异常。查询参数优先于配置，仅适合预览/运维配置；正式部署可固定入口参数。适配器和服务端必须自行校验已认证设备身份，不能信任 URL 的设备编号作为授权依据。

`storefrontUrl` 必须换成顾客手机能访问的地址。设备页在屏幕下方持续显示该地址的二维码，确认、打印、取件期间都不会消失，并附带 `station` 参数。`127.0.0.1` 本地演示链接只能在当前电脑使用，正式本地宿主未配置公网地址时不展示无效的设计二维码。

## 响应结构

```ts
type Queue = {
  stationId: string;
  items: Array<{
    orderId: string;
    ticket: string; // A001 等展示号码，不是取单授权凭据
    code: string; // 仅向已认证设备返回，不在排队屏幕公开显示
    model: string;
    status: 'waiting' | 'awaiting_confirmation' | 'printing' | 'ready';
  }>;
  confirmBy: number | null; // 服务器给出的当前叫号期限，毫秒时间戳
};
type Station = {
  id: string; // 必须与当前 stationId 一致
  name?: string;
  status: 'ready' | 'offline' | 'busy' | 'maintenance';
  availableModels: string[]; // 使用订单快照的机型名称，例如 iPhone 17
  activeJobId?: string; // 当前设备未结束的任务，供刷新恢复
};
type Order = {
  id: string;
  revision: number; // 正整数，用于拒绝旧设计
  status: 'paid' | 'unpaid' | 'printing' | 'ready' | 'completed' | 'cancelled';
  amountCents: number; // 已支付订单的锁定金额，非前端报价
  currency: string; // 如 USD
  snapshot: object; // 与 simple-core.js/readPass 兼容的 version:2 设计快照
  jobId?: string;
};
type Job = {
  id: string;
  status: 'printing' | 'ready' | 'completed' | 'error';
  phase?: 'preparing' | 'printing' | 'finishing';
  progress?: number; // 0–100；未知时省略，页面显示不定进度
  order: Order; // 包含同一个 jobId；正常状态须与 Job.status 一致
};
```

订单 ID、任务 ID 是 1–100 位字母、数字、短横线或下划线。当前快照按已有格式校验，包含设计、机型及版式；照片采用已有的受限 data URI 格式，不能直接塞入任意远程图片地址。正式素材传输方式需与设备方另行确认。

服务端必须原子校验最新设计码、订单修订、付款、机型库存、设备状态和队首归属，并锁定订单及库存后再发起打印。`idempotencyKey` 相同的重试必须返回同一任务，包括网络超时后重试；同一订单使用新键也不能重复打印。`collect` 必须幂等，只能在任务已可取件时确认完成。

打印任务刷新恢复不能只依赖浏览器：设备服务必须持久保存活动任务、确认打印机反馈、支持重启后的 `activeJobId`。页面每秒查询一次状态，不凭本地计时推断真实任务完成。出货传感器或打印机状态的映射由设备适配器负责。

可抛出带 `code` 的错误：`INVALID_CODE`、`NOT_FOUND`、`UNPAID`、`REPLACED`、`CANCELLED`、`ALREADY_COLLECTED`、`ALREADY_STARTED`、`OUT_OF_STOCK`、`OFFLINE`、`BUSY`、`DEVICE_ERROR`、`NOT_CONNECTED`、`CONNECTION`、`QUEUE_TURN`、`QUEUE_FULL`。页面显示统一顾客文案，不直接展示上游错误原文。

## 手机扫码、设备输码与会话

- 设备没有扫码硬件。下方始终显示二维码，顾客手机可以在他人确认、打印、取件期间扫码设计；设备端不接收扫码器事件。
- 已有设计的顾客点击“输入我的设计码”，在中间操作区使用触摸键盘入队；上方队列与下方二维码保持可见。完整码为 `POP-C-` + 16 位十六进制字符。
- 手机扫设备屏幕仅打开带设备编号的设计页面，当前不会自动将订单推送到设备。后续若改为手机确认后自动送单，需要双方接口支持设备会话绑定、订单授权与任务推送。
- 手动输入：设备屏幕提供十六进制触摸键盘，也支持物理键盘、粘贴。识别到 URL 时只取 `code` 参数，不打开或请求扫码得到的网址。
- 确认前空闲 100 秒出现提醒，120 秒清空当前设计。用户选择继续会保留；已开始或结果未确认的打印任务不会被自动清除。
- 打印意图在调用设备前保留同一幂等键，刷新恢复时先查任务。收到超时不显示成功，也不会另建任务。
- 取件完成后移除设计和活动任务，8 秒回首页。浏览器仅保存活动任务 ID 或已确认的打印意图，不保存顾客照片；模拟适配器另存示例任务的编号和时间。
- 设备关闭标签页、崩溃、退出全屏、屏幕休眠等行为由设备宿主管理；真正的 kiosk 模式和现场取件传感器需在硬件联调中验证。

## 队列展示与正式服务边界

设备页面分为三块：上方公开队列（取件号、等待数、当前状态），中间当前订单的确认/进度/取件，下方固定二维码。队列卡片不显示照片、邮箱或完整设计码。帮助面板只覆盖中间区域，不遮住二维码。

演示规则：先到先服务；重复加入同一订单保留同一个号码；最多 100 单。只允许队首确认开印。等待确认超过 90 秒且有其他顾客时，移到队尾保留号码和订单，也可以点击“让下一位先来”。打印中和待取件的订单不参与轮转。按当前单取件口方案，确认取件后才让下一位开印，防止取错；多取件仓的调度需设备方确认能力。

**生产排队应由我们的服务器负责，不能依靠设备网页或 sessionStorage。** 手机扫码绑定网点及具体设备，主动推送已确认订单到该设备队列；服务器为订单分配展示号、记录设计版本、处理幂等入队和叫号期限，再通知设备网页。设备打印完成信号来自厂商接口。页面刷新、两台屏幕同时在线、断线重连都只能恢复服务端顺序，不能本地抢占或另建打印任务。

当前实现只完成队列屏幕、模拟队列规则及接入约定。还未实现手机绑定会话、手机推单接口、服务器队列表或厂商打印回调。旧版仅有 1 号适配器的打印方法仍可由客户端调用，但不提供队列能力，页面会标示队列不可用；正式接入需要上述 2 号契约。生产 `enqueue` 需验证设计码的取单授权，手机端另须验证订单所有权；不能把展示号或 URL 设备编号当作凭据。

实现入口：`frontend/storefront/device.html`；页面与样式：`device-app.js`、`device.css`、`device-queue.css`；校验与适配器：`device-core.js`、`device-service.js`。规则测试：`npm test` 包含 `frontend/tests/device.test.mjs`。
