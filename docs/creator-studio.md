# POPOMO 创作者 1.0 与美化组件交接

日期：2026-10-21。依据用户确认的三类内容逻辑；AI 运行方式明确为可操作模拟。

## 体验入口

- `#discover`：内容发现。整壳设计、照片、贴纸分类，搜索、分批加载、作者链接。
- `#creator?id=mika`、`noah`、`popomo`：三个示例创作者主页；不代表真实签约作者。
- `#content?id=case-daisy-day`：整壳内容详情，复制后进入 DIY。
- `#content?id=photo-meadow`：照片详情，添加为当前设计中的独立图层。
- `#studio`：可编辑图层、照片与贴纸、AI 模拟预览、交付入口。
- `#creator-workspace`：仅已分配创作身份的演示账户显示创作表单。消费者页面没有后台模式开关。

网站公开无需登录；“账户”中的演示登录只用于本机流程，无真实认证、权限控制、数据隔离或跨设备同步。

## 演示账号与流程

在右上角账户输入邮箱并选择手机型号，无密码、不会发送邮件：

| 邮箱 | 模拟职责 |
| --- | --- |
| `studio@popomo.demo` | 分配三个创作身份，可审核通过、退回修改、下架 |
| `mika@popomo.demo` | 仅 Mika 身份，可存草稿、提交审核 |
| `noah@popomo.demo` | 仅 Noah 身份，可存草稿、提交审核 |
| 其他邮箱 | 普通消费者，可 DIY、使用公开内容，不能发布 |

登录后从“账户 → 我的创作空间”，或工作台“保存到我的创作账号”进入。新建照片/贴纸可独立上传文件，也可选择内置示例素材；整壳设计保存当前工作台的图层快照。填写中文、英文标题后保存草稿 → 提交审核 → 使用审核演示账号通过并发布。已发布内容编辑后先保留旧公开版本，重新审核通过才增加版本号。下架内容不再被新引用；已完成的订单保留购买时快照。

此处“发布”只更新当前浏览器的演示内容库，不上传访客文件到公开网站。同一浏览器中可切换不同演示账号走完审核流程。真实多用户权限、审核和内容同步是后续研发工作。

## 三类内容与来源

`creator-core.js` 管理内容和演示身份。内容包含 `id/type/creatorId/version/status/zh/en`，其中 `type` 只允许 `photo/sticker/case`。照片、贴纸保存 `src`；整壳保存 `design`。本地内容位于 `ai-case-studio-v1` 状态的 `creator.drafts/published`。

- 照片/贴纸：在当前设计上增加图层，保留其他图层与背景。
- 整壳：独立深拷贝；通过撤销可恢复原个人作品。
- `design.source` 记录完整设计作者和版本；`layer.source` 分别记录所引用素材作者和版本。修改文字、拖动、复制图层、美化、购物车和订单快照保留来源。
- 不能把照片内的文字或图案自动拆成独立元素。模板中独立定义的文字和图案可以编辑；整张图片自身可移动、缩放、旋转。
- 私人上传照片不会自动成为公开内容，需创作账号显式保存、提交、发布。
- 内置示例素材归属只是演示账号分配，不是法定著作权声明。OpenMoji 贴纸沿用原署名和 CC BY-SA 4.0 说明。

## 素材扩充

模板从 16 款扩充为 28 款，贴纸从 12 款扩充为 24 款。新增 12 款模板包含春日、云朵、海浪、蝴蝶结、橘子、棋盘、星芒等；文字为独立文本层。保留旧 ID、收藏和本机已有设计，不强制覆盖旧作品。

新贴纸为项目原生 SVG，生成脚本：`scripts/make-creator-assets.mjs`。新增照片素材两张位于 `dist/assets/creator/`：

| 文件 | 生成来源 |
| --- | --- |
| `photo-meadow.png` | 内置 ImageGen，2026-10-21，原创照片风格花田素材 |
| `photo-coast.png` | 内置 ImageGen，2026-10-21，原创照片风格海岸素材 |

海岸提示词：Create one original portrait 2:3 photo-looking artwork for a DIY phone-case content library. A quiet sunlit Mediterranean coastline: turquoise water, pale peach sand, white surf, one small wildflower at the lower right, soft sunlight with warm film grain, calm minimal composition, plenty of open sea in the center. Real photographic aesthetic, no text, no logos, no borders, no phone mockup. Colorful but gentle, polished stock photo for a creative consumer platform.

花田生成源文件：`C:/Users/53671/.codex/generated_images/01a14393-879f-7803-8023-d16824cf1efa/exec-97926e3b-9c72-41e2-9754-6d69ab3a0a62.png`。项目已包含复制后的素材，无需依赖原机路径运行。两张素材是 AI 生成的照片风格内容，不是实物手机壳质量证明。

## AI 美化组件

可独立复用的模块：

- `dist/beautify-core.js`：`createBeautyPreview(design,{preset,intensity,layout})` 纯函数，返回深拷贝设计；`photoEffect()` 生成预览滤镜。
- `dist/beautify-ui.js`：`installBeautifier({app,getDesign,getModel,onApply,toast})`，委托监听 `data-beauty="open"` 按钮，返回 `open/close`。
- 样式：`dist/creator.css` 中 `beauty-*` 与 `#beautify-dialog`。

```js
installBeautifier({
  app,
  getDesign: () => state.design,
  getModel: () => state.model,
  onApply: design => {
    history.push(state.design); // 仅应用时记录一次撤销
    state.design = design;
    persist();
    render();
  },
  toast
});
```

提供清透自然、温暖胶片、品牌撞色三种方向和 0–100 强度，配色按强度混合，照片应用滤镜，轻排版只调整过于靠边的位置和旋转。无生成新图、自动抠图、自动拆层、印刷安全检测或实物预检能力。

预览/取消/失败不改变原设计；成功应用仍保留独立图层，可在工作台撤销。参数更改使旧预览失效；原设计变化后应用被拦截，需重新生成；离开页面取消待处理预览。演示选项可触发一次失败并重试。界面始终显示“模拟效果 / Simulated effect”，没有网络 AI 调用。

## 专用 Skill

项目交付源文件：`skills/popomo-template-studio/SKILL.md`。

已安装到原电脑：`C:/Users/53671/.codex/skills/popomo-template-studio/SKILL.md`。新会话加载；用于辅助制作可编辑素材和维护演示组件，不是网站访客运行时依赖。现有 `imagegen` 技能用于制作图片，未安装不相关第三方包。技术团队可将 skill 文件夹复制到自己的 Codex skills 目录。

## 不变业务边界

USD、默认手机型号、设备 ID 和机型/库存校验、单壳邮寄与设备即时打印保留。配件只邮寄、与手机壳合并后统一邮寄保留。营销券规则和价格仍为演示，不因引用创作者素材增加费用。2.0 签约作者邀请、合同与收益模块继续保留在独立方案中。

## 验证与后续研发

当前规则测试：39 项通过。浏览器共 92 项：新创作者/美化 13 项、专项修复回归 4 项、既有工作台 17 项、配件 22 项、营销 13 项、双语交付 11 项与并发结账重复验证 12 项通过。两种语言的新增页面覆盖 360/390/768/1440 宽度；原工作台和交易流程覆盖 1080 设备屏宽度。截图位于 `test-results/creator-*`、`test-results/beautify-*`。

正式研发需实现服务端身份与多创作身份分配、上传存储、内容版本和审核、来源及授权台账，以及真实 AI 服务适配；浏览器演示状态不得当作生产权限或数据存储。真实 AI 的费用、重试、任务状态与内容规则需另行确认。


最终独立审查的三项问题已修复，并补充先失败后通过的浏览器回归：发布标题按文本显示，创作表单切换语言保留身份和标题，已有草稿载入独立工作台副本并回存修改。专项回归还验证了旧美化预览不能覆盖新设计。完整验证脚本 `node scripts/verify-creator-release.mjs`；输出 `test-results/creator-release-verification.json`。

本轮回归还复现了跨标签页 localStorage 缓存延迟：两次相邻的支付锁回调读到相同未核销记录。新增 `payment-ledger.js`，在既有 Web Lock 内使用共享 IndexedDB 交易记录完成读取与写入，再同步本机状态；订单和优惠核销仍为模拟。记录按浏览器数据集 ID 隔离，清除本机演示状态会开始新的数据集。新并发检查连续运行 12 组双标签页付款，并校验仅一笔成功和一笔被拒绝。

## 社区互动补充

发现/作者页面新增瀑布流和详情弹层，支持点赞、收藏、关注、评论及一层回复。查看 [社区互动说明](community-interactions.md) 获取范围、数据接口、验证路径与生产研发要求。
