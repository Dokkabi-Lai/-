# Render + Supabase 免费部署

该方案会生成可直接分享的 HTTPS 地址。应用运行在 Render，账号、投递记录和岗位存入 Supabase PostgreSQL，头像存入 Supabase Storage，因此重新部署后不会丢失。

## 1. 创建 Supabase 项目

1. 在 https://supabase.com 创建项目。
2. 在 Storage 新建名为 `avatars` 的 Public bucket。
3. 在 Project Settings → API 复制 Project URL 和 `service_role` key。
4. 在 Database → Connect 复制 PostgreSQL URI，优先选择 Session pooler，并在末尾增加 `?sslmode=require`。

不要把数据库密码或 `service_role` key 写入代码或提交到 Git。

## 2. 创建飞书自建应用

1. 在飞书开放平台创建企业自建应用。
2. 为应用开通“查看、评论、编辑和管理电子表格”相关权限并发布版本。
3. 将应用添加为目标表格协作者。
4. 记录 App ID、App Secret、电子表格分享链接以及工作表 ID。工作表 ID 可留空，程序会读取第一个工作表。

表格至少需要“公司”和“岗位”两列。投递链接建议使用完整的 `https://` 文本。

## 3. 部署 Render

1. 把仓库推送到 GitHub。
2. 登录 https://render.com，选择 New → Blueprint。
3. 连接该仓库；Render 会读取根目录的 `render.yaml`。
4. 填写以下环境变量：

```text
DATABASE_URL=Supabase PostgreSQL URI
ADMIN_EMAILS=你的注册邮箱
SUPABASE_URL=Supabase Project URL
SUPABASE_SERVICE_ROLE_KEY=Supabase service_role key
SUPABASE_STORAGE_BUCKET=avatars
FEISHU_APP_ID=飞书 App ID
FEISHU_APP_SECRET=飞书 App Secret
FEISHU_SPREADSHEET_TOKEN=飞书表格完整链接
FEISHU_SHEET_ID=工作表 ID（可留空）
FEISHU_SYNC_ENABLED=true
```

`JWT_SECRET` 由 Blueprint 自动生成。不要在部署后随意更换，否则所有用户需要重新登录。

## 4. 首次使用

1. 打开 Render 提供的 `https://xxx.onrender.com` 地址。
2. 使用 `ADMIN_EMAILS` 中的邮箱注册；首次启动会自动创建“默认岗位群”并迁入旧岗位。
3. 群主在群组菜单中绑定飞书表格，再到岗位库点击“从飞书同步”进行首次导入。
4. 群主复制邀请链接发给朋友。每个群共享自己的岗位库，但投递、收藏、Pass、日历和个人资料互相隔离。

## 免费层说明

- Render 长时间无人访问会休眠，首次打开可能等待几十秒。
- Supabase 免费项目长期无活动时可能暂停，进入 Supabase 控制台可恢复。
- 免费实例默认不安装 Chromium，因此动态网页 JD 抓取不可用；岗位表和飞书同步不受影响。

## 5. Supabase 连接串详细配置

进入 Supabase 项目，点击顶部 Connect：

1. 选择 Session pooler，不要选择 Transaction pooler。
2. 复制 URI，端口通常为 `5432`。
3. 把 `[YOUR-PASSWORD]` 替换成创建项目时的数据库密码。
4. 在末尾添加 `?sslmode=require`。

示例结构：

```text
postgresql://postgres.PROJECT_REF:URL编码后的密码@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require
```

如果密码包含 `@`、`#`、`/`、`:` 等字符，需要先做 URL 编码。最省事的方式是重置成由字母、数字和下划线组成的强密码。不要使用 6543 Transaction pooler，否则 SQLAlchemy 可能遇到连接或 prepared statement 问题。

应用首次启动会自动创建表和执行轻量迁移，不需要在 Supabase SQL Editor 手动建表。

## 6. Supabase 头像存储详细配置

1. 打开 Storage → New bucket。
2. Bucket 名填写 `avatars`。
3. 勾选 Public bucket；否则上传成功后浏览器也无法显示头像。
4. 打开 Project Settings → API：
   - Project URL 填入 Render 的 `SUPABASE_URL`
   - `service_role` key 填入 `SUPABASE_SERVICE_ROLE_KEY`

`service_role` 拥有高权限，只能保存在 Render Environment，不能写进前端、截图公开或提交 Git。头像最大 3MB，支持 JPG、PNG、WebP 和 GIF。

## 7. Render Blueprint 逐步操作

1. 将代码推到 GitHub 仓库。
2. 登录 Render，点击 New → Blueprint。
3. 连接 GitHub，选择仓库和需要部署的分支。
4. Render 识别到 `render.yaml` 后，确认创建 `autumn-application-tracker` Web Service。
5. 在提示中逐一填写 `sync: false` 的变量。
6. 点击 Apply，等待 Docker 构建和健康检查。
7. 部署完成后打开 `https://你的服务名.onrender.com/api/health`，应看到：

```json
{"status":"ok","job_count":0}
```

`job_count` 首次为 0 是正常的，绑定飞书或录入岗位后会增加。`JWT_SECRET` 由 Render 自动生成，不要删除或更换，否则所有用户需重新登录。

完整变量：

```text
DATABASE_URL=带 sslmode=require 的 Supabase Session pooler URI
ADMIN_EMAILS=你的邮箱,另一个管理员邮箱
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=Supabase service_role key
SUPABASE_STORAGE_BUCKET=avatars
FEISHU_APP_ID=飞书自建应用 App ID
FEISHU_APP_SECRET=飞书自建应用 App Secret
FEISHU_SYNC_ENABLED=true
FEISHU_SYNC_HOUR=6
FEISHU_SYNC_MINUTE=0
TZ=Asia/Shanghai
```

飞书表格链接由各群群主在网站内绑定，不必再统一放进 `FEISHU_SPREADSHEET_TOKEN`。旧默认群仍兼容该环境变量。

## 8. 飞书应用和群组绑定

1. 飞书开放平台 → 创建企业自建应用。
2. 权限管理中搜索“电子表格”，开通读取电子表格所需权限。
3. 创建并发布应用版本。
4. 在目标飞书表格的协作者设置中添加该应用。
5. 将 App ID 和 App Secret 填进 Render 环境变量并重新部署。
6. 网站中进入群组菜单 → 飞书设置，粘贴表格完整链接。
7. 群主开启每日自动同步并保存。

每个群可以绑定不同表格。同步按“公司、岗位、地点、批次、链接”去重；飞书删除的岗位会在对应群中下架，不会删除成员已有的历史投递。

飞书/Excel 推荐字段顺序：

```text
公司 | 公司类型 | 批次 | BASE | 岗位 | 岗位JD | 投递链接 | 开始日期 | 截止日期 | 投递机制 | 内推码 | 记录时间
```

## 9. 群组与现有数据迁移

- 已有岗位自动进入“默认岗位群”。
- 已有账号自动成为默认群成员，最早的管理员作为群主。
- 新注册账号自动加入默认群，之后可通过邀请链接加入其他群。
- 群内岗位共享；Application、JobMark、日历和个人资料仍按用户保存。
- 如果从本地 SQLite 迁移到 Supabase，需要另行导出旧数据库；仅重新部署代码不会自动搬运本机数据库内容。

## 10. 常见问题

### Render 健康检查失败

优先查看 Render Logs。常见原因是数据库密码错误、密码未 URL 编码，或连接串缺少 `sslmode=require`。

### 头像上传失败

确认 bucket 名与 `SUPABASE_STORAGE_BUCKET` 一致、bucket 为 Public，并且填写的是 `service_role` 而不是 anon key。

### 飞书提示无权限

确认应用版本已经发布、权限已审批，并且应用已被添加为目标表格协作者。

### 第一次打开很慢

Render 免费服务会休眠，唤醒通常需要几十秒。这不会影响 PostgreSQL 和头像持久化。

### 部署后数据消失

检查 Render 是否设置了 `DATABASE_URL`。若未设置，应用会回退到容器内 SQLite，而 Render 免费容器重启后本地文件会消失。

