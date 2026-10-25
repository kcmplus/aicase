# 图片展示与原图

用户端与后台共用 `frontend/storefront/image-view.js`。保存的设计、订单和图库记录仍引用原始图片路径；只在显示时选择 WebP 预览，不改变订单图片内容或重新压缩用户订单照片。

## 静态素材

运行 `npm run images:build`（使用 backend/.venv 中锁定的 Pillow）。脚本从原始素材生成 320 / 640 / 1280 像素宽度的预览，不放大小图，长图限制高度 2560；透明度保留，EXIF 方向校正，有效颜色配置转换为 sRGB。WebP 质量 86，属于有损展示压缩，原图不删除。品牌图只提取原有字标区域，避免下载整张品牌画板。

预览文件名含内容摘要，输出至 `assets/optimized/`，并生成 `image-manifest.js`。将预览和清单一起加入 Git、一起发布。重新生成不删除旧预览，避免已有引用失效。

2026-10-25 基线：26 张原图共 68,201,644 字节，对应最大预览共 6,746,984 字节，减少 90.1%。例如宠物原图从 2,934,515 字节变为 640 像素预览 149,610 字节或 320 像素缩略图 48,524 字节。此数据比较文件体积，不代表网速或页面时间固定提升倍数。

## 后台上传

后台继续接收最大 10 MB、2000 万像素的 JPG / PNG / WebP。读取后保存完整分辨率、去除 EXIF 的标准 PNG，同时生成上述预览及元数据。`path` 仍是原图；`image_variants` 是可选的展示元数据，随上传、管理记录和公开案例接口返回。无预览的旧图片自动回退到原路径。

已有公开图库上传可运行 `python manage.py optimize_library_images` 补齐预览。命令只处理 `MEDIA_ROOT/uploads/`，幂等，不处理订单数据库里的私人照片，不更改任何图库记录。

## 加载和缓存

`srcset` / `sizes` 让浏览器按照显示尺寸、像素密度选择图片；尺寸属性预留布局空间。图库缩略图、案例对比和非首屏图片使用浏览器原生 `loading=lazy`，异步解码。编辑主图立即加载，品牌图预加载；折叠的 AI 案例区在展开前不请求图片。

Nginx 对含内容摘要的 `assets/optimized/` 和 `media/previews/` 返回一年 immutable 缓存。入口 HTML、JS、CSS 和 API 仍使用现有更新策略，不对价格、订单或私人照片增加公共缓存。新图片产生新 URL，避免旧缓存遮盖更新。

验证：前端资源存在性、格式、压缩比例、设计不可变性及恶意元数据回退；后端上传权限、EXIF、透明度、完整分辨率、不同尺寸、公开/管理接口和补齐命令；本地浏览器检查折叠区未请求、展开加载 WebP 及 390 像素布局。

参考：[浏览器原生懒加载](https://web.dev/articles/browser-level-image-lazy-loading)、[响应式图片](https://web.dev/learn/design/responsive-images)、[Pillow 图像方向处理](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html#PIL.ImageOps.exif_transpose)。
