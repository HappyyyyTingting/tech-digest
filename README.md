# tech-digest

Grok 每天搜索 X 上的科技股市动态，写成面向新手的 Markdown 日报，提交到这个仓库；GitHub Actions 再把完整日报渲染成邮件发到邮箱。

当前已经打通：

- **阶段 1**：`Grok → GitHub`（每天写入 `digests/YYYY-MM-DD.md`）
- **阶段 2**：`GitHub → 邮件`（Actions 自动渲染完整正文并发送）

```
Grok Automation（每天 07:30）
  → 写入 digests/YYYY-MM-DD.md
  → GitHub Actions（push 触发）
  → scripts/send_email.py
  → 响应式 HTML + 纯文本
  → 邮箱（完整正文，无「继续阅读」）
```

> 日报内容仅供学习参考，不构成投资建议。

## 仓库结构

```
.github/workflows/
  send-email.yml     # push 到 digests/*.md 时自动发邮件
digests/
  2026-10-23.md      # Grok 每天写一份，文件名用日期
  _TEMPLATE.md       # 格式示例，不会被当成日报
scripts/
  send_email.py      # Markdown → 响应式邮件 + 纯文本，并发送
tests/
  test_send_email.py # 渲染、主题、纯文本、SMTP / Resend 测试
requirements.txt     # mistune
```

## 阶段 1：Grok → GitHub（已完成）

### 1. 在 GitHub 创建空仓库

在 <https://github.com/new> 创建：

- Owner：`HappyyyyTingting`
- Repository name：`tech-digest`
- Visibility：**Public**（公开仓库的 Actions 免费；日报内容本来就是公开新闻）
- **不要**勾选 "Add a README file"、".gitignore"、license

创建后得到：

```
https://github.com/HappyyyyTingting/tech-digest
```

### 2. 把本地骨架推上去

在本地终端执行：

```bash
cd /Users/tingtingyu/tingting/tech-digest
git remote add origin https://github.com/HappyyyyTingting/tech-digest.git
git add .
git commit -m "chore: init tech-digest repository"
git push -u origin main
```

### 3. 连接 Grok 的 GitHub connector

1. 打开 <https://grok.com/connectors>
2. 找到 **GitHub**，点击连接
3. 在 GitHub 授权页选择 **Only select repositories**
4. 只勾选 `HappyyyyTingting/tech-digest`
5. 确认给予 **write** 权限（Grok 需要提交文件）

授权范围越小越好，不要选 "All repositories"。

### 4. 创建 Grok Automation

打开 <https://grok.com/automations>，新建一个 automation：

- **Schedule**：每天一次，建议设在早上 07:30（Asia/Shanghai），给阶段 2 的邮件任务留时间
- **Delivery**：先选 app notification 或 none（阶段 1 不需要邮件）
- **Prompt**：复制下面这段

```text
你是一个面向股市新手的科技情报编辑。请生成一份「科技股市入门日报」，
用中文 Markdown 输出，语言通俗易懂。

## 数据来源与写入方式

1. 搜索过去 24 小时 X 上关于科技巨头和半导体/AI 产业链的重要动态。
   优先使用高互动、可信的 X 帖子，其次使用可靠媒体、公司公告或财报。
2. 使用 GitHub connector，把完整日报写入仓库 HappyyyyTingting/tech-digest 的
   digests/<当天日期，格式 YYYY-MM-DD>.md，直接 commit 到 main 分支。
3. 写入前先尝试读取仓库 digests/ 目录下最近几天的文件，确认「今日入门小课堂」
   昨天讲过什么，今天讲下一个概念，避免重复。如果读不到历史文件，就按常见
   入门顺序选一个，并在小课堂开头注明。
4. 不要修改仓库里的其他文件；不要创建 PR；如果当天文件已存在，覆盖它。
5. commit message 使用 "digest: YYYY-MM-DD"。
6. 写入成功后只回复一句「已写入 digests/YYYY-MM-DD.md」，不要把全文再贴一遍。
   如果写入失败，说明失败原因，不要假装成功。

## 日报结构

# 科技股市入门日报 YYYY-MM-DD

> 一句话总结今天科技股和产业链最重要的变化。

### 一、今日重要新闻

列出过去 24 小时内最重要的 4–7 条新闻，覆盖科技巨头和关键细分行业。

覆盖方向：
- 科技巨头：Apple、Microsoft、Google、NVIDIA、Meta、Amazon、Tesla 等
- 关键细分行业：芯片/半导体、存储（DRAM/NAND）、AI 大模型、先进封装、
  半导体设备、AI 算力相关等

每条包含：
- 简要标题
- 核心内容总结（2–3 句，把关键信息写清楚，不要只给链接）
- 来源（优先 X 上的高互动帖子或可靠信息，附链接）

### 二、新闻解读（小白版）

用最简单的语言解释这些新闻可能对相关公司和行业意味着什么：
- 这件事偏利好还是偏利空？为什么？
- 对短期和中期可能有什么影响？
- 普通人需要注意什么信号？

要求：
- 用「可能」「偏利好/偏利空」这样的表述，不要给出确定性预测
- 解释清楚逻辑，避免专业术语堆砌

### 三、关键数据速览

简要列出主要公司和行业相关的核心数据：
- 股价变动、市值、近期涨跌幅
- 行业景气指标（如存储价格、AI 算力需求、半导体设备出货等）

要求：
- 优先使用过去 24 小时内可核实的数据，注明数据时间和来源
- 如果拿不到可靠数据，就写「数据暂缺」，不要编造
- 用通俗的方式说明这些数字代表什么

### 四、今日入门小课堂

每天只讲 1 个基础知识点，从入门开始，循序渐进。

可讲的主题例如：
- 什么是市盈率（PE）？
- 什么是市值？
- 什么是财报？
- 美联储加息/降息对科技股有什么影响？
- 芯片行业常见术语：先进制程、HBM、CoWoS 等

要求：
- 先看仓库里最近几天的日报，避免重复昨天讲过的概念
- 用生活化的例子解释，控制在 300 字以内

### 五、给初学者的小建议

针对今天的新闻和数据，给出 1–2 条适合股市新手的观察建议或学习方向。

要求：
- 只给观察和学习建议，不要给具体买卖建议
- 语言简单、可执行

---

文末加一句：以上内容仅供学习参考，不构成投资建议。

## 总体要求

- 全文控制在 3000 字以内，适合手机阅读
- 不要写「继续阅读 / Continue Reading」，不要要求点开链接才能看到正文
- 忽略明显广告、营销号和低质内容
- 所有新闻和数字都要有来源；不确定的信息要明确标注
- 输出完整内容，不要省略任何一节
```

### 5. 手动跑一次验证

在 automation 页面点 **Run now**，然后检查：

1. 打开 <https://github.com/HappyyyyTingting/tech-digest/commits/main>
2. 应该看到一条 `digest: 2026-10-23` 的提交
3. 点开 `digests/2026-10-23.md`，确认格式和内容完整
4. 回到 Grok 的 run history，确认这次运行没有报错

如果成功，阶段 1 就完成了。

## 阶段 2：GitHub → 邮件

### 它是怎么工作的

1. Grok 把当天日报 commit 到 `main` 的 `digests/YYYY-MM-DD.md`。
2. `Send digest email` workflow 被 push 触发。
3. workflow 只找出本次新增/修改的 `digests/*.md`，逐个执行 `scripts/send_email.py`。
4. 脚本取第一个 H1 作为邮件主题，把正文完整转成响应式 HTML，同时生成纯文本版本。
5. 通过 Resend API 或 SMTP 发到 `MAIL_TO`。

正文不会被截断，也没有「Continue Reading」。`_TEMPLATE.md` 永远不会被发送。

### 1. 选择邮件服务并准备账号

#### 方案 A：Resend（最省事，推荐先用这个）

1. 打开 <https://resend.com> 注册（可以用你的 Foxmail 邮箱注册）。
2. 在 **API Keys** 页面创建一个 key，权限选 `Sending access` 即可。
3. 测试阶段可以直接用 `onboarding@resend.dev` 作为发件人；它只能发到 Resend 账号注册邮箱。
4. 如果要发到其他地址或长期使用，在 Resend 里验证自己的域名，然后把 `MAIL_FROM` 改成 `日报 <digest@你的域名>`。

对应 secrets：

| Secret | 值 |
|---|---|
| `EMAIL_PROVIDER` | `resend`（可选；设置了 `RESEND_API_KEY` 会自动选 Resend） |
| `RESEND_API_KEY` | `re_...` |
| `MAIL_FROM` | `onboarding@resend.dev` 或已验证域名下的地址 |
| `MAIL_TO` | 收件邮箱，多个用英文逗号分隔 |

#### 方案 B：SMTP（QQ / Foxmail / 163 / SMTP2GO 等）

以 Foxmail / QQ 邮箱为例：

1. 登录 QQ 邮箱网页版 → 设置 → 账号 → 开启 **SMTP 服务**。
2. 按提示生成 **授权码**。注意：SMTP 密码填授权码，不是 QQ 登录密码。
3. 服务器填写 `smtp.qq.com`，端口 `465`，加密方式 `ssl`。
4. `SMTP_USER` 和 `MAIL_FROM` 都填完整邮箱地址。

对应 secrets：

| Secret | 示例 |
|---|---|
| `EMAIL_PROVIDER` | `smtp` |
| `SMTP_HOST` | `smtp.qq.com` |
| `SMTP_PORT` | `465` |
| `SMTP_SECURITY` | `ssl`（465）或 `starttls`（587） |
| `SMTP_USER` | `your-name@foxmail.com` |
| `SMTP_PASSWORD` | 授权码 |
| `MAIL_FROM` | `your-name@foxmail.com` |
| `MAIL_TO` | 收件邮箱 |

> GitHub Actions 的服务器在海外，QQ/Foxmail 可能因为异地登录触发风控。如果日志里出现 `SMTP 登录失败` 或连接超时，优先改用 Resend；也可以换 SMTP2GO、Mailgun 等服务。

### 2. 在 GitHub 添加 Secrets

打开仓库：

`Settings → Secrets and variables → Actions → New repository secret`

把上表里的名字和值逐个添加。`MAIL_TO` 和 `MAIL_FROM` 是必填；`MAIL_REPLY_TO` 可选。

注意：

- Secrets 不会出现在公开仓库里，也不会被 workflow 日志打印。
- 不要把邮箱授权码、API key 写进 README、Markdown 或代码。
- 如果使用 Resend 的 `onboarding@resend.dev`，收件人必须是 Resend 账号注册邮箱；否则会报 403。

### 3. 先做一次不发送的测试（可选）

`Actions → Send digest email → Run workflow`

- `file` 留空 = 使用最新一份日报
- 勾选 `dry_run` = 只渲染，不发邮件
- 运行结束后在该次 run 页面底部下载 `email-preview` artifact，打开 `email_preview.html` 检查排版

### 4. 发一封真实测试邮件

再次 `Run workflow`，`file` 留空，`dry_run` 不勾选。运行成功后：

1. 检查收件箱和垃圾邮件。
2. 点开邮件，确认五个小节和来源链接都在。
3. 在手机上打开，确认是单栏、字号可读。

### 5. 之后就是自动的

Grok 每天写入 `digests/YYYY-MM-DD.md` 后，push 会自动触发 workflow 并发邮件。可以在 `Actions` 页面看到每次运行记录。

### 本地预览和本地发送

```bash
cd /Users/tingtingyu/tingting/tech-digest
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 只生成预览，不发送
.venv/bin/python scripts/send_email.py --file digests/2026-10-23.md --dry-run
open email_preview.html

# 本地真实发送（环境变量只放在当前终端，不要提交）
export MAIL_TO='your@email.com'
export MAIL_FROM='onboarding@resend.dev'
export RESEND_API_KEY='re_...'
.venv/bin/python scripts/send_email.py --latest
```

本地发送也支持 SMTP，把上面的 Resend 变量换成 `SMTP_*` 即可。

### 运行测试

```bash
.venv/bin/python -m unittest discover -s tests -v
```

### 邮件渲染规则

- 邮件主题：日报第一个 `# ` 标题；没有标题时用「科技股市入门日报 + 日期」。
- 正文：完整 Markdown 转 HTML，保留标题、列表、表格、引用和来源链接。
- 纯文本：同时生成 `text/plain` 版本，纯文本客户端也能读。
- 样式：单栏、最大宽度 640px、16px 字号、1.75 行高、移动端媒体查询。
- 安全：Markdown 里的原始 HTML 会被转义；`javascript:` / `data:` 等危险链接会被拦截。
- 大小：超过约 90KB 会在日志里警告（正常 3000 字日报约 10KB），不会截断。

## 常见问题

### Grok 说没有权限 / 无法写入

- 回到 <https://grok.com/connectors> 重新授权 GitHub
- 确认选的是 **Only select repositories** 并且勾了 `tech-digest`
- 确认给了 write 权限
- 如果仓库开了分支保护，允许 connector 直接提交，或改成提交到新分支

### 提交到了 `master` 而不是 `main`

新仓库默认分支通常是 `main`。如果 Grok 提交到了别的分支，在 GitHub
仓库的 Settings → Branches 里把默认分支改成 `main`，或把 prompt 里的分支名改成实际分支。

### 文件路径不对

Grok 必须写到 `digests/YYYY-MM-DD.md`。如果它写到了根目录，检查 prompt 是否完整复制。

### 公开仓库安全吗

- 日报内容来自公开的 X 帖子，公开没有问题
- 不要把 API key、邮箱密码、个人隐私写进 Markdown
- 阶段 2 的 secrets 存在 GitHub Actions Secrets 里，不会出现在公开仓库
- 工作流日志只打印日报路径、主题和邮件大小，不打印密码或 API key

### 推送后 workflow 没有运行

- 确认改动的是 `digests/*.md`，不是根目录或其他路径
- 打开仓库的 `Actions` 页面，看 `Send digest email` 是否有运行记录
- 如果仓库长期没有活动，GitHub 可能暂停定时任务；本 workflow 由 push 触发，不受 60 天限制
- 如果 Grok 通过 GitHub App 提交，push 事件通常会触发；如果确实没有，使用 `workflow_dispatch` 手动补发
- 检查仓库 `Settings → Actions → General` 是否允许 Actions 运行

### 日志提示缺少配置

脚本会明确列出缺少的变量，例如：

```
错误：缺少 SMTP 配置：SMTP_HOST, SMTP_USER, SMTP_PASSWORD
```

回到 `Settings → Secrets and variables → Actions` 补齐即可。注意 secret 名称必须完全一致。

### Resend 返回 403

- 测试域名 `onboarding@resend.dev` 只能发送到 Resend 账号注册邮箱
- 如果要发给其他地址，先在 Resend 验证自己的域名，再用该域名下的发件地址
- 确认 API key 有 `Sending access` 权限

### SMTP 登录失败

- QQ / Foxmail / 163 的 SMTP 密码是 **授权码**，不是网页登录密码
- 确认邮箱设置里已经开启 SMTP 服务
- 465 端口配 `SMTP_SECURITY=ssl`；587 端口配 `starttls`
- 海外 GitHub runner 可能触发邮箱风控，换 Resend 通常最省事

### 邮件在垃圾箱里

- 把发件人加入联系人
- 使用 Resend 并验证自己的域名，配置 SPF / DKIM，送达率会明显更好
- 测试阶段用 `onboarding@resend.dev` 时，部分邮箱会把它当陌生发件人

### 收到了旧日报或重复邮件

- push 触发只发送本次改动/新增的 `digests/*.md`
- 手动 `workflow_dispatch` 留空 `file` 时会发送最新一份，不判断是否已经发过
- 如果同一天 Grok 覆盖了日报，会再发一次更新版，这是预期行为
- 想避免重复，可以在手动触发时指定具体文件，或之后加一个“已发送”状态文件

### 想改收件人或发件人

改 GitHub Secrets 里的 `MAIL_TO` / `MAIL_FROM` 即可，不需要改代码。多个收件人用英文逗号分隔。

### 想调整邮件样式

编辑 `scripts/send_email.py` 里的 `_email_css()` 和 `wrap_email_html()`，然后运行本地预览确认。改完 push 后，下一次日报会自动使用新样式。
