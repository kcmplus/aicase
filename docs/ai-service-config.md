# AI 生图服务配置

入口：后台侧栏「AI 生图配置」（`/admin/ai-service`），也可从「AI 提示词」进入。仅有效的超级管理员可以访问、保存及检查连接；普通后台角色不能获得此权限。

## 使用

1. 在配置页选择「OpenAI」或「七七八 AI」，点击对应控制台链接创建该服务商的 API Key。
2. 选择模型，填入该服务商的 Key，点击「保存配置」。保存后前台使用所选服务商。
3. 点击「检查连接」，查看结果和检查时间。

各服务商独立保留模型及加密密钥；切换时不会复用另一家的 Key。首次选择尚未配置的服务商时生图不可用，填写其 Key 后启用。保存后仅显示密钥末尾四位。留空保存会保留该服务商的原密钥；填写新 Key 会替换；「清除密钥」需要明确确认，且只清除当前服务商的 Key。服务商、模型或密钥变更后会清空旧检查结果。配置使用版本号防止多个管理员互相覆盖；遇到冲突需刷新后重新编辑。

保存不要求 `sk-` 等特定前缀，也不限制凭据的最小长度；支持 `at` 开头的凭据。首尾空白会自动去除，内部空白、控制字符及误粘贴的请求头会提示修正。保存成功只表示已加密存储，凭据是否被所选服务商接受由「检查连接」确认。

连接检查仅读取模型信息，不调用图片生成接口，也不会将凭据转发至重定向地址：

| 服务商 | 固定 API 地址 | 检查接口 | 已接入模型 |
| --- | --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | `GET /models/{model}` | 原有 OpenAI 图像模型 |
| 七七八 AI | `https://api.lk888.ai/v1` | `GET /models` | `tt-image-2`（按次）、`tt-image-2-token`（官转，按 token） |

检查通过只说明可读取所选模型信息，不能证明图片生成权限、账户余额或图片质量。模型列表权限或七七八 AI 的密钥 IP 白名单也可能影响检查。API 地址为后端固定映射，控制台地址 `https://ai778.cc/api/console` 不能当作 API 地址填入。

前台已经接入真实生图：顾客确认后使用上传原图、后台英文风格提示词与机型构图要求调用图片编辑接口。确认页显示实际服务商，提交同时校验服务商；若期间后台切换，要求刷新重新确认，且不扣生成次数。已经排队的任务保留原服务商及模型，并只读取那家服务商的密钥。

两家均调用 `POST /images/edits`。七七八 AI 按文档使用单图 multipart 字段 `image`，请求 `1024x1536`、medium、`response_format=b64_json`，不发送该模型不支持的 `background` / `output_format`。结果在服务端校验并转为 PNG 后私有保存；不下载接口意外返回的任意远程图片 URL。实际输出分辨率由渠道决定。保存 Key 不会自动触发生图；配置页展示最近一次真实生图的服务商与结果。详见 [真实 AI 生图](live-ai-generation.md)。

## 存储与部署

- 依赖 `cryptography`，版本锁定在 `backend/requirements.txt`。迁移 `0005_ai_service_config` 新增单例配置表；`0011_ai_relay_provider` 增加服务商、其他服务商的加密配置及任务服务商快照。升级执行 `backend/.venv/bin/python backend/manage.py migrate`。旧配置及历史任务默认归属 OpenAI，原密钥保留。
- 生产通过 `AI_CONFIG_ENCRYPTION_KEY` 环境变量提供独立 Fernet 主密钥（32 字节随机数的 URL-safe Base64）。不要复用 Django SECRET_KEY、OpenAI Key，也不要将其放入前端、Git 或日志。
- 配置表当前密钥及 `provider_profiles` 中非当前服务商的密钥均使用认证加密；接口只返回状态、末尾四位和检查时间。审计仅记录操作名称，不包含明文、密文或请求正文。配置接口禁止缓存，写操作要求 Session + CSRF。
- 开发环境首次启动自动生成 `backend/.local-ai-encryption-key`，权限 0600，已加入 Git 忽略；生产缺少有效主密钥时禁止保存/使用 API Key。
- 主密钥必须跨发布保持不变，和数据库一起进行受限备份。替换或丢失主密钥会使原密文无法解密，需重新填写 API Key；不要在每次发布时重新生成。
- 测试服务器主密钥位于 root-only `/etc/aicase/backend.env`，既有备份脚本同时备份该文件和数据库。密钥不进入 Web 发布目录。限流目前使用单进程缓存，多实例需共享限流设施。

## 验证

新增自动测试覆盖超级管理员限制、CSRF、密文存储、响应及日志脱敏、空值保留、清除、并发版本冲突、加密配置异常、固定服务地址、禁止重定向、上游错误脱敏和检查限流。外部请求均模拟，不使用真实 API Key。新增覆盖跨服务商切换及清除、密钥隔离、排队任务服务商保持、服务商变更后的重新确认、第三方参数及响应解析。本次未提供七七八 AI Key，未验证真实出图或余额。

参考：[OpenAI API 身份验证](https://developers.openai.com/api/reference/overview)、[图像生成模型](https://developers.openai.com/api/reference/resources/images/methods/generate)、[读取模型信息](https://developers.openai.com/api/reference/resources/models/methods/retrieve)、[Fernet](https://cryptography.io/en/latest/fernet/)。文档核对日期：2026-10-27。

第三方依据：[七七八 AI 图片接口文档](https://ai778.cc/apidoc#model/tt-image-2)、[控制台](https://ai778.cc/api/console)。第三方文档核对日期：2026-10-30。文档将旧 `gpt-image-2` / `gpt-image-2-guan` 标识对应到 `tt-image-2` / `tt-image-2-token`；本项目发送新的标识，并在连接检查中兼容列表返回的旧标识。
