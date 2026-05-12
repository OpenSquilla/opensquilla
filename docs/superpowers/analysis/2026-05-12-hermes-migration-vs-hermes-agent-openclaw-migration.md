# OpenSquilla Hermes 迁移 vs Hermes Agent OpenClaw 迁移分析

日期：2026-05-12

## 分析范围

本文对比当前 OpenSquilla 的一键 Hermes 迁移能力（`opensquilla migrate hermes`）和 Hermes Agent 已有的一键 OpenClaw 迁移能力（`hermes claw migrate`）。

目标不是泛泛判断“能不能迁”，而是回答三个问题：

1. 当前 OpenSquilla 已经和 Hermes Agent 迁移能力对齐了哪些部分。
2. 当前 OpenSquilla 和 Hermes Agent 的关键差异在哪里。
3. 如果要把 OpenSquilla 的 Hermes 迁移继续打磨到更接近成熟迁移工具，还需要补哪些工程项。

证据来自本地代码：

- `opensquilla/src/opensquilla/migration/hermes.py`
- `opensquilla/src/opensquilla/cli/migrate_cmd.py`
- `hermes-agent/hermes_cli/claw.py`
- `hermes-agent/hermes_cli/setup.py`
- `hermes-agent/optional-skills/migration/openclaw-migration/scripts/openclaw_to_hermes.py`
- `hermes-agent/tests/hermes_cli/test_setup_openclaw_migration.py`

OpenSquilla Hermes 迁移测试已重新跑过：

```powershell
uv run pytest tests/test_migration/test_hermes_migration.py tests/test_migration/test_hermes_e2e.py -q --basetemp ... -p no:cacheprovider
```

结果：`10 passed in 1.47s`。

Hermes Agent 侧迁移测试在当前本地 checkout 中没有跑通，因为它的虚拟环境缺少 `pytest`：`No module named pytest`。

## 总结结论

OpenSquilla 当前已经具备可用的一键 Hermes 迁移入口：支持 dry-run、显式 apply、可选 secrets 迁移、preset/include/exclude、技能冲突策略、JSON 输出，并且有 CLI 层面的 E2E 测试。

但和 Hermes Agent 的 OpenClaw-to-Hermes 迁移相比，OpenSquilla 目前还不是“成熟迁移工具级别”的完整体。差距主要集中在三类：

1. 安全性不足：OpenSquilla 还没有 apply 前的完整目标空间备份；`--overwrite` 的 help 文案声称会备份被覆盖文件，但当前实现没有一致做到 item-level backup。
2. 覆盖面更窄：OpenSquilla 接受了不少 Hermes runtime option id，但当前真正实现的映射主要是用户数据、部分 config/env/channel/MCP/plugin/cron 归档；Hermes Agent 的迁移覆盖了更大的运行时配置面。
3. 人类可读的迁移指导不足：OpenSquilla 目前写 `report.json` 和 `summary.md`；Hermes Agent 还有更完整的 warnings、next_steps、`MIGRATION_NOTES.md` 和通用递归脱敏。

## 已经对齐的能力

### 1. dry-run 和 apply 分离

OpenSquilla 默认是预览，不传 `--apply` 不落地写入。证据：

- `opensquilla/src/opensquilla/cli/migrate_cmd.py:199` 暴露 `--apply`。
- `opensquilla/src/opensquilla/migration/hermes.py:169` 是迁移主流程入口。
- `opensquilla/src/opensquilla/migration/hermes.py:174` 到 `hermes.py:178` 只在主流程里规划用户数据、迁配置、归档不支持项。

Hermes Agent 也有预览/执行分离，但交互模型不同：

- `hermes-agent/hermes_cli/claw.py:468` 在 `--dry-run` 下停止。
- `hermes-agent/hermes_cli/claw.py:791` 打印“不带 dry-run 再执行”的提示。
- `hermes-agent/hermes_cli/claw.py:5` 到 `claw.py:7` 给了 CLI 示例，包括 `--dry-run`、`--yes`、`--overwrite --migrate-secrets`。

差异：OpenSquilla 更偏脚本自动化，用 `--apply` 明确执行；Hermes Agent 更偏人机引导，用 `--dry-run` 预览、`--yes` 跳过确认。

### 2. secrets 迁移都是显式 opt-in

OpenSquilla：

- `opensquilla/src/opensquilla/cli/migrate_cmd.py:203` 暴露 `--migrate-secrets`。
- `opensquilla/src/opensquilla/migration/hermes.py:356` 在没有 opt-in 时跳过模型/Provider secrets。
- `opensquilla/src/opensquilla/migration/hermes.py:421` 在没有 opt-in 时跳过 channel tokens。

Hermes Agent：

- `hermes-agent/optional-skills/migration/openclaw-migration/scripts/openclaw_to_hermes.py:100` 明确 provider API key 迁移需要 `--migrate-secrets`。
- `openclaw_to_hermes.py:1064` 和 `openclaw_to_hermes.py:1374` 会提示用户重新带 `--migrate-secrets`。

结论：两边在“默认不搬 secrets”这件事上是对齐的。

### 3. 都支持 preset/include/exclude

OpenSquilla：

- `opensquilla/src/opensquilla/cli/migrate_cmd.py:80` 校验 Hermes include option。
- `opensquilla/src/opensquilla/cli/migrate_cmd.py:84` 校验 Hermes exclude option。
- `opensquilla/src/opensquilla/migration/hermes.py:46` 定义 `MIGRATION_OPTIONS`。

Hermes Agent：

- `hermes-agent/optional-skills/migration/openclaw-migration/scripts/openclaw_to_hermes.py:895` 开始通过 `run_if_selected(...)` 逐项执行迁移阶段。
- `openclaw_to_hermes.py:962` 是 `run_if_selected` 入口。

结论：两边都有“选择迁移范围”的机制。

### 4. 都支持技能冲突策略

OpenSquilla：

- `opensquilla/src/opensquilla/cli/migrate_cmd.py:229` 暴露 `--skill-conflict`。
- `opensquilla/src/opensquilla/migration/hermes.py:21` 支持 `skip`、`overwrite`、`rename`。

Hermes Agent：

- `hermes-agent/hermes_cli/claw.py:472` 在发现 conflict 且未传 `--overwrite` 时拒绝执行。
- `hermes-agent/hermes_cli/claw.py:484` 给出 `--overwrite` 和 item-level backup 指引。
- `openclaw_to_hermes.py:2876` 给出 overwrite/manual merge 提示。

结论：两边都有冲突策略，但 Hermes Agent 的拒绝和引导更强。

## 关键差异

### 1. OpenSquilla 当前实现规模明显更小

本地统计：

- `opensquilla/src/opensquilla/migration/hermes.py`：555 行。
- `hermes-agent/optional-skills/migration/openclaw-migration/scripts/openclaw_to_hermes.py`：3136 行。
- `hermes-agent/hermes_cli/claw.py`：810 行。

这不是说 OpenSquilla 实现一定不好；它是新功能，而且有意从较小范围开始。但这能说明一点：不能因为 OpenSquilla 有了 `migrate hermes` 命令，就默认它已经达到 Hermes Agent 迁移器的成熟覆盖面。

### 2. OpenSquilla 更适合自动化，Hermes Agent 更适合交互式迁移

OpenSquilla 的典型命令：

```powershell
uv run opensquilla migrate hermes --source <path> --apply --migrate-secrets --json
```

OpenSquilla 的 CLI 会直接返回结构化 report。证据：

- `opensquilla/src/opensquilla/cli/migrate_cmd.py:257` 调用 `HermesMigrator(options).migrate()`。
- `opensquilla/src/opensquilla/cli/migrate_cmd.py:259` 在非 JSON 模式下打印迁移结果。

Hermes Agent 的典型命令：

```powershell
hermes claw migrate --dry-run
hermes claw migrate --yes
hermes claw migrate --preset full --overwrite --migrate-secrets
```

Hermes Agent 的路径更强调人工确认、冲突拒绝、备份后执行。这对普通用户更友好，对脚本化流水线则稍微重一些。

### 3. Hermes Agent 把迁移接入了首次 setup，OpenSquilla 还没有

Hermes Agent 在 setup 过程中会发现 OpenClaw 并引导迁移。证据：

- `hermes-agent/hermes_cli/setup.py:2907` 在跳过迁移时提示可之后运行 `hermes claw migrate --dry-run`。
- `hermes-agent/hermes_cli/setup.py:2968` 提示用户可以用 `--dry-run` 再预览，或者用 `--preset minimal` 做轻量导入。
- `hermes-agent/hermes_cli/setup.py:3003` 告诉用户冲突数量，并提示 `--overwrite`。

OpenSquilla 当前只有独立命令 `opensquilla migrate hermes`，还没有在 first-run setup、dashboard onboarding 或 gateway 启动路径里检测 `~/.hermes` 并主动提示迁移。

### 4. OpenSquilla 的迁移覆盖面更窄

OpenSquilla 当前 Hermes 迁移主流程只有三个大阶段：

- `opensquilla/src/opensquilla/migration/hermes.py:174`：`_plan_user_data(selected)`
- `opensquilla/src/opensquilla/migration/hermes.py:175`：`_migrate_config_and_env(selected)`
- `opensquilla/src/opensquilla/migration/hermes.py:178`：`_archive_unsupported(selected)`

配置/env 映射从 `opensquilla/src/opensquilla/migration/hermes.py:291` 开始，主要覆盖模型/env/search/MCP/channel 相关映射和一部分归档逻辑。

Hermes Agent 的 OpenClaw 迁移阶段明显更广。证据：

- `openclaw_to_hermes.py:895` 到 `openclaw_to_hermes.py:955` 依次执行 soul、workspace agents、memory、instructions、messaging、secret settings、Discord、Slack、WhatsApp、Signal、provider keys、model config、TTS config、command allowlist、skills、shared skills、daily memory、archive、MCP servers、plugins config、cron jobs、hooks、agent config、gateway config、session config、full providers、deep channels、browser config、tools config、approvals config、memory backend、skills config、UI identity、logging config。

最值得注意的问题：OpenSquilla 接受了一些 runtime option id，但当前没有独立实现对应迁移逻辑。证据：

- `opensquilla/src/opensquilla/migration/hermes.py:35` 到 `hermes.py:44` 包含 `tools-config`、`browser-config`、`session-config`、`gateway-config`、`approvals-config`、`logging-config` 等 option id。
- 但当前 `opensquilla/src/opensquilla/migration/hermes.py` 没有对应的 `_migrate_tools_config`、`_migrate_browser_config`、`_migrate_session_config`、`_migrate_gateway_config`、`_migrate_approvals_config`、`_migrate_logging_config` 方法。

结论：这是当前最明确的 parity gap。用户传 `--include tools-config` 这类参数时，CLI 会接受，但实际迁移行为并没有 Hermes Agent 那样完整。

### 5. OpenSquilla 的安全网比 Hermes Agent 弱

Hermes Agent apply 前会做完整 pre-migration backup。证据：

- `hermes-agent/hermes_cli/claw.py:501` 开始描述 pre-migration backup 阶段。
- `hermes-agent/hermes_cli/claw.py:511` 导入 `create_pre_migration_backup`。
- `hermes-agent/hermes_cli/claw.py:512` 调用 `create_pre_migration_backup(hermes_home=hermes_home)`。

OpenSquilla 当前会把迁移输出写到 `~/.opensquilla/migration/hermes/<timestamp>`，但没有在 apply 前完整备份目标 `~/.opensquilla`。

还有一个更实际的问题：OpenSquilla CLI help 和实现不完全一致。

- `opensquilla/src/opensquilla/cli/migrate_cmd.py:206` 的 Hermes `--overwrite` help 表述是覆盖已有文件并备份。
- `opensquilla/src/opensquilla/migration/hermes.py:247` 到 `hermes.py:250` 的文件写入/合并路径没有看到统一的 item-level backup。
- `opensquilla/src/opensquilla/migration/hermes.py:270` 在 skill overwrite 时会 `shutil.rmtree(destination)`，但没有可见的 item-level backup。

Hermes Agent 在这点上更强：

- `hermes-agent/hermes_cli/claw.py:472` 在有冲突且没有 `--overwrite` 时拒绝执行。
- `hermes-agent/hermes_cli/claw.py:484` 明确提示 overwrite 会有 item-level backup。

结论：OpenSquilla 应优先修这个问题。迁移工具最重要的是可逆性和可信度，覆盖面可以逐步补，安全承诺不能和实现不一致。

### 6. OpenSquilla 的报告更适合机器读，Hermes Agent 的报告更适合人处理后续问题

OpenSquilla 写：

- `opensquilla/src/opensquilla/migration/hermes.py:280`：`report.json`
- `opensquilla/src/opensquilla/migration/hermes.py:289`：`summary.md`

Hermes Agent 除了 report/summary，还有更强的人类指导：

- `openclaw_to_hermes.py:570` 开始是迁移报告脱敏逻辑。
- `openclaw_to_hermes.py:624` 是 `redact_migration_value`。
- `openclaw_to_hermes.py:657` 写报告前先 redacted。
- `openclaw_to_hermes.py:685` 输出 warnings。
- `openclaw_to_hermes.py:702` 输出 next_steps。
- `openclaw_to_hermes.py:2955` 写 `MIGRATION_NOTES.md`。

OpenSquilla 目前的 report 对自动化足够有用，但对普通用户排查“哪些东西迁了、哪些没迁、哪些需要手工检查”还不够直接。

### 7. OpenSquilla 有一个明确优势：Hermes custom provider 映射

OpenSquilla 现在能把 Hermes 的 `custom + base_url` provider 映射成 OpenAI-compatible provider 配置。证据：

- `opensquilla/src/opensquilla/migration/hermes.py:313` 附近实现 custom provider/base_url 映射。
- `opensquilla/tests/test_migration/test_hermes_migration.py:194` 有对应测试。

这点对 Hermes-to-OpenSquilla 很重要，因为很多 Hermes 用户会配置 OpenAI-compatible 的自定义 endpoint。

## OpenSquilla 后续优化项

### P0：先补安全性和实现/文案一致性

#### 1. 给 `--overwrite` 做真正的 item-level backup

问题：

当前 CLI help 表示 overwrite 会备份被覆盖文件，但 Hermes migrator 里没有统一 backup 机制。尤其是 skill overwrite 时直接删除目录，这个行为对迁移工具来说风险偏高。

需要做的事情：

- 新增 backup root，例如 `~/.opensquilla/migration/hermes/<timestamp>/backups/items`。
- 每次覆盖已有目标之前，先把原文件或原目录复制到 backup root。
- 每条被覆盖的 migration item 都记录 `backup` 字段。
- 覆盖范围包括 workspace files、skills、config、env、archive 输出等所有可能替换已有内容的路径。
- 加测试：预先创建目标文件/目录，执行 `--apply --overwrite`，断言旧内容在 backup path 中存在。

验收标准：

- `--overwrite` 不会在没有备份的情况下删除或替换用户已有内容。
- `report.json` 中每个 overwritten item 都能看到 backup path。
- CLI help 和实际行为一致。

#### 2. apply 前做完整 pre-migration backup

问题：

Hermes Agent apply 前备份整个 Hermes home。OpenSquilla 当前没有在写 `~/.opensquilla` 前做完整备份。

需要做的事情：

- 在第一次写入前创建 `~/.opensquilla` 的完整备份。
- 推荐路径：`~/.opensquilla/backups/pre-hermes-migration-<timestamp>.zip`，或放到本次 migration output dir。
- 如果排除 runtime/cache/log 等大目录，必须在 report 中写明 exclusions。
- 默认 apply 就备份；是否提供 `--no-backup` 可以之后再评估，但默认不应该跳过。

验收标准：

- 任意 `--apply` 执行前都有完整 backup。
- backup path 出现在 `report.json`、`summary.md` 和未来的 `MIGRATION_NOTES.md`。
- backup 创建失败时，迁移必须在任何写入前中止。

#### 3. 更明确地区分 merge、skip、conflict、overwrite

问题：

OpenSquilla 当前有些文件会在 `overwrite=False` 时合并内容。这个行为有用，但如果 report 只写 skipped/planned/migrated，用户很难判断现有配置到底有没有被改动。

需要做的事情：

- 对目标碰撞做更细状态分类：`merged`、`conflict`、`skipped`、`overwritten`。
- 对 append-only/可安全合并文件继续 merge，但 report 要写清楚新增了什么。
- 对语义不确定的配置文件，默认 conflict，除非用户显式选择 overwrite 或 merge mode。

验收标准：

- 用户能从 report 判断每个目标是未动、追加、合并、跳过，还是覆盖。
- 不再有“看起来迁了，但其实只是静默合并/跳过”的模糊状态。

### P1：补齐 option surface，避免参数看起来支持但实际没行为

#### 4. 对每个已接受 option id 做真实行为，或者暂时移除

问题：

OpenSquilla 现在接受 `tools-config`、`browser-config`、`session-config`、`gateway-config`、`approvals-config`、`logging-config` 等 option id，但没有 dedicated migration handler。这会让用户以为这些配置已经完整迁移。

需要做的事情：

- 对每个 option id 明确三选一：
  - 能映射的，写入 OpenSquilla native config；
  - 暂时不能映射的，归档并生成 warning/manual step；
  - 完全不支持的，先从 `MIGRATION_OPTIONS` 移除，避免 CLI 接受无效参数。
- 给每个 option id 加测试，证明它会 map、archive 或 reject。

建议顺序：

1. `tools-config`：映射 terminal timeout、命令策略等 OpenSquilla 有对应字段的内容。
2. `approvals-config`：如果 OpenSquilla 有审批模式字段，映射 mode；复杂规则先归档。
3. `browser-config`：映射 enable/headless 等直接字段；高级设置归档。
4. `session-config`：映射 reset/retention 等直接字段；高级配置归档。
5. `gateway-config`：映射 host/port/enable 这类静态配置，不迁 live runtime state。
6. `logging-config`：除非 OpenSquilla 有对应字段，否则先归档并提示人工检查。

验收标准：

- `--include <option>` 对每个 accepted option 都有可见、可测试的结果。
- 不支持但检测到的配置会进入 warnings/next_steps，不会静默无效。

#### 5. 扩大 Hermes 用户数据覆盖面

问题：

Hermes Agent 迁移覆盖 daily memory、workspace agents、shared skills、command allowlist 等。OpenSquilla 现在主要覆盖核心 persona/memory/skills/config/env，还需要明确 Hermes 的其他用户资产怎么处理。

需要做的事情：

- 梳理 Hermes home 和 profile home 的真实目录结构。
- 建一张 mapping matrix：source path、OpenSquilla destination、转换规则、fallback/archive 规则。
- 增加测试 fixture，覆盖 shared skills、profile-specific config、额外 workspace 文件、daily memory 等真实场景。

验收标准：

- Hermes 主要用户资产都被明确标记为 migrated、archived 或 intentionally unsupported。
- report 用用户能理解的话说明没迁的原因和下一步。

### P1：增强人类可读报告和后续指导

#### 6. 增加 `MIGRATION_NOTES.md`

问题：

OpenSquilla 目前只有 `summary.md`，信息密度偏低，不能替代迁移后的操作说明。

需要做的事情：

- 在 `report.json` 和 `summary.md` 同目录写 `MIGRATION_NOTES.md`。
- 包含这些章节：
  - 已迁移项目；
  - 跳过的冲突；
  - 归档的不支持项；
  - 语义转换；
  - 没有迁移的 secrets；
  - 推荐验证命令。

验收标准：

- 用户只看 migration output dir 就能知道下一步检查什么。
- 文档里包含具体命令，例如 `opensquilla gateway start` 和 CLI chat smoke test。

#### 7. report schema 增加 warnings 和 next_steps

问题：

Hermes Agent 的 report 会给 warnings 和 next_steps。OpenSquilla 现在主要是 items 列表，缺少顶层指导。

需要做的事情：

- 在 Hermes migration report 顶层增加 `warnings: list[str]` 和 `next_steps: list[str]`。
- 对 skipped secrets、不支持配置、archive-only mapping、conflicts 写 warning。
- `summary.md` 和未来 `MIGRATION_NOTES.md` 都从同一份 warnings/next_steps 生成。

验收标准：

- `--json` 消费方能程序化判断是否需要人工后续处理。
- 人类读 summary/notes 时能看到明确下一步。

#### 8. 增加通用递归脱敏

问题：

OpenSquilla 目前在很多地方避免写 secrets，但没有 Hermes Agent 那种写报告前统一递归脱敏的兜底机制。迁移工具只靠各个调用点自觉，很容易漏。

需要做的事情：

- 增加通用 `redact_migration_value` 类似函数，递归处理 dict/list/string。
- 按 key 和 value pattern 双重脱敏：token、api_key、secret、password、bearer 等。
- 写 `report.json` 和打印 `--json` 前统一过红线。
- 增加嵌套 secrets 测试：details、source metadata、archived summaries、warnings 字符串都要覆盖。

验收标准：

- report 文件和 stdout JSON 不出现 token-like 明文。
- 脱敏逻辑集中复用，不分散在各个记录点。

### P2：提升 onboarding 和真实端到端置信度

#### 9. first-run 检测 Hermes home 并引导迁移

问题：

Hermes Agent setup 会主动发现 OpenClaw 并提示迁移。OpenSquilla 目前要求用户自己知道 `opensquilla migrate hermes`。

需要做的事情：

- 在 first-run setup、gateway/dashboard onboarding 中检测 `~/.hermes`。
- 如果 `~/.opensquilla` 还没有有效配置，优先提示 dry-run。
- 打印精确 apply 命令，但 secrets 仍必须显式 opt-in。

验收标准：

- Hermes 用户安装 OpenSquilla 后，不看文档也能看到迁移入口。
- 不会在用户未确认时迁移 secrets。

#### 10. 加真实 gateway/CLI E2E harness

问题：

手动 E2E 已验证过：Hermes 设计人设、启动 gateway、CLI 对话验证、清空 OpenSquilla、迁移、启动 OpenSquilla gateway、CLI 对话验证迁移效果。但自动测试目前主要是合成 home 和文件断言。

需要做的事情：

- 增加 opt-in integration test，不放进默认快速 CI。
- 使用 deterministic local OpenAI-compatible test server，避免真实外部 API。
- 迁移前后都通过 gateway + CLI 对话验证同一个 persona marker。
- 测试结束清理临时 homes、ports 和 gateway 进程。

验收标准：

- 开发者能用一个明确命令跑完整真实链路。
- 测试能稳定证明“文件迁了”之外，“运行时真的吃到了迁移结果”。

#### 11. 建迁移 parity matrix

问题：

以后继续改迁移功能时，可能有人新增 option id 或改行为，但文档和测试没同步。

需要做的事情：

- 新增 parity matrix，列出每个 Hermes artifact/option：
  - 是否支持；
  - 是 native map、archive-only、manual step，还是 unsupported；
  - 对应测试文件；
  - 对应 report/warning 行为。
- 加测试确保 `MIGRATION_OPTIONS` 里的每个 option id 都在 matrix 中出现。

验收标准：

- 代码、文档、测试对支持范围保持一致。
- 新增 option id 时，不能静默绕过文档和测试。

## 推荐执行顺序

1. 先修 `--overwrite` item-level backup。
2. 再加 apply 前完整 pre-migration backup。
3. 加 report 顶层 `warnings`、`next_steps` 和通用递归脱敏。
4. 加 `MIGRATION_NOTES.md`。
5. 清理/补齐 accepted option ids，确保每个 include/exclude option 都有真实行为。
6. 扩展 `tools-config`、`approvals-config`、`browser-config`、`session-config`、`gateway-config`、`logging-config`。
7. 加 first-run Hermes 检测和迁移引导。
8. 加 opt-in 的真实 gateway/CLI E2E harness。

这个顺序的原则是：先保证迁移可逆、可解释、可信，再扩大迁移覆盖面。否则覆盖面越大，越容易把不可逆风险扩大。

