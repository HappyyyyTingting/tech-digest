# tech-digest

Grok 每天搜索 X 上的科技动态，写成 Markdown 日报，提交到这个仓库。

当前是**阶段 1**：只验证 `Grok → GitHub` 的写入链路。邮件发送在阶段 2 再加。

## 仓库结构

```
digests/
  2026-10-23.md      # Grok 每天写一份，文件名用日期
  _TEMPLATE.md       # 格式示例，不会被当成日报
scripts/             # 阶段 2 的 Markdown → 邮件工具
```

## 阶段 1 步骤

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
你是一个科技情报编辑。搜索过去 24 小时 X 上科技、AI、开发者社区最重要的动态，
生成一份中文日报。

使用 GitHub connector，把日报写入仓库 HappyyyyTingting/tech-digest 的
digests/<当天日期，格式 YYYY-MM-DD>.md，直接 commit 到 main 分支。

格式必须严格如下：

# 科技日报 YYYY-MM-DD

> 一句话总结今天最重要的趋势

## 今日要闻

### 1. 标题

2–3 句中文摘要，把关键信息写在正文里。

[原帖](https://x.com/...)

### 2. 标题

2–3 句中文摘要。

[原帖](https://x.com/...)

要求：
- 最多 8 条，按重要性排序
- 每条必须有中文摘要和原帖链接
- 不要只给链接，不要写“继续阅读 / Continue Reading”
- 不要修改仓库里的其他文件
- 不要创建 PR，直接提交到 main
- 如果当天文件已存在，覆盖它
- commit message 使用 "digest: YYYY-MM-DD"
```

### 5. 手动跑一次验证

在 automation 页面点 **Run now**，然后检查：

1. 打开 <https://github.com/HappyyyyTingting/tech-digest/commits/main>
2. 应该看到一条 `digest: 2026-10-23` 的提交
3. 点开 `digests/2026-10-23.md`，确认格式和内容完整
4. 回到 Grok 的 run history，确认这次运行没有报错

如果成功，阶段 1 就完成了。

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

## 阶段 2（待做）

阶段 2 会加一个 GitHub Actions workflow：

```
digests/YYYY-MM-DD.md
  → scripts/render_email.py
  → 响应式 HTML + 纯文本
  → SMTP / Resend
  → 你的邮箱（完整正文）
```

阶段 1 验证通过后再做，避免把两个问题混在一起排查。
