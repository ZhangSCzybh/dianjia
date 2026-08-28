# Dianjia AI Memory System

这是“店家”个人知识库的本地操作程序：负责导入对话、生成日报、提取并归档长期记忆、检索和 RAG 问答。知识库 Markdown 位于相邻目录 [dianjia](../dianjia)，默认 SQLite 索引位于本项目的 `data/dianjia.db`。

本 README 说明如何运行程序；目录规范、Source/Candidate/Decision 数据格式、归档规则和完整治理流程以 [dianjia/README.md](../dianjia/README.md) 为唯一准则。使用其他 AI 协助归档时，也应先让它阅读该文件。

## 快速开始

```bash
cd /Users/zhangshichao/Documents/Workspace/dianjia-py
python main.py init
python main.py web
```

浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。`init` 只创建缺失目录和 SQLite 表，不覆盖现有知识内容。首次接手已有 Markdown 知识库时，再执行一次 `python main.py rebuild-index`。

`python main.py ...` 与 `python -m app.main ...` 完全等价；下文使用前者，命令行偏好者可以直接替换。

## Web 控制台

Web 是日常使用的主入口。页面中的所有功能与 CLI 共用同一套知识库、SQLite 索引和处理规则。

```bash
python main.py web                 # 默认监听 127.0.0.1:8765，仅本机可访问
python main.py web --port 9000     # 使用其他端口
```

推荐每天按以下顺序操作：

1. 在“导入对话”粘贴当天的完整对话或工作记录，填写容易识别的记录名称；日期留空即使用当天。
   Web 导入框最多接受 100,000 个字符，界面会实时显示计数；后端也会再次校验，超限内容不会写入知识库。
2. 点击“导入”。内容会进入 `00_Inbox`，相同内容会自动去重。
3. 点击“一键处理”。Web 会立即返回任务并在页面轮询进度；后台依次生成日报、候选记忆、判断归档动作并更新索引。即使 AI 请求较慢，也不会因浏览器等待超时而丢失任务。
4. 在“知识库问答”输入问题。系统先检索最高相关的长期记忆，再将这些内容交给 AI 回答。

页面也提供分步操作：

- “生成日报”：仅从当天 `00_Inbox` 生成 `01_Daily`，不写长期记忆。
- “提取候选”：从日报生成待判断的 `02_Candidate` JSON，不写长期记忆。
- “处理记忆”：执行候选的创建、更新、合并、保留或丢弃决策。
- “重建索引”：手动改动 `03_Memory` Markdown 后，同步 SQLite 和 `INDEX.md`。
- “记忆搜索”：按关键词查找长期记忆；“知识库问答”用于先检索再生成自然语言答案。

关闭运行 `web` 的终端会停止服务；下次使用时再次启动即可。

## 常见场景

| 你要做什么 | 推荐操作 | 结果 |
| --- | --- | --- |
| 导入一段当天对话并完成归档 | Web：导入后点击“一键处理” | 日报、候选、长期记忆、索引依次更新 |
| 只整理当天记录，不写长期记忆 | Web：点击“生成日报” | 生成 `01_Daily` Markdown 和 JSON |
| 想检查 AI 会拿哪些知识回答 | `python main.py ask "问题" --context-only` | 只输出检索到的 Top 5 上下文，不调用 AI |
| 手动修改了长期记忆 Markdown | `python main.py rebuild-index` | 重建 SQLite 和 `INDEX.md` |
| 初次接入旧版知识库 | `python main.py migrate-legacy` | 补齐 frontmatter、保留迁移快照并重建索引 |
| AI API 报错 | 先运行 `ask ... --context-only` | 区分本地检索问题和 AI 服务问题 |

## 命令行操作

命令行适合批量导入、调试和自动化。所有命令均在项目目录执行。

### 导入原始记录

```bash
python main.py ingest /path/to/notes.md
python main.py ingest notes.md --date 2026-08-28
python main.py ingest-dir /path/to/chats
cat today.md | python main.py ingest -
```

- `ingest FILE`：导入一个 `.md`、`.markdown` 或 `.txt` 文件到 `00_Inbox`。
- `ingest-dir DIRECTORY`：批量导入目录内支持的文件；文件名包含 `YYYY-MM-DD` 时会自动识别日期。
- `ingest -`：从标准输入读取内容，便于接入脚本或管道。
- `--date YYYY-MM-DD`：显式指定记录日期；不传时为当天。

内容通过 SHA-256 去重，重复导入不会生成第二份 Source。

### 分步每日处理

```bash
python main.py daily --date 2026-08-28
python main.py memory extract --date 2026-08-28
python main.py memory process 2026-08-28-candidates.json
```

- `daily`：只读取指定日期（或当天）的 Source，生成日报 Markdown 与 JSON。
- `memory extract`：从日报提取 `CandidateMemory`，写入 `02_Candidate`，不直接写入长期记忆。
- `memory process [候选文件]`：对候选检索已有记忆并执行决策。省略文件名时处理最近生成的候选文件。
- `extract`、`process`：分别是 `memory extract`、`memory process` 的兼容简写。

```bash
python main.py run-daily --date 2026-08-28
```

`run-daily` 等价于连续执行 `daily`、`memory extract`、`memory process`。它会写入或更新长期记忆；与只生成日报的 `daily` 不同，适合在当天记录全部导入后使用。

`run-daily` 对 Source 按增量处理：首次运行会处理当天的新 Source；同一天再次运行时，未变化且已经完成处理（或已进入待复核）的 Source 会自动跳过，因此不会重复创建记忆、追加版本或写入处理动作。只有新导入的 Source、Source 文件内容发生变化的记录，或没有 `source_ids` 的手工候选，才会再次进入判断流程。日报和候选 JSON 仍可以每次重新生成，这是为了反映当天最新的 Inbox 内容。处理状态保存在 SQLite 的 `sources.processed_at`、`pipeline_status` 和 `last_candidate_hash` 字段中。

命令行会在终端（标准错误输出）显示实际模式，例如 `[daily] 使用 AI 总结`、`[extract] 使用本地兜底`、`[judge] AI 决策 2 条，本地规则 1 条`。因此不要只看最终的 `create/update` 结果；以这些阶段标记判断是否真正请求了 AI。`ask` 也会显示 `[ask] 使用 AI 回答` 或 `[ask] AI 失败，返回本地检索上下文`。

如果希望强制重新处理某个候选，可使用分步命令 `python main.py memory process <候选文件>`；该命令默认不启用 Source 增量跳过，会按候选文件执行一次处理。修改 Source 后重新运行 `run-daily`，程序会通过内容哈希检测变化并重新处理。

Web 的 `/api/run-daily` 使用异步任务模式：POST 后返回 `job_id`，再通过 `/api/run-daily/<job_id>` 查询 `running`、`completed` 或 `failed` 状态。命令行 `run-daily` 不变，仍会等待流程完成后再输出结果。

### 查询与维护

```bash
python main.py search "SQL" --limit 10
python main.py show MEMORY_ID
python main.py rebuild-index
python main.py migrate-legacy
python main.py status
python main.py --help
python main.py memory --help
```

- `search KEYWORD`：按标题、标签、分类和摘要搜索；`--limit` 控制显示数量。
- `show MEMORY_ID`：输出一条记忆的完整 Markdown。
- `rebuild-index`：以 `03_Memory` Markdown 为事实来源重建 SQLite 和 `INDEX.md`。
- `migrate-legacy`：仅为缺少 YAML frontmatter 的旧记忆补齐元数据。原文先备份到 `06_Archive/migrations/`，再重建索引。
- `status`：查看 Source、长期记忆和处理动作的数量。

## RAG 知识库问答

```bash
python main.py ask "我之前如何处理库存唯一键问题？"
python main.py ask "DRP 有相关问题吗？" --limit 5
python main.py ask "会员销售归类" --context-only
```

`ask` 先在 `03_Memory` 检索，再向 AI 提问。检索使用本地哈希 n-gram embedding、余弦相似度以及标题、标签、分类、摘要命中加权；会从问题动态提取中文主题和英文实体以过滤明显无关的内容。无论 `--limit` 传入多大，实际上下文最多使用关联度最高的 5 条记忆。

`--context-only` 不会访问 AI API，只显示将发送给 AI 的上下文，适用于检查“为什么命中这几条”。AI 不可用时，普通 `ask` 也会保留并输出已检索的上下文，因此检索结果不会丢失。

## AI 配置

在项目根目录创建 `.env`。程序启动时会自动读取它，无需手动 `export`；该文件已被 Git 忽略，不能提交或分享其中的 Key。

```env
AI_API_KEY=your_api_key
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-5
```

`AI_BASE_URL` 应填写服务商提供的 OpenAI-compatible 基础地址。程序会请求：

```text
${AI_BASE_URL}/chat/completions
```

为避免网关因请求过大主动断开连接，日报总结和候选提取发送给 AI 的单次上下文会限制在约 12 万字符；完整原始记录仍会保存在 `01_Daily`，不会被截断。若服务商返回 `RemoteDisconnected`、超时或其他连接错误，程序会自动切换本地兜底规则，`run-daily` 不会因此中断。

也可以通过同名环境变量临时覆盖 `.env`。AI 用于日报总结、候选提取、记忆判断和 RAG 回答；调用失败时，日报、提取和判断会改用本地兜底规则，问答则返回检索上下文与错误说明。候选提取的本地兜底会按每条原始 Source 合并为一条候选，清理 `<details>` 等对话包装，并依据内容自动归入 `SQL`、`BI`、`Testing`、`AI` 或 `Projects`；只有无法识别主题时才使用 `General`。

### API 排错

- `401` / `403`：检查 API Key、模型权限、账户额度以及服务商的域名访问限制。
- `404`：通常是基础地址不正确。不要在 `AI_BASE_URL` 中重复填写 `/chat/completions`。
- 无法连接：检查网络、代理和服务商地址；先用 `ask "问题" --context-only` 验证本地 RAG 是否正常。

## 与其他 AI 协作归档

其他 AI 可以协助整理对话，但不应绕过本程序直接臆造长期记忆。给它以下边界即可：

1. 先阅读 [dianjia/README.md](../dianjia/README.md)，遵守 Source、Candidate、Decision 和 Markdown frontmatter 规范。
2. 原始对话先作为 Source 放入 `00_Inbox`，不要直接覆盖 `03_Memory` 的既有正文。
3. 对新内容先形成 Candidate，再检索相近的 Top 5 记忆后提出 `create`、`update`、`merge`、`candidate`、`discard` 或 `conflict` 决策。
4. 需要更新时保留版本快照；不确定或互相矛盾时保留候选或冲突，不能把推测写成历史事实。
5. 修改长期记忆 Markdown 后执行 `python main.py rebuild-index`。

程序执行 `update` 时会将旧版本保存到 `06_Archive/versions/<memory-id>/`。执行 `merge` 时，被合并的来源记忆会在 SQLite 中标记为 `archived` 并建立关系记录，原 Markdown 仍作为可追溯的历史文件保留。

## 路径与边界

默认路径：

```text
程序：/Users/zhangshichao/Documents/Workspace/dianjia-py
知识库：/Users/zhangshichao/Documents/Workspace/dianjia
索引：/Users/zhangshichao/Documents/Workspace/dianjia-py/data/dianjia.db
```

需要切换知识库或索引位置时，可在 `.env` 或系统环境中设置：

```env
DIANJIA_KNOWLEDGE_ROOT=/path/to/dianjia
DIANJIA_DATA_ROOT=/path/to/data
```

目录职责如下：`00_Inbox` 保存原始 Source，`01_Daily` 保存每天总结，`02_Candidate` 保存待判断内容，`03_Memory` 保存长期知识事实，`06_Archive` 保存版本和迁移快照，`INDEX.md` 提供可读导航。SQLite 是搜索、关系和处理记录索引，删除后可通过 `rebuild-index` 从长期 Markdown 恢复。

完整数据流、数据字段和归档治理规则见 [dianjia/README.md](../dianjia/README.md)。
