# AI CASE STUDIO Implementation Plan

**Goal:** 可预览、可测试的六页响应式演示原型。
**Architecture:** 浏览器本地状态 + 纯函数业务校验 + 六页路由。
**Tech Stack:** HTML / CSS / JavaScript modules / Node test runner / Playwright。
**Spec:** design.md

## Global Constraints
- 保留邮寄、现场两条闭环；全部外部能力标为模拟。
- 账户记忆默认机型；扫码设备不能默默替换已选机型。
- 无真实支付、打印、认证、物流或 AI 服务。

## Review Focus
- 未知设备、不支持、缺货、离线不得提交现场订单。
- 首访、登录、退出及刷新保持正确账户状态。
- 图片上传失败、过大或格式错误不破坏已有设计。
- 支付失败及双击不重复生成订单。
- 手机和竖屏设备无溢出，按钮可触摸、表单可键盘操作。

## Tasks
- [x] 1. core.test.mjs 先定义兼容、库存、订单和默认机型行为测试，运行观察失败，再实现 dist/core.js 直至通过。
- [x] 2. 实现 dist/index.html、styles.css、views.js、app.js；加入本地矢量艺术图案及六页交互。
- [x] 3. tests/browser.mjs 检查邮寄/现场闭环、账户持久化、扫码异常、上传、失败支付与响应式截图；修复发现的问题。
- [x] 4. README 记录启动与演示边界，运行完整验证并打开预览；尝试私有托管。

验证记录：6 项规则测试；15 项浏览器流程检查，含 5 种尺寸 × 6 页面无横向溢出；独立代码复核发现默认机型覆盖、异步支付状态、扫码刷新三处问题，均先复现后修复，另有 2 项专门回归检查。测试截图位于 test-results。
