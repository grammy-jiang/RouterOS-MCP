# GitHub Copilot Coding Agent – Best Practices for High-Quality, Autonomous Work
# GitHub Copilot Coding Agent 高效使用最佳实践

---

## 1. Objective & Scope / 目标与范围

**English**

This document defines best practices for using the GitHub Copilot **coding agent** to maximize **high-quality, useful work** in each session. The goal is to get reviewable, production-ready PRs merged safely—not to generate large volumes of edits or artificially extend agent runtime.

Key assumptions:

- Copilot coding agent runs inside **GitHub Actions** and is designed for **short, autonomous tasks** that end with a pull request, not for multi-hour batch jobs.
- Session duration is **finite and not configurable** from the repository. Treat each run as "tens of minutes to complete a well-scoped change," not a multi-hour pipeline.
- Long-running work (heavy tests, data pipelines, builds) should be handled by **standard CI workflows** triggered by the agent's PR, not by the agent itself.

**Chinese / 中文**

本文档定义团队如何高效使用 GitHub Copilot **coding agent**，目标是在每次会话有限的运行时间内产出**高质量、对业务有价值的结果**，而不是把它当成可以"长期后台跑"的工作进程。我们关注的是最终 PR 的质量和可审查性，而不仅仅是生成的代码数量。

核心前提：

- Copilot coding agent 运行在 **GitHub Actions** 之中，本质是为 **短周期的自治任务** 设计——输出一个 PR，而不是跑几个小时的大型批处理任务。
- 会话时长 **有限且无法在仓库侧配置**。心里预期应是"几十分钟内完成一个明确范围的改动"，而不是几个小时的流水线。
- 真正长时间的工作（重型测试、数据处理、复杂构建）应该由 **普通 CI 工作流** 完成，由 agent 创建的 PR 触发。

---

## 2. Mental Model: What the Agent Is (and Isn't) / 心智模型：Agent 本质是什么、又不是什么

**English**

Think of Copilot coding agent as:

- A **temporary contractor**: you give it a well-written ticket, it does focused work, opens a PR, and exits.
- Not a daemon, not a job scheduler, and not a replacement for CI.

The agent operates in an ephemeral development environment powered by GitHub Actions. When you assign an issue to Copilot or mention `@copilot` in a PR comment, the agent evaluates the task, explores your repository, makes changes, executes automated tests and linters, then opens a pull request with its work.

Entry points include: assigning issues directly to "Copilot," mentioning `@copilot` in pull request comments, using the agents panel at `github.com/copilot/agents`, delegating tasks via VS Code's GitHub Pull Requests extension, or using the `/delegate` command in GitHub CLI.

Position the agent around: **small, well-scoped issues, clear acceptance criteria, and quick PR turnaround**.

**Chinese / 中文**

把 Copilot coding agent 当作：

- 一个 **临时外包工程师**：给它一张写清楚的工单，它集中干活，提 PR，然后会话结束。
- 它不是常驻服务，也不是任务调度器，更不是 CI 的替代品。

Agent 运行在基于 GitHub Actions 的临时开发环境中。当你把 issue 指派给 Copilot 或在 PR 评论中 @copilot 时，agent 会评估任务、探索仓库结构、执行代码修改、运行测试和 lint 检查，然后提交 PR。

触发方式包括：直接把 issue 指派给 "Copilot"、在 PR 评论中 @copilot、使用 `github.com/copilot/agents` 面板、通过 VS Code 的 GitHub Pull Requests 扩展委派任务、或使用 GitHub CLI 的 `/delegate` 命令。

Agent 的定位是：**小而清晰的 issue、明确的验收标准、快速的 PR 循环**，同时产出能够通过正常代码审查和质量门禁的人类水准 PR。

---

## 3. The Configuration File Hierarchy / 配置文件层级结构

**English**

Understanding the instruction file hierarchy is fundamental to controlling agent behavior. Files are processed in a specific priority order, with more specific instructions taking precedence.

**Repository-wide instructions** live in `/.github/copilot-instructions.md` and apply to all tasks. This file should tell Copilot:

- How to **build** the project
- How to **run tests**
- Coding conventions, frameworks, and "don't" rules
- The **quality bar / definition of done** for code changes (required tests, lint/type checks, documentation updates, review expectations)

**Path-specific instructions** use YAML frontmatter in `/.github/instructions/**/*.instructions.md` files to target specific file patterns:

```yaml
---
applyTo: "app/models/**/*.rb"
excludeAgent: "code-review"
---
# These instructions apply only to Ruby model files
```

**Agent instruction files** (`**/AGENTS.md`, `/CLAUDE.md`, `/GEMINI.md`) provide compatibility with multiple AI coding tools. The `AGENTS.md` format is particularly powerful because the nearest file in the directory tree takes precedence, allowing fine-grained control over different parts of your codebase.

**Custom agent profiles** in `.github/agents/CUSTOM-AGENT-NAME.md` create specialized agents for specific workflows—a test specialist, documentation writer, or security reviewer, each with distinct instructions and permissions.

**Chinese / 中文**

理解配置文件的层级结构是控制 agent 行为的基础。文件按特定优先级顺序处理，更具体的指令优先。

**仓库级指令** 位于 `/.github/copilot-instructions.md`，适用于所有任务。该文件应告诉 Copilot：

- 项目如何 **编译 / 构建**
- 如何 **运行测试**
- 编码规范、常用框架以及禁止事项
- 针对改动的 **质量标准 / 完成定义**（必须通过的测试、lint / 类型检查、需要更新的文档、review 期待等）

**路径级指令** 在 `/.github/instructions/**/*.instructions.md` 文件中使用 YAML frontmatter 来针对特定文件模式：

```yaml
---
applyTo: "app/models/**/*.rb"
excludeAgent: "code-review"
---
# 这些指令仅适用于 Ruby model 文件
```

**Agent 指令文件**（`**/AGENTS.md`、`/CLAUDE.md`、`/GEMINI.md`）提供与多种 AI 编码工具的兼容性。`AGENTS.md` 格式特别强大，因为目录树中最近的文件优先，允许对代码库不同部分进行细粒度控制。

**自定义 agent 配置文件** 位于 `.github/agents/CUSTOM-AGENT-NAME.md`，可为特定工作流创建专门的 agent——测试专家、文档撰写者或安全审查员，各有不同的指令和权限。

---

## 4. Writing Effective Instructions / 编写有效的指令

**English**

GitHub's analysis of over 2,500 repositories reveals that effective instruction files share five critical elements: a clear role definition, executable commands listed early, concrete code examples, explicit boundaries, and complete tech stack specifications with versions.

**Put executable commands early.** The agent needs to know how to build, test, and validate your project immediately:

```markdown
## Available Commands
- `make build` - Build the project
- `make test` - Run unit tests
- `make fmt` - Format code before committing
- `make ci` - Full CI check (build, lint, test)
```

**One real code snippet beats three paragraphs.** Instead of describing your error handling philosophy, show it:

```python
# Error handling pattern for this project
async def fetch_user(user_id: str) -> User:
    try:
        response = await client.get(f"/users/{user_id}")
        response.raise_for_status()
        return User.model_validate(response.json())
    except httpx.HTTPStatusError as e:
        logger.error(f"Failed to fetch user {user_id}: {e.response.status_code}")
        raise UserNotFoundError(user_id) from e
```

**Define three-tier boundaries** using "always do," "ask first," and "never do" rules:

- ✅ **Always**: Run `make fmt` before commits, write unit tests for new functions
- ⚠️ **Ask first**: Adding new dependencies, modifying database schemas
- 🚫 **Never**: Modify production configuration, remove existing tests, change authentication logic

**Provide fast, focused test commands**—not just "run the full suite":

```markdown
## Fast Validation Commands
- `pytest tests/service_x -q` - Quick tests for service_x only
- `npm test -- --testPathPattern=auth` - Auth module tests only
```

**Chinese / 中文**

GitHub 对超过 2,500 个仓库的分析表明，有效的指令文件具有五个关键要素：清晰的角色定义、尽早列出的可执行命令、具体的代码示例、明确的边界，以及带版本号的完整技术栈说明。

**尽早列出可执行命令。** Agent 需要立即知道如何构建、测试和验证项目：

```markdown
## 可用命令
- `make build` - 构建项目
- `make test` - 运行单元测试
- `make fmt` - 提交前格式化代码
- `make ci` - 完整 CI 检查（构建、lint、测试）
```

**一个真实的代码片段胜过三段描述。** 与其描述错误处理哲学，不如直接展示：

```python
# 本项目的错误处理模式
async def fetch_user(user_id: str) -> User:
    try:
        response = await client.get(f"/users/{user_id}")
        response.raise_for_status()
        return User.model_validate(response.json())
    except httpx.HTTPStatusError as e:
        logger.error(f"Failed to fetch user {user_id}: {e.response.status_code}")
        raise UserNotFoundError(user_id) from e
```

**定义三层边界**，使用"必须做"、"先询问"和"绝不做"规则：

- ✅ **必须**：提交前运行 `make fmt`，为新函数编写单元测试
- ⚠️ **先询问**：添加新依赖、修改数据库 schema
- 🚫 **绝不**：修改生产配置、删除现有测试、更改认证逻辑

**提供快速、局部的测试命令**——不要只写"运行完整测试套件"：

```markdown
## 快速验证命令
- `pytest tests/service_x -q` - 仅运行 service_x 的快速测试
- `npm test -- --testPathPattern=auth` - 仅运行认证模块测试
```

---

## 5. Pre-Warming the Environment / 预热运行环境

**English**

A major source of wasted agent time is repeated environment setup (checkout, dependency install, tooling). Use a dedicated workflow: `.github/workflows/copilot-setup-steps.yml`.

This workflow is referenced by Copilot when running the coding agent and should contain the **stable, reusable setup steps** for your repo so that each agent run starts from a pre-warmed environment instead of re-installing everything from scratch:

- Runs in GitHub Actions **before** the agent starts
- Lets you:
  - Install system packages
  - Restore dependencies (pip, npm, NuGet, etc.)
  - Perform an initial successful build or smoke test

Example:

```yaml
# .github/workflows/copilot-setup-steps.yml
name: Copilot Setup Steps

on:
  push:
    paths:
      - .github/workflows/copilot-setup-steps.yml

jobs:
  copilot-setup-steps:
    runs-on: ubuntu-latest
    timeout-minutes: 45

    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v5

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Verify build works
        run: make build

      - name: Verify tests can run
        run: make test --dry-run
```

**Chinese / 中文**

Agent 时间浪费的主要来源是重复的环境设置（checkout、依赖安装、工具配置）。使用专用工作流：`.github/workflows/copilot-setup-steps.yml`。

该工作流在运行 coding agent 时被 Copilot 引用，应包含仓库的**稳定、可复用的设置步骤**，使每次 agent 运行从预热环境开始，而不是从头安装一切：

- 在 agent 启动**之前**在 GitHub Actions 中运行
- 允许你：
  - 安装系统包
  - 恢复依赖（pip、npm、NuGet 等）
  - 执行初始的成功构建或冒烟测试

示例：

```yaml
# .github/workflows/copilot-setup-steps.yml
name: Copilot Setup Steps

on:
  push:
    paths:
      - .github/workflows/copilot-setup-steps.yml

jobs:
  copilot-setup-steps:
    runs-on: ubuntu-latest
    timeout-minutes: 45

    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v5

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Verify build works
        run: make build

      - name: Verify tests can run
        run: make test --dry-run
```

---

## 6. Designing Tasks the Agent Can Complete / 把任务拆成 Agent 真能完成的颗粒度

**English**

When you assign an issue to `@copilot`, the **issue is the prompt**. For high efficiency and high-quality output:

**Scope tightly.** One agent task = one logical change:

- ✅ Implement a specific feature flag
- ✅ Refactor a single module / component
- ✅ Add tests for a clearly defined surface area
- ❌ "Modernize the whole repo"
- ❌ "Improve performance everywhere"

**Right-size tasks for a single agent session.** Aim for changes that mostly touch one service, module, or well-defined slice of the repo. A good rule of thumb: modifications reviewable by a human in 15–30 minutes. If a task naturally splits into multiple PRs, create multiple issues and let the agent handle them iteratively.

**Write issue templates for agents.** Include at minimum:

- **Context** – what this code does in business terms
- **Change request** – what should be different after the agent finishes
- **Acceptance criteria** – what we will check to decide if the PR is acceptable
- **How to build & test** – commands, test suites, environment notes
- **Files to modify** – explicit list of files the agent should touch
- **Do not change** – files, packages, or behaviors that must be preserved
- **Known edge cases & pitfalls** – prevent the agent from re-introducing historical bugs

**Make success measurable.** Tie acceptance criteria to concrete checks: specific test commands, linters, or smoke flows ("this endpoint still returns 200 for this payload"). Call out what must **not** break (critical paths, SLAs, or user journeys).

**Reference existing design docs / ADRs.** Link to design docs, architecture diagrams, or ADRs so the agent does not have to infer architecture from scratch.

**Include visual context when relevant.** The agent supports vision models and can work from screenshots, mockups, or diagrams.

Example issue structure:

```markdown
## Problem
The user profile API returns 500 when accessing /api/users/{id} for users without profile photos.

## Context
This endpoint is called ~10K times/day. The photo field was added in v2.3 but older users don't have it populated.

## Acceptance Criteria
- [ ] API returns default avatar URL when user has no photo
- [ ] Add unit tests covering the edge case
- [ ] Update API documentation in /docs/api.md
- [ ] Endpoint returns 200 for test user ID `test-user-no-photo`

## Files to Modify
- `src/api/routes/users.py` - Add fallback logic
- `tests/api/test_users.py` - Add test cases
- `docs/api.md` - Update response schema

## Do Not Change
- Authentication middleware
- Database schema

## How to Test
- `pytest tests/api/test_users.py -v`
- `curl localhost:8000/api/users/test-user-no-photo` should return 200
```

**Chinese / 中文**

当你把 issue 指派给 `@copilot` 时，**issue 描述就是 prompt**。为提高效率并保证输出质量：

**控制任务范围。** 一次 agent 任务 = 一个清晰的逻辑改动：

- ✅ 实现一个特定的 feature flag
- ✅ 重构单个模块 / 组件
- ✅ 为特定范围补齐测试
- ❌ "重构整个仓库，让它更现代化"
- ❌ "整体性能优化一下"

**按一次会话的大小拆任务。** 尽量让改动集中在某一个服务、模块或明确边界内的子系统。经验法则：修改范围最好控制在人工可以在 15–30 分钟内审完。如果一个需求天然会拆成多次 PR，就在一开始拆成多个 issue，让 agent 逐步完成。

**为 agent 设计专用 issue 模板。** 至少包含：

- **背景**：业务上这块代码的作用
- **变更说明**：期望完成后哪里发生变化
- **验收标准**：我们如何判断 PR 合格
- **构建与测试方式**：命令、测试集、环境要求
- **需要修改的文件**：明确列出 agent 应该修改的文件
- **禁止修改**：不能动的文件、模块或关键行为
- **已知边界条件 / 坑点**：提醒 agent 避免重犯历史问题

**让成功标准可检测。** 把验收标准绑定到具体检查方式上：明确的测试命令、lint 规则或冒烟流程（例如"某个接口在给定请求体下仍然返回 200"）。明确哪些关键路径、SLA 或用户路径 **绝对不能被破坏**。

**引用现有设计文档 / ADR。** 在 issue 中附上设计文档、架构图或 ADR 链接，避免 agent 完全"盲猜"系统结构。

**在相关时包含视觉上下文。** Agent 支持视觉模型，可以从截图、设计稿或图表工作。

Issue 结构示例：

```markdown
## 问题
当访问 /api/users/{id} 时，没有头像的用户会返回 500 错误。

## 背景
该接口每天调用约 10K 次。photo 字段在 v2.3 中添加，但老用户没有填充。

## 验收标准
- [ ] 用户没有头像时 API 返回默认头像 URL
- [ ] 添加覆盖该边界情况的单元测试
- [ ] 更新 /docs/api.md 中的 API 文档
- [ ] 测试用户 ID `test-user-no-photo` 返回 200

## 需要修改的文件
- `src/api/routes/users.py` - 添加回退逻辑
- `tests/api/test_users.py` - 添加测试用例
- `docs/api.md` - 更新响应 schema

## 禁止修改
- 认证中间件
- 数据库 schema

## 测试方式
- `pytest tests/api/test_users.py -v`
- `curl localhost:8000/api/users/test-user-no-photo` 应返回 200
```

---

## 7. Optimizing Issue and Prompt Structure / 优化 Issue / 提示词结构

**English**

Small structural tweaks in issues can significantly improve outcomes:

**Ask for a plan first.** Request that the agent write a short numbered plan before implementing. This improves alignment and makes review easier:

```markdown
Before making changes, please:
1. Write a numbered plan of the changes you'll make
2. List any assumptions you're making
3. Then implement the plan
```

**Use explicit follow-up prompts** when the agent stops with TODOs. The comment `@copilot Please replace the TODO with a full implementation` often pushes past cautious stopping points.

**Batch PR comments using "Start a review"** rather than adding individual comments. Submitting all feedback at once triggers more comprehensive work than piecemeal requests.

**Reference earlier goals in follow-up comments.** When the agent loses focus during a long PR thread, explicitly reminding it of the original objectives helps it regain context.

**Chinese / 中文**

在 issue 结构上做一些小优化，可以显著提升效果：

**要求先写计划。** 要求 agent 在实施前先写一份简短的编号执行计划。这有助于对齐预期和审查：

```markdown
在修改之前，请：
1. 写出你将要做的修改的编号计划
2. 列出你做的任何假设
3. 然后实施该计划
```

**当 agent 留下 TODO 停止时使用明确的后续提示。** 评论 `@copilot 请用完整实现替换 TODO` 通常能推动越过谨慎的停止点。

**使用"开始审查"批量提交 PR 评论**，而不是添加单独的评论。一次性提交所有反馈比零散请求触发更全面的工作。

**在后续评论中引用早期目标。** 当 agent 在长 PR 讨论线程中失去焦点时，明确提醒它原始目标有助于恢复上下文。

---

## 8. Constraining Blast Radius / 用路径与规则限制改动"爆炸半径"

**English**

Use explicit constraints to keep changes focused and safe:

- Tell the agent to **work only in specific paths** (for example `src/service_x/` and `tests/service_x/`), especially in monorepos.
- Ask the agent to avoid repo-wide reformatting or large search/replace that creates noisy diffs.
- For infrastructure, schema, or data changes, split work into: "agent prepares code + tests" and "human-run pipeline applies change".

Create **specialized custom agents** for recurring quality concerns. A test specialist agent with focused instructions produces better results than asking the general agent to also write tests:

```markdown
---
name: test-agent
description: QA specialist for comprehensive testing
---
You are a QA software engineer. You:
- Write tests following existing patterns in /tests/
- Run tests and iterate on failures
- Never modify source code or remove failing tests
- Use table-driven tests when testing multiple inputs
```

**Chinese / 中文**

通过清晰的边界控制改动范围，降低风险：

- 在说明里明确要求 agent **只修改某些目录 / 文件**（如 `src/service_x/`、`tests/service_x/`），特别是在 monorepo 中。
- 避免让 agent 做全仓代码格式化或大规模查找替换，以免产生噪音很大的 diff。
- 对基础设施、数据库 schema 或数据操作类改动，可以拆成两步：agent 负责准备代码和测试，真正执行变更由人工触发流水线完成。

为重复出现的质量问题创建**专门的自定义 agent**。有专门指令的测试专家 agent 比要求通用 agent 同时写测试产生更好的结果：

```markdown
---
name: test-agent
description: 专门负责全面测试的 QA 专家
---
你是一名 QA 软件工程师。你：
- 按照 /tests/ 中现有模式编写测试
- 运行测试并针对失败进行迭代
- 永远不修改源代码或删除失败的测试
- 测试多个输入时使用表驱动测试
```

---

## 9. Embedding the Agent in CI and Team Process / 把 Agent 工作融入 CI 和团队流程

**English**

Integrate the agent into existing review and governance instead of bypassing it:

- Use `CODEOWNERS` so agent PRs automatically request review from the right maintainers.
- Keep **required checks strict** for agent PRs (tests, lint, type checks, security scans); do not weaken gates for automation.
- Disallow direct bot pushes to main: agents open PRs, humans review and merge.
- In higher-risk repos, require agent changes to pass through **staging / canary environments** before promotion.
- Track simple metrics (agent PR count, merge rate, average review changes, CI failure rate), periodically sample merged agent PRs and recurring review feedback, and use them to refine instructions, templates, and `copilot-instructions`.

**Start small and calibrate.** Use labels like `good-first-agent-task`, `agent-refactor`, `agent-tests-only` to identify agent-suitable issues. Start with tasks whose success is easily verified by local tests and small file sets.

**Chinese / 中文**

让 agent 自然融入现有的代码审查和治理流程，而不是绕过去：

- 使用 `CODEOWNERS`，让 agent 的 PR 自动请求到合适的代码负责人。
- 对 agent PR 保持 **严格的必需检查**（测试、lint、类型检查、安全扫描），不要为自动化放宽门槛。
- 禁止机器人直接向 main 推送代码：agent 只能提 PR，由人工审核并合并。
- 在高风险仓库中，可以要求 agent 改动必须先通过 **预发布 / 金丝雀环境** 验证，再推广到正式环境。
- 记录一些简单指标（agent PR 数量、合并率、平均修改量、CI 失败率），定期抽样检查已合并的 agent PR 和常见审查意见，并据此迭代说明文档、issue 模板和 `copilot-instructions`。

**从小处开始校准。** 通过 `good-first-agent-task`、`agent-refactor`、`agent-tests-only` 等标签，把适合 agent 的 issue 标记出来。优先选择可以通过本地测试和少量文件清晰验证正确性的任务。

---

## 10. Security Considerations / 安全防护与使用边界

**English**

While Copilot includes built-in security protections (CodeQL analysis, secret scanning, dependency checking against GitHub's Advisory Database), treat AI-generated commands and changes as **untrusted until reviewed**.

**Built-in protections:**

- The agent operates with read-only repository access
- Can only push to branches prefixed with `copilot/`
- Cannot approve or merge its own PRs
- Firewall-controlled internet access

**Additional guardrails you should implement:**

- Review shell commands proposed or executed by the agent
- Avoid giving the agent access to secrets it does not strictly need
- Keep destructive operations (infra changes, data deletions) behind separate, human-initiated workflows
- Never assign tasks involving authentication changes, secrets handling, or PII processing
- Configure branch protection rules that apply to Copilot branches
- Implement pre-commit hooks for additional secrets scanning

**Important note:** Research indicates AI code review may miss critical vulnerabilities including SQL injection, XSS, and insecure deserialization. These built-in tools supplement but don't replace dedicated security practices. Always review generated code with security awareness before merging.

**Chinese / 中文**

虽然 Copilot 包含内置安全保护（CodeQL 分析、密钥扫描、依赖检查），但应将 AI 生成的命令和变更视为 **未经审查的不可信输入**。

**内置保护：**

- Agent 以只读仓库访问权限运行
- 只能推送到以 `copilot/` 为前缀的分支
- 不能批准或合并自己的 PR
- 防火墙控制的互联网访问

**你应该实施的额外防护：**

- 对 agent 提议或执行的命令行操作进行人工复核
- 不要给 agent 提供不必要的密钥或凭证
- 破坏性操作（如基础设施变更、数据删除）放到单独的人为触发工作流中执行
- 永远不要分配涉及认证更改、密钥处理或 PII 处理的任务
- 配置适用于 Copilot 分支的分支保护规则
- 实施预提交钩子进行额外的密钥扫描

**重要提示：** 研究表明 AI 代码审查可能会遗漏关键漏洞，包括 SQL 注入、XSS 和不安全的反序列化。这些内置工具是对专门安全实践的补充而非替代。合并前始终以安全意识审查生成的代码。

---

## 11. Common Anti-Patterns / 常见反模式（尽量避免）

**English**

1. **Massive, ambiguous tickets**
   - "Refactor the whole service so it's cleaner."
   - "Fix all performance issues in this repo."

   These cause the agent to burn its limited runtime thrashing around with no clear success condition.

2. **Letting the agent own long-running pipelines**

   Trying to have the agent run full multi-hour test suites or data jobs directly is inefficient. CI is built for that.

3. **Skipping setup steps**

   Re-installing dependencies and tools from scratch on every agent run drastically cuts into useful time.

4. **Blindly merging agent PRs**

   Copilot is powerful, but not infallible. Always review, run tests, and treat it as a junior dev who works fast but can be wrong.

5. **No explicit quality expectations**

   Simply writing "add tests" produces inconsistent results. Specify framework, coverage expectations, and patterns to follow.

6. **Missing dependency pre-installation**

   Several factors cause the agent to stop before completing a task. Missing dependencies trigger trial-and-error loops that exhaust resources.

**Chinese / 中文**

1. **笼统而巨大的工单**
   - "把这个服务整体重构一下，写干净点。"
   - "修掉整个仓库的性能问题。"

   这类需求会让 agent 在有限时间内乱试一通，却缺乏可验证的成果。

2. **让 agent 直接承担长耗时流水线**

   让 agent 直接跑几个小时的测试或数据任务，效率很低；这本来就是 CI 的职责。

3. **不做预热 / setup**

   每次会话都从零安装依赖和工具，会严重吞噬有效工作时间。

4. **不审查直接合并 agent 的 PR**

   Copilot 很强，但不是神。PR 必须经过正常的代码审查和测试，就当是一个"速度很快但容易犯错的新人"。

5. **没有明确的质量期望**

   简单写"添加测试"会产生不一致的结果。指定框架、覆盖率期望和要遵循的模式。

6. **缺少依赖预安装**

   多种因素会导致 agent 在完成任务前停止。缺少依赖会触发试错循环，耗尽资源。

---

## 12. Operational Checklist / 落地执行检查清单

**English – Before using the agent at scale**

**Repository Setup:**

- [ ] Add `.github/copilot-instructions.md` with build/test instructions, coding conventions, and quality expectations
- [ ] Add `.github/workflows/copilot-setup-steps.yml` to pre-warm dependencies and tools
- [ ] Configure path-specific instructions for complex areas of the codebase
- [ ] Decide which stacks warrant **custom agents** and set them up

**Issue Management:**

- [ ] Create issue templates specifically optimized as prompts for `@copilot`
- [ ] Define labels to identify agent-suitable tasks (`good-first-agent-task`, `agent-refactor`, etc.)
- [ ] Document the standard issue structure (Context, Change Request, Acceptance Criteria, Files to Modify, Do Not Change, How to Test)

**Quality and Security:**

- [ ] Configure CI workflows that run on PRs from the agent with full checks
- [ ] Verify `CODEOWNERS` will assign appropriate reviewers to agent PRs
- [ ] Document the **quality expectations for agent PRs** (tests to run, review rules, when to request design review)
- [ ] Document security guardrails around secrets and dangerous commands

**Ongoing Operations:**

- [ ] Track metrics (PR count, merge rate, CI failure rate)
- [ ] Schedule periodic review of merged agent PRs
- [ ] Establish process for updating instructions based on feedback

**Chinese / 中文 – 在正式大量使用 agent 前**

**仓库设置：**

- [ ] 新增 `.github/copilot-instructions.md`，说明构建 / 测试方式、编码规范和质量期望
- [ ] 新增 `.github/workflows/copilot-setup-steps.yml`，预热依赖和工具
- [ ] 为代码库的复杂区域配置路径级指令
- [ ] 确定哪些技术栈需要 **自定义 agent**，并完成配置

**Issue 管理：**

- [ ] 设计专门给 `@copilot` 用的 issue 模板，优化成"好 prompt"
- [ ] 定义标签来标识适合 agent 的任务（`good-first-agent-task`、`agent-refactor` 等）
- [ ] 记录标准 issue 结构（背景、变更说明、验收标准、需要修改的文件、禁止修改、测试方式）

**质量与安全：**

- [ ] 配置对 agent PR 触发的 CI 流水线，跑完整检查
- [ ] 验证 `CODEOWNERS` 会为 agent PR 分配合适的审查人
- [ ] 明确并记录 **agent PR 的质量预期**（需要运行的测试、review 规则、何时需要设计评审）
- [ ] 明确关于密钥和危险命令的安全边界

**持续运营：**

- [ ] 跟踪指标（PR 数量、合并率、CI 失败率）
- [ ] 安排定期审查已合并的 agent PR
- [ ] 建立基于反馈更新指令的流程

---

## 13. Summary / 总结

**English**

Use GitHub Copilot coding agent as a high-speed, short-lived coding assistant that produces high-quality, reviewable PRs:

- Give it **well-scoped issues** with clear acceptance criteria and explicit file lists
- Provide a **pre-warmed environment** via `copilot-setup-steps.yml`
- Set **clear quality expectations** (tests, architecture, style) in repository instructions
- Maintain **strong CI and review guardrails**—same standards as human-authored code
- **Chain multiple focused sessions** rather than expecting multi-hour autonomous work

Do not expect it to behave like a long-running background worker. The gap between mediocre and excellent results comes down to preparation: well-structured instruction files, clearly written issues, pre-configured environments, and explicit quality requirements.

The most successful teams use Copilot Agent for work it handles well (bug fixes, test coverage, documentation, incremental features) while reserving complex architectural decisions and security-critical code for human developers.

**Chinese / 中文**

把 GitHub Copilot coding agent 当作一个高速度、短生命周期、能够产出高质量 PR 的编码助手：

- 提供**范围清晰的 issue**，包含明确的验收标准和文件列表
- 通过 `copilot-setup-steps.yml` 提供**预热好的环境**
- 在仓库指令中设置**明确的质量标准**（测试、架构、风格）
- 保持**可靠的 CI 与代码审查保护机制**——与人工代码相同的标准
- **通过多个聚焦的会话串联**完整需求，而不是期待多小时的自主工作

不要指望它像一个长期后台进程那样工作。优秀结果与平庸结果之间的差距取决于准备工作：结构良好的指令文件、清晰的 issue、预配置的环境和明确的质量要求。

最成功的团队将 Copilot Agent 用于它擅长的工作（bug 修复、测试覆盖、文档、增量功能），同时将复杂的架构决策和安全关键代码保留给人类开发者。

---

## 14. Quick Reference / 快速参考

| Aspect / 方面 | Best Practice / 最佳实践 |
|---------------|--------------------------|
| Task scope / 任务范围 | One logical change, reviewable in 15-30 min / 一个逻辑改动，15-30分钟可审完 |
| Issue structure / Issue 结构 | Context + Change + Acceptance + Files + Do Not Change + Test / 背景 + 变更 + 验收 + 文件 + 禁止修改 + 测试 |
| Instructions / 指令 | Commands first, code examples, three-tier boundaries / 命令优先，代码示例，三层边界 |
| Environment / 环境 | Pre-warm with `copilot-setup-steps.yml` / 用 `copilot-setup-steps.yml` 预热 |
| Quality gates / 质量门禁 | Same as human code: tests, lint, security scans / 与人工代码相同：测试、lint、安全扫描 |
| Security / 安全 | No secrets access, review all commands, human-initiated destructive ops / 不访问密钥，审查所有命令，人工触发破坏性操作 |
| Iteration / 迭代 | Multiple focused sessions, not one long run / 多个聚焦会话，而非一次长运行 |

---

## References / 参考资料

- [GitHub Docs – About GitHub Copilot coding agent](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent)
- [GitHub Docs – Best practices for using Copilot to work on tasks](https://docs.github.com/en/copilot/how-tos/agents/copilot-coding-agent/best-practices-for-using-copilot-to-work-on-tasks)
- [GitHub Docs – Repository-wide custom instructions](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions)
- [GitHub Docs – Preinstalling tools in Copilot's environment](https://docs.github.com/en/enterprise-cloud@latest/copilot/how-tos/use-copilot-agents/coding-agent/customize-the-agent-environment)
- [GitHub Blog – How to write a great agents.md: Lessons from over 2,500 repositories](https://github.blog/ai-and-ml/github-copilot/how-to-write-a-great-agents-md-lessons-from-over-2500-repositories/)
- [GitHub Blog – Assigning and completing issues with coding agent](https://github.blog/ai-and-ml/github-copilot/assigning-and-completing-issues-with-coding-agent-in-github-copilot/)
- [GitHub Blog – GitHub Copilot coding agent 101](https://github.blog/ai-and-ml/github-copilot/github-copilot-coding-agent-101-getting-started-with-agentic-workflows-on-github/)
