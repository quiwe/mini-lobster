---
name: self-improving-agent
description: "捕获学习、错误和纠正，实现持续改进。适用场景：(1) 命令或操作意外失败，(2) 用户纠正你，(3) 用户请求不存在的功能，(4) 外部 API 或工具失败，(5) 发现知识过时或有误，(6) 发现更好的方法"
---

# 自我改进技能

将学习、错误和纠正记录到 markdown 文件，实现持续改进。

## 快速参考

| 情况 | 操作 |
|------|------|
| 命令/操作失败 | 记录到 `.learnings/ERRORS.md` |
| 用户纠正你 | 记录到 `.learnings/LEARNINGS.md`，分类 `correction` |
| 用户请求缺失功能 | 记录到 `.learnings/FEATURE_REQUESTS.md` |
| API/外部工具失败 | 记录到 `.learnings/ERRORS.md` |
| 知识过时 | 记录到 `.learnings/LEARNINGS.md`，分类 `knowledge_gap` |
| 发现更好方法 | 记录到 `.learnings/LEARNINGS.md`，分类 `best_practice` |

## 首次使用初始化

在记录任何内容之前，确保项目根目录存在 `.learnings/` 目录及文件：

```bash
mkdir -p .learnings
[ -f .learnings/LEARNINGS.md ] || printf "# Learnings\n\nCorrections, insights, and knowledge gaps captured during development.\n\n**Categories**: correction | insight | knowledge_gap | best_practice\n\n---\n" > .learnings/LEARNINGS.md
[ -f .learnings/ERRORS.md ] || printf "# Errors\n\nCommand failures and integration errors.\n\n---\n" > .learnings/ERRORS.md
[ -f .learnings/FEATURE_REQUESTS.md ] || printf "# Feature Requests\n\nCapabilities requested by the user.\n\n---\n" > .learnings/FEATURE_REQUESTS.md
```

不要覆盖已存在的文件。如果 `.learnings/` 已初始化则此操作无效果。

**不要记录** secrets、tokens、私钥、环境变量或完整的源/配置文件，除非用户明确要求。优先使用简短摘要或脱敏片段，而非原始命令输出或完整转录。

## 日志格式

### 学习记录

追加到 `.learnings/LEARNINGS.md`：

```markdown
## [LRN-YYYYMMDD-XXX] category

**Logged**: ISO-8601 时间戳
**Priority**: low | medium | high | critical
**Status**: pending
**Area**: frontend | backend | infra | tests | docs | config

### Summary
一句话描述学到了什么

### Details
完整上下文：发生了什么、哪里错了、正确答案是什么

### Suggested Action
具体修复或改进

### Metadata
- Source: conversation | error | user_feedback
- Related Files: path/to/file.ext
- Tags: tag1, tag2
- See Also: LRN-YYYYMMDD-XXX（如与已有条目相关）
```

### 错误记录

追加到 `.learnings/ERRORS.md`：

```markdown
## [ERR-YYYYMMDD-XXX] skill_or_command_name

**Logged**: ISO-8601 时间戳
**Priority**: high
**Status**: pending
**Area**: frontend | backend | infra | tests | docs | config

### Summary
简要描述失败内容

### Error
```
实际错误消息或输出
```

### Context
- 尝试的命令/操作
- 使用的输入或参数
- 环境详情（如相关）

### Suggested Fix
如可识别，提供可能的解决方案

### Metadata
- Reproducible: yes | no | unknown
- Related Files: path/to/file.ext
- See Also: ERR-YYYYMMDD-XXX（如重复发生）
```

### 功能请求

追加到 `.learnings/FEATURE_REQUESTS.md`：

```markdown
## [FEAT-YYYYMMDD-XXX] capability_name

**Logged**: ISO-8601 时间戳
**Priority**: medium
**Status**: pending
**Area**: frontend | backend | infra | tests | docs | config

### Requested Capability
用户想要做什么

### User Context
为什么需要它，要解决什么问题

### Complexity Estimate
simple | medium | complex
```

## ID 生成格式

`TYPE-YYYYMMDD-XXX`
- TYPE: `LRN`（学习）、`ERR`（错误）、`FEAT`（功能）
- YYYYMMDD: 当前日期
- XXX: 序号或随机3位字符（如 `001`、`A7B`）

## 状态更新

解决问题后更新条目：
- `**Status**: pending` → `**Status**: resolved`
- 添加 Resolution 块：
```markdown
### Resolution
- **Resolved**: 2025-01-16T09:00:00Z
- **Notes**: 简要描述做了什么
```

其他状态：`in_progress`（正在处理）、`wont_fix`（决定不处理）、`promoted`（提升到项目文档）

## 提升到项目文档

广泛适用的学习内容应提升到永久项目文档：

| 学习类型 | 提升到 |
|---------|--------|
| 项目事实、约定俗成 | `MEMORY.md` |
| 工作流和自动化 | `MEMORY.md` 相关章节 |
| 工具使用注意 | `MEMORY.md` 相关章节 |

### 何时提升
- 学习适用于多个文件/功能
- 任何贡献者（人类或 AI）都应知道
- 防止重复犯错
- 记录项目特定约定

### 如何提升
1. **提炼**为简洁的规则或事实
2. **添加**到目标文件的适当章节
3. **更新**原条目：`**Status**: pending` → `**Status**: promoted`

## 自动检测触发

自动记录你注意到的内容：

**纠正**（→ 分类为 `correction` 的学习）：
- "No, that's not right..."
- "Actually, it should be..."
- "You're wrong about..."
- "That's outdated..."

**功能请求**（→ 功能请求）：
- "Can you also..."
- "I wish you could..."
- "Why can't you..."

**知识缺口**（→ 分类为 `knowledge_gap` 的学习）：
- 用户提供了你不知道的信息
- 引用的文档已过时
- API 行为与理解不符

**错误**（→ 错误记录）：
- 命令返回非零退出码
- 异常或堆栈跟踪
- 超时或连接失败

## 优先级指南

| 优先级 | 使用场景 |
|--------|---------|
| `critical` | 阻塞核心功能、数据丢失风险、安全问题 |
| `high` | 重大影响、影响常见工作流、重复问题 |
| `medium` | 中等影响、有变通方法 |
| `low` | 小麻烦、边缘情况、可选改进 |

## 定期回顾

在自然断点回顾 `.learnings/`：
- 开始新的重要任务前
- 完成一个功能后
- 在有历史学习的领域工作时

### 快速状态检查
```bash
# 统计待处理项
grep -h "**Status**: pending" .learnings/*.md | wc -l

# 列出待处理高优先级项
grep -B5 "Priority**: high" .learnings/*.md | grep "^## "
```

## 最佳实践

1. **立即记录** - 上下文在问题发生后最清晰
2. **具体描述** - 未来的 agent 需要快速理解
3. **包含复现步骤** - 对错误尤为重要
4. **链接相关文件** - 使修复更容易
5. **提供具体修复建议** - 不只是"调查"
6. **使用一致的分类** - 便于过滤
7. **积极提升** - 有疑问时添加到 MEMORY.md
8. **定期回顾** - 过时的学习失去价值
