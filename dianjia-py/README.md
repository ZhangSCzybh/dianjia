# Dianjia AI Memory System

这是一个 Markdown-first 的个人知识库 MVP。程序代码位于当前 `dianjia-py` 目录，知识库默认使用相邻目录 `/Users/zhangshichao/Documents/Workspace/dianjia`，SQLite 索引位于 `data/dianjia.db`。

## 快速开始

在项目目录执行：

```bash
cd /Users/zhangshichao/Documents/Workspace/dianjia-py

python -m app.main init                  # 初始化目录和 SQLite 表，不覆盖已有正文
python -m app.main rebuild-index         # 扫描 03_Memory，重建 SQLite 索引和 INDEX.md
```

## 每日使用流程

### 1. 导入对话

```bash
python -m app.main ingest /path/to/notes.md          # 导入单个 Markdown/TXT 到 00_Inbox
python -m app.main ingest notes.md --date 2026-08-27 # 导入并指定记录日期
python -m app.main ingest-dir ~/Documents/chats     # 批量导入 .md/.markdown/.txt 文件
cat today.md | python -m app.main ingest -           # 从标准输入导入文本
```

文件名中包含 `YYYY-MM-DD` 时，`ingest-dir` 会自动使用该日期；否则使用当天日期。相同内容会通过 SHA-256 自动跳过。

### 2. 生成每日总结

```bash
python -m app.main daily                          # 只生成日报，不处理长期记忆
python -m app.main daily --date 2026-08-27         # 为指定日期生成日报
```

输出文件：`01_Daily/YYYY/MM/YYYY-MM-DD.md`。`daily` 只读取当天的 `00_Inbox`，不会生成候选 JSON，也不会新增长期记忆。

### 3. 提取候选记忆

```bash
python -m app.main memory extract                   # 从今天的日报提取候选记忆
python -m app.main memory extract --date 2026-08-27 # 从指定日期日报提取候选
python -m app.main extract                           # 上一命令的兼容简写
```

输出文件：`02_Candidate/YYYY-MM-DD-candidates.json`。候选记忆仍待判断，不会直接写入 `03_Memory`。

### 4. 处理候选记忆

```bash
python -m app.main memory process                    # 处理最近生成的候选文件
python -m app.main memory process 2026-08-27-candidates.json # 处理指定候选文件
python -m app.main process                            # 上一命令的兼容简写
```

当前离线 MVP 使用本地启发式规则：没有相似记忆时创建新记忆，有相似标题时追加更新。结果写入 `03_Memory`，并记录到 SQLite 的 `memory_actions`。

### 5. 一键执行每日流程

```bash
python -m app.main run-daily                      # daily + memory extract + memory process
python -m app.main run-daily --date 2026-08-27     # 一键处理指定日期
```

`run-daily` 会依次生成日报、提取候选、创建或更新长期记忆，最后更新 SQLite 索引和 `INDEX.md`。因此，`daily` 适合只整理记录；`run-daily` 适合每天工作结束后完成完整沉淀。

## 查询和维护

```bash
python -m app.main search "SQL"                   # 按标题、标签、分类和摘要搜索
python -m app.main search "SQL" --limit 20        # 最多返回 20 条结果
python -m app.main ask "我之前遇到过类似的 SQL 问题吗？" # 检索知识库后回答问题
python -m app.main ask "ClickHouse 日期怎么处理？" --limit 5 # 检索关联度最高的记忆（最多 5 条）
python -m app.main ask "会员销售归类" --context-only  # 只查看 RAG 上下文，不调用 AI
python -m app.main show MEMORY_ID                  # 查看某条记忆的完整 Markdown
python -m app.main rebuild-index                   # Markdown 改动后同步 SQLite 和 INDEX.md
python -m app.main status                          # 查看 sources、memories、actions 数量
python -m app.main --help                           # 查看所有顶层命令
python -m app.main memory --help                    # 查看 memory 子命令
```

`python main.py ...` 是 `python -m app.main ...` 的等价简写。

## Web 控制台

启动本地网页界面：

```bash
python main.py web                    # 默认地址 http://127.0.0.1:8765
python main.py web --port 9000        # 使用其他端口
```

打开终端输出的地址即可操作。页面提供对话导入、日报生成、候选提取、长期记忆处理、索引重建、关键词搜索和 RAG 问答；所有操作使用与 CLI 相同的知识库和 SQLite 数据。

### 页面操作说明

1. **系统状态**：查看原始记录、长期记忆和处理记录数量。点击“刷新状态”同步最新数量；Markdown 文件被手动修改后点击“重建索引”。
2. **导入对话**：将聊天记录粘贴到文本框，填写记录名称和日期（日期可留空），点击“导入”。内容会保存到 `00_Inbox`，重复内容会自动跳过。
3. **每日处理**：填写处理日期（留空表示今天）。点击“生成日报”只生成 `01_Daily` 文件；点击“提取候选”生成 `02_Candidate` JSON；点击“处理记忆”将候选创建或更新到 `03_Memory`。
4. **一键处理**：点击“一键处理”完成日报、候选提取、长期记忆处理和索引更新，适合每天工作结束后使用。
5. **知识库问答**：输入问题后点击“检索并回答”。系统会先检索相关 Markdown 记忆，再调用 `.env` 中配置的 AI；回答下方会显示参考记忆。AI 不可用时仍会显示检索上下文。
6. **记忆搜索**：输入关键词点击“搜索”，按标题、标签、分类和摘要查找长期记忆。

### 推荐日常操作

```text
启动 Web 控制台
→ 粘贴并导入当天对话
→ 点击“一键处理”
→ 在“知识库问答”中提问
```

关闭终端会停止 Web 服务；重新使用时再次执行 `python main.py web`。Web 控制台只监听本机 `127.0.0.1`，不会自动对外网开放。

## RAG 对话

`ask` 是对话入口。它会先对问题和每条 Markdown 记忆生成本地向量，按余弦相似度排序，同时给标题、标签、分类命中的记忆加分，然后只取关联度最高的 Top 5（即使传入更大的 `--limit` 也不会超过 5 条）。再读取这些 `03_Memory` Markdown 正文，将其作为历史上下文交给 AI。回答末尾会列出实际使用的参考记忆。

当前使用的是无外部依赖的本地哈希 n-gram embedding，适合个人知识库和离线运行。检索会从问题动态提取中文主题短语和英文实体作为约束，不再维护固定主题列表；例如问题包含“会员”时，候选正文必须真实出现会员主题词，避免商品成本等无关记忆混入结果。后续可以将同一检索接口替换为真正的远程 embedding 模型，SQLite 和 Web 入口无需改变。

配置 AI API 后启用自动回答（请以服务商提供的 OpenAI-compatible Chat Completions 端点为准）：

```bash
export AI_API_KEY=your_api_key
export AI_BASE_URL=https://api.openai.com/v1  # 可替换为任意 OpenAI-compatible 服务
export AI_MODEL=gpt-5
python -m app.main ask "我之前如何处理库存唯一键问题？"
```

没有配置 `AI_API_KEY` 时，`ask` 仍会运行检索并打印上下文；可以先用 `--context-only` 检查召回内容，再配置模型。

### API 报错排查

- `HTTP 401/403`：Key 无效、无权限，或模型不属于该服务商。检查 `AI_API_KEY`、`AI_MODEL` 和服务商控制台权限。
- `HTTP 404`：通常是 `AI_BASE_URL` 路径不对。OpenAI-compatible 服务一般要求填写到 `/v1`，程序会请求 `${AI_BASE_URL}/chat/completions`。
- `无法连接 AI API`：检查域名、网络和代理设置。可以先运行 `python -m app.main ask "问题" --context-only`，确认本地检索正常。

API 不可用时，程序会保留 RAG 检索结果并输出 Markdown 上下文，不会丢失问题或知识库内容。

## 目录说明

- `00_Inbox`：原始导入记录
- `01_Daily`：每日总结
- `02_Candidate`：待判断候选记忆
- `03_Memory`：长期记忆，Markdown 是事实来源
- `06_Archive`：归档内容
- `INDEX.md`：知识导航索引
- `data/dianjia.db`：搜索、关系和操作历史索引

## 路径配置

```bash
export DIANJIA_KNOWLEDGE_ROOT=/path/to/dianjia # 覆盖知识库路径
export DIANJIA_DATA_ROOT=/path/to/data         # 覆盖 SQLite 数据路径
```
