# AI 生图服务配置

入口：后台侧栏「AI 生图配置」（`/admin/ai-service`），也可从「AI 提示词」进入。仅有效的超级管理员可以访问、保存及检查连接；普通后台角色不能获得此权限。

## 使用

1. 在 OpenAI 平台创建 API Key，并确认项目可使用的图像模型。
2. 在配置页选择模型，填入 Key，点击「保存配置」。
3. 点击「检查连接」，查看结果和检查时间。

保存后仅显示密钥末尾四位。留空保存会保留原密钥；填写新 Key 会替换；「清除密钥」需要明确确认。模型或密钥变更后会清空旧检查结果。配置使用版本号防止多个管理员互相覆盖；遇到冲突需刷新后重新编辑。

保存不要求 `sk-` 等特定前缀，也不限制凭据的最小长度；支持 `at` 开头的凭据。首尾空白会自动去除，内部空白、控制字符及误粘贴的请求头会提示修正。保存成功只表示已加密存储，凭据是否被 OpenAI 接受由「检查连接」确认。

连接检查仅向固定地址 `https://api.openai.com/v1/models/{model}` 发送 GET 请求，读取模型信息，不调用图片生成接口，也不会将凭据转发至重定向地址。检查通过只说明可访问该模型信息，不能证明图片生成权限、账户余额或图片质量；受限 Key 若无 Models 读取权限也可能检查失败。前台已接入真实生图：顾客确认后使用上传原图、后台英文风格提示词与机型构图要求调用图片编辑接口。保存 Key 不会自动触发生图或修改案例；配置页另外展示最近一次真实生图的结果。详见 [真实 AI 生图](live-ai-generation.md)。

## 存储与部署

- 依赖 `cryptography`，版本锁定在 `backend/requirements.txt`。迁移 `0005_ai_service_config` 新增单例配置表。
- 生产通过 `AI_CONFIG_ENCRYPTION_KEY` 环境变量提供独立 Fernet 主密钥（32 字节随机数的 URL-safe Base64）。不要复用 Django SECRET_KEY、OpenAI Key，也不要将其放入前端、Git 或日志。
- 配置表存储认证加密后的 API Key；接口只返回状态、末尾四位和检查时间。审计仅记录操作名称，不包含明文、密文或请求正文。配置接口禁止缓存，写操作要求 Session + CSRF。
- 开发环境首次启动自动生成 `backend/.local-ai-encryption-key`，权限 0600，已加入 Git 忽略；生产缺少有效主密钥时禁止保存/使用 API Key。
- 主密钥必须跨发布保持不变，和数据库一起进行受限备份。替换或丢失主密钥会使原密文无法解密，需重新填写 API Key；不要在每次发布时重新生成。
- 测试服务器主密钥位于 root-only `/etc/aicase/backend.env`，既有备份脚本同时备份该文件和数据库。密钥不进入 Web 发布目录。限流目前使用单进程缓存，多实例需共享限流设施。

## 验证

新增自动测试覆盖超级管理员限制、CSRF、密文存储、响应及日志脱敏、空值保留、清除、并发版本冲突、加密配置异常、固定服务地址、禁止重定向、上游错误脱敏和检查限流。外部请求均模拟，不使用真实 API Key。后台页面已验证模型保存与刷新保留。

参考：[OpenAI API 身份验证](https://developers.openai.com/api/reference/overview)、[图像生成模型](https://developers.openai.com/api/reference/resources/images/methods/generate)、[读取模型信息](https://developers.openai.com/api/reference/resources/models/methods/retrieve)、[Fernet](https://cryptography.io/en/latest/fernet/)。文档核对日期：2026-10-27。
