# Dianjia Knowledge Base

这是 Dianjia 的 Markdown 知识库和长期记忆事实来源。程序、Web 控制台、CLI 和 API 配置说明位于项目 [dianjia-py](dianjia-py/README.md)；本文件只定义知识库的治理规则、数据格式和处理流程。

## 核心原则

1. 原始对话、日报、候选记忆和长期记忆是不同层级，不能混用。
2. Markdown 是事实来源；SQLite 只保存索引、检索和关系数据，可通过扫描 Markdown 重建。
3. AI 负责理解、提取和判断；Python 负责校验、文件写入、归档和数据库更新。
4. 新知识写入长期记忆前，必须检索已有记忆。优先 `update` 或 `merge`，避免重复创建。
5. 长期记忆必须脱离当天对话后仍然可理解、可检索、可复用。
6. 不确定内容可以保留，但必须标记待验证，不能作为已确认事实描述。
7. AI 不能直接选择任意文件路径、修改 Markdown 或执行数据库写入。

## 目录和职责

```text
dianjia/
├── 00_Inbox/       原始 Source 内容
├── 01_Daily/       每日总结 Markdown 和 JSON
├── 02_Candidate/   待判断、待确认和冲突候选
├── 03_Memory/      长期记忆，Markdown 事实来源
├── 04_Weekly/      周总结预留目录
├── 05_Monthly/     月总结预留目录
├── 06_Archive/     版本、迁移和历史归档（含 General 等已归档分类）
└── INDEX.md         自动生成的知识导航
```

`03_Memory` 按一级分类组织，例如 `SQL`、`BI`、`Testing`、`AI`、`Projects`。AI 提取候选时会优先复用已有分类；只有没有合适分类时才建议新分类。新分类仅在候选最终执行 `create`、写入长期记忆时才会正式创建目录。AI 不可用时，程序仍按内置关键词规则分类。分类名应稳定、明确，并避免同义目录重复。

## 完整数据流

```text
文件 / Web 粘贴 / stdin / 未来聊天导出
→ Source Adapter
→ Source 标准化与 SHA-256 去重
→ 00_Inbox + SQLite.sources
→ Daily Summary
→ Daily JSON + Daily Markdown
→ Memory Extractor
→ CandidateMemory JSON
→ Top 5 Existing Memories
→ Memory Judge
→ MemoryDecision
→ Python 执行器
→ Markdown + SQLite + Archive + Relations + INDEX.md
```

### 1. Source

所有输入必须先转换为统一 Source。它至少包含：

```text
source_id
source_type      file / web / stdin / chat_export
title
content
source_date
origin_path
content_hash
metadata
created_at
```

系统会标准化文本换行并以 SHA-256 去重，然后写入 `00_Inbox` 和 `sources` 表。不要仅手动将文件复制进 `00_Inbox`，否则不会生成可追踪的 Source 记录。

### 2. Daily Summary

Daily 读取某一天的 Source，输出：

```text
01_Daily/YYYY/MM/YYYY-MM-DD.json
01_Daily/YYYY/MM/YYYY-MM-DD.md
```

Daily JSON 是机器处理依据，字段包括：

```json
{
  "date": "2026-08-28",
  "source_ids": ["..."],
  "completed": [],
  "problems": [],
  "knowledge": [],
  "projects": [],
  "tomorrow": []
}
```

Markdown 是面向阅读的日报。AI 可用时生成结构化总结；AI 不可用时使用本地模板，流程仍可继续。

### 3. CandidateMemory

Extractor 只负责发现可能值得保存的知识，不决定最终归档操作。每项候选至少包含：

```json
{
  "title": "",
  "category": "",
  "subcategory": "",
  "tags": [],
  "summary": "",
  "content": "",
  "source_date": "",
  "source_ids": [],
  "category_action": "existing",
  "category_reason": "",
  "category_confidence": 0.0,
  "score": {
    "reusability": 0,
    "importance": 0,
    "uniqueness": 0,
    "stability": 0,
    "personal_relevance": 0
  },
  "total_score": 0
}
```

候选文件保存为 `02_Candidate/YYYY-MM-DD-candidates.json`。`category_action` 为 `existing` 时必须复用已有分类；为 `new` 时表示 AI 建议的新分类，Python 会校验名称安全性，并且只在最终 `create` 时创建对应目录。`local_fallback` 表示 AI 不可用或分类输出无效后，已使用本地关键词规则。候选评分用于判断和排序，不代表 AI 可以绕过 Judge 直接写入长期记忆。

评分规则：

| 总分 | 默认含义 |
|---:|---|
| 0-11 | 通常没有长期价值，倾向 `discard` |
| 12-16 | 有价值但证据或稳定性不足，倾向 `candidate` |
| 17-20 | 适合长期记忆，交由 Judge 决定 create/update/merge |
| 21-25 | 高价值核心记忆，仍需经过检索和 Judge |

实现约束：`total_score` 始终由五项评分之和计算，不能使用 AI 单独返回的不一致总分。AI Judge 即使返回 `create`，当总分低于 12 时也会自动降级为 `candidate`，保留在候选区待复核，不直接写入长期记忆。

### 4. Retrieve

每个 Candidate 先检索已有长期记忆，返回最多 Top 5：

```text
动态主题锚点过滤
→ 英文实体精确匹配
→ 本地 embedding 余弦相似度
→ 标题、标签、分类、摘要关键词加权
→ 关联度排序
→ Top 5 Existing Memories
```

新业务主题不需要维护固定关键词列表。问题中的中文主题短语和英文实体会动态成为检索约束；低相关记忆不应仅因为通用词或向量碰撞进入上下文。

### 5. Memory Judge

Judge 的输入是 `CandidateMemory + Top 5 Existing Memories`。AI 只返回 `MemoryDecision` JSON，Python 对其校验后才执行：

```json
{
  "action": "update",
  "target_memory_id": "existing-memory-id",
  "reason": "候选内容补充了已有规则",
  "confidence": 0.9,
  "total_score": 22,
  "changes": {
    "summary": "",
    "content": "",
    "tags_to_add": []
  },
  "merge_memory_ids": []
}
```

允许动作：

| 动作 | 含义 |
|---|---|
| `create` | 新建长期记忆 |
| `update` | 补充或修正指定已有记忆 |
| `merge` | 合并多个高度重叠的记忆 |
| `candidate` | 保留为待确认候选 |
| `discard` | 丢弃临时、重复或低价值内容 |
| `conflict` | 标记与已有记忆冲突，等待人工确认 |

`update` 和 `merge` 必须携带真实存在的 `target_memory_id`；`confidence` 必须在 0 到 1；`total_score` 必须在 0 到 25。AI 不可用时，系统使用本地 create/update/candidate 兜底规则。

## 长期记忆格式

每个 `03_Memory` 文件必须有 YAML frontmatter：

```yaml
---
id: sql-debug-membership-store-join-001
title: 会员销售归类异常：品牌 15056
category: SQL
subcategory: SQL问题排查
tags:
  - 会员分类
  - LEFT JOIN
summary: 跨店会员被误归类时，应检查会员维表是否错误限制销售门店。
status: active
verification_status: verified
memory_level: core_memory
score: 24
created_at: 2026-08-27
updated_at: 2026-08-27
source_dates:
  - 2026-08-27
---
```

字段规则：

- `id`：稳定唯一，不因标题变更而变化。
- `status`：`active` 或 `archived`。只有 `active` 记忆参与检索。
- `verification_status`：`verified` 或 `pending`。待验证记忆仍可检索，但回答时应避免将其表述为已确认事实。
- `tags`：保存业务名词、字段名、规则名和常用别名，帮助新主题检索。
- `summary`：一到两句可独立理解的结论。
- `source_dates`：记录事实来源日期；详细来源关系保存在 SQLite 的 `memory_sources`。

正文建议维持以下结构：

```markdown
# 标题

## 一句话结论

## 问题 / 场景

## 核心结论

## 使用方法

## 示例或验证依据

## 关联记忆
```

一条记忆只表达一个核心知识点。若两个主题独立，应拆分；若内容高度重叠，应由 `merge` 合并。

## 执行、归档和关系

### Create

```text
创建 03_Memory/<category>/<id>.md
→ 写入 memories
→ 写入 memory_sources
→ 更新 INDEX.md
```

### Update

```text
读取旧 Markdown
→ 复制旧版本到 06_Archive/versions/<memory_id>/
→ 写入更新内容和元数据
→ 更新 memories 与 memory_sources
→ 更新 INDEX.md
```

### Merge

```text
更新目标记忆
→ 归档目标的旧版本
→ 将被合并记忆标记为 archived（保留原 Markdown 作为历史记录）
→ 写入 memory_relations (merged_from)
→ 更新 INDEX.md
```

### Candidate、Conflict、Discard

```text
candidate → 02_Candidate/pending-*.json
conflict  → 02_Candidate/conflicts-*.json
discard   → 不写长期记忆，只记录 memory_actions
```

`memory_actions` 记录每次决策、理由和候选载荷，用于审计“为什么创建、更新或丢弃”。

## INDEX 和恢复

`INDEX.md` 是人类导航，不是数据库。它由系统从 active Markdown 记忆自动生成，使用相对 Markdown 链接。不要手动将 `INDEX.md` 当作唯一索引维护。

当 SQLite 丢失、Markdown 被手动修改，或完成批量迁移后，执行项目中的 `rebuild-index` 重建索引。旧版无 frontmatter 的长期记忆可通过 `migrate-legacy` 自动迁移；迁移前的原文件快照位于 `06_Archive/migrations/`。已合并、废弃的分类历史文件可放在 `06_Archive/<category>/`（例如 `06_Archive/General/`），这些文件不参与 active 记忆索引。

## RAG 使用规则

用户提问时：

```text
问题
→ 动态主题与实体提取
→ Top 5 长期记忆检索
→ 读取 Markdown 上下文
→ AI 基于历史记忆回答
→ 返回参考记忆
```

回答必须区分：

- 历史记忆中已确认的事实；
- `verification_status: pending` 的待验证信息；
- 历史记忆没有覆盖时的通用推测。

不能把检索不到的信息伪装成历史经验，也不应为了凑 Top 5 而加入低相关记忆。

## 操作说明

请参阅 [dianjia-py README](dianjia-py/README.md)，其中包含 CLI、Web 控制台、`.env`、RAG API、迁移命令和故障排查说明。 


By 再也不会
