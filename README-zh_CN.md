# Octopus Agent

桌面 + CLI 双模式 AI 编码与通用智能体客户端，具备**治理框架**。

对标 Claude Desktop、Claude Code CLI、Codex 和 Hermes 智能体能力。一个独立的、受治理框架约束的智能助手，面向普通用户和开发者。

## 核心差异化：治理框架

所有 AI 输出、文件操作、Shell 执行和代码编写行为都经过治理层的**拦截、验证和约束**：

- **权限引擎** — 4 种模式：手动、接受编辑、计划、自动
- **文件系统沙箱** — AI 只能在授权目录内操作（CubeSandbox MicroVM 或本地）
- **Shell 命令治理** — 安全命令允许执行，危险命令需要审批
- **完整行为审计** — 每个操作都记录到 SQLite 供审查
- **任务回滚** — 一键恢复到任何之前的文件状态
- **钩子系统** — 4 种钩子类型（Python、Command、HTTP、Prompt），支持热重载
- **凭证管理** — 使用机器派生密钥的加密存储

## 快速开始

```bash
# 从源码安装
git clone https://github.com/Asamo096/Octopus-Agent.git
cd Octopus-Agent
pip install -e ".[dev]"

# 配置提供商
octopus cli
/config set provider openai
/config set api_key sk-your-key-here
/config set base_url https://api.openai.com/v1
/model                    # 使用方向键选择模型

# 或使用 litellm 原生提供商
/config set provider xiaomi_mimo
/config set api_key your-key-here
/model

# 开始聊天
❯ 写一个 Python 排序算法
```

## 使用模式

### 交互式 CLI

```bash
octopus cli                           # 启动交互式会话
octopus cli -c <session-id>           # 恢复会话
octopus cli --model gpt-4o            # 使用特定模型
octopus cli --permission-mode auto    # 设置权限模式
```

### 单次提示

```bash
octopus cli "用 Python 写一个 hello world"
octopus cli "修复 main.py 中的 bug"
```

### 代码智能体

```bash
octopus code init           # 初始化工作区
octopus code fix            # 扫描并修复 bug
octopus code test           # 生成单元测试
octopus code refactor       # 重构代码库
octopus code logs           # 查看审计日志
```

## 权限模式

| 模式 | Shell | 写/读/删除 | 使用场景 |
|------|-------|-----------|----------|
| **手动** | 请求批准 | 请求批准 | 不可信代码，审查所有操作 |
| **接受编辑** | 阻止 | 允许 | 代码审查，允许编辑但不允许执行 |
| **计划** | 阻止 | 允许 | 规划，允许文件操作但不允许执行 |
| **自动** | 允许 | 允许 | 可信环境，完全自动化 |

在会话中使用 `Shift+Tab` 切换模式。

## 会话内命令

| 命令 | 描述 |
|------|------|
| `/help` | 显示帮助 |
| `/model` | 获取并选择模型（方向键） |
| `/config show` | 显示当前配置 |
| `/config set model <m>` | 设置模型名称 |
| `/config set provider <p>` | 设置提供商名称 |
| `/config set base_url <u>` | 设置提供商基础 URL |
| `/config set api_key <key>` | 设置 API 密钥 |
| `/tokens` | 显示 token 估算 |
| `/compact` | 强制对话压缩 |
| `/reset` | 重置对话 |
| `/exit` | 退出 |

## 配置

配置文件存储在 `~/.octopus/`：

### auth.json（API 密钥）

```json
{
  "OPENAI_API_KEY": "sk-...",
  "ANTHROPIC_API_KEY": "sk-ant-..."
}
```

### config.toml（提供商设置）

```toml
model_provider = "openai"
model = "gpt-4o"
model_reasoning_effort = "high"

[model_providers.openai]
name = "OpenAI"
base_url = "https://api.openai.com/v1"
wire_api = "chat_completions"
requires_openai_auth = true
```

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                    入口: `octopus`                       │
├──────────────────────┬──────────────────────────────────┤
│   CLI 层 (Typer)     │   GUI 层 (Tauri + React)         │
│   - 交互式模式       │   - 聊天面板                     │
│   - 代码命令         │   - 终端 (xterm.js)              │
│   - 会话管理         │   - 侧边栏导航                   │
├──────────────────────┴──────────────────────────────────┤
│              共享核心: octopus-core                      │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌───────────┐  │
│  │ 治理    │ │  智能体  │ │   工具    │ │  LLM      │  │
│  │ 内核    │ │  系统    │ │  系统     │ │ 提供商    │  │
│  └─────────┘ └──────────┘ └───────────┘ └───────────┘  │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌───────────┐  │
│  │ 权限    │ │  审计    │ │  记忆     │ │  沙箱     │  │
│  │ 引擎    │ │  日志    │ │  系统     │ │ (Cube)    │  │
│  └─────────┘ └──────────┘ └───────────┘ └───────────┘  │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌───────────┐  │
│  │  钩子   │ │  回滚    │ │   认证    │ │  插件     │  │
│  │  管理   │ │  引擎    │ │  存储     │ │  系统     │  │
│  └─────────┘ └──────────┘ └───────────┘ └───────────┘  │
├─────────────────────────────────────────────────────────┤
│  SQLite（持久状态 + 审计）+ WebSocket（IPC）              │
└─────────────────────────────────────────────────────────┘
```

## 功能特性

### 智能体循环
- 思考-行动-观察循环，支持并行工具执行
- 自动压缩：微压缩、上下文折叠、响应式压缩
- 会话持久化：跨重启恢复对话
- 可配置的最大轮次限制和预算控制

### 多智能体系统
- 进程内智能体协调器，支持并行/顺序执行
- 内置智能体定义：通用、探索者、审查者、规划者
- 后台工作智能体，支持每个工作智能体的预算控制
- 基于 Markdown 和 YAML 前置元数据的智能体定义

### 记忆系统
- 跨会话持久记忆，存储为 Markdown 文件
- 基于 TF 的相关性评分，带重要性和时效性加权
- 记忆类型：用户、反馈、项目、参考
- 会话记忆压缩与事实提取

### 钩子系统（4 种类型）
- **Python** — 异步回调钩子
- **Command** — Shell 执行，支持 `$ARGUMENTS` 和环境变量注入
- **HTTP** — 向外部服务发送 webhook POST
- **Prompt** — 基于 LLM 的验证
- 配置文件更改时热重载
- 默认钩子：权限检查、回滚检查点、审计日志

### 技能系统
- 基于 Markdown 的技能定义，带 YAML 前置元数据
- 技能发现：内置、用户、项目目录
- 参数替换（`$ARGUMENTS`、`$1`、`$2` 等）
- 每个技能的工具限制

### 沙箱隔离
- **CubeSandbox** — 硬件隔离的 KVM MicroVM（冷启动 < 60ms）
- **本地** — CubeSandbox 不可用时的子进程回退
- 文件读写、命令执行、快照、回滚

### 响应处理
- 为不支持函数调用的提供商解析 XML 工具调用
- 代码块检测和执行
- 裸 Shell 命令检测
- 思考块剥离
- 模型工件清理
- 按工具类型渲染输出（语法高亮、面板）

### 重试与错误处理
- 指数退避（10 次重试，0.5s-32s）
- 429/529 速率限制处理
- 提示过长响应式压缩
- 孤立的 tool_use/tool_result 清理

## 工具（14 个）

| 工具 | 描述 |
|------|------|
| `read_file` | 读取文件内容，支持偏移/限制 |
| `write_file` | 写入文件，自动创建父目录 |
| `edit_file` | 基于字符串的查找/替换编辑 |
| `glob` | 文件模式匹配 |
| `grep` | 跨文件正则内容搜索 |
| `shell` | Shell 命令执行（受治理） |
| `git` | Git 操作（status、diff、log、commit 等） |
| `diff` | 统一差异生成 |
| `git_diff` | 暂存/未暂存更改的 Git diff |
| `web_search` | 通过 DuckDuckGo 进行网络搜索 |
| `web_fetch` | 获取 URL 内容 |
| `code_search` | 工作区正则搜索 |
| `mcp` | MCP 服务器工具桥接 |
| `agent` | 生成子智能体（通过协调器） |

## 技术栈

| 层 | 技术 |
|----|------|
| GUI | Tauri 2.x + React + TypeScript |
| CLI | Typer + Rich + prompt-toolkit |
| LLM | litellm（100+ 提供商） |
| 数据 | Pydantic v2 + SQLite (aiosqlite) |
| 沙箱 | CubeSandbox (KVM MicroVM) |
| 记忆 | 带 YAML 前置元数据的 Markdown 文件 |
| 认证 | Fernet 加密 (cryptography) |
| 测试 | pytest + pytest-asyncio |
| 代码检查 | ruff + mypy |

## 开发

```bash
# 安装依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 代码检查
ruff check src/ tests/

# 格式化
ruff format src/ tests/

# 类型检查
mypy src/
```

## 实现阶段

| 阶段 | 状态 | 内容 |
|------|------|------|
| 阶段 1（第 1-4 周） | 完成 | 内核、智能体循环、工具、CLI |
| 阶段 2（第 5-8 周） | 完成 | 配置、提供商、Tauri GUI、IPC 桥接 |
| 阶段 3（第 9-14 周） | 完成 | 回滚引擎、插件系统 |
| 阶段 4（第 15-20 周） | 完成 | 上下文、压缩、记忆、钩子、多智能体、沙箱、认证、MCP |
| 阶段 5（第 21-26 周） | 完成 | claude-code 模式：技能、文件缓存、预算、工作智能体 |

## 许可证

MIT 许可证 — 详见 [LICENSE](LICENSE)。

## 致谢

- [OpenHarness](https://github.com/HKUDS/Openarness) (HKUDS) 提供参考架构
- [claude-code](https://github.com/anthropics/claude-code) (Anthropic) 提供 CLI 模式
- [CubeSandbox](https://github.com/TencentCloud/CubeSandbox) (腾讯云) 提供硬件隔离沙箱
- Claude Desktop、Claude Code CLI、Codex 和 Hermes 提供灵感
