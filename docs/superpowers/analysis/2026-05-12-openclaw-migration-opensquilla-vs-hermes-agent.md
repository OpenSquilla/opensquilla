# OpenSquilla OpenClaw 迁移 vs Hermes Agent OpenClaw 迁移分析

日期：2026-05-12

## 分析范围

本文对比两个从 OpenClaw 迁出的“一键迁移”能力：

- OpenSquilla：`opensquilla migrate openclaw`
- Hermes Agent：`hermes claw migrate`

两者的源都是 OpenClaw home，但目标不同：

- OpenSquilla 把 OpenClaw 迁到 OpenSquilla-native 的 config、workspace、skills、env、gateway config。
- Hermes Agent 把 OpenClaw 迁到 Hermes-native 的 config.yaml、memories、skills、.env、Hermes runtime config。

因此这里不能只看 option 名称是否一样，还要看每个 option 最终落到目标系统哪里、是否可运行、是否可逆、是否给用户明确后续动作。

证据来自本地代码：

- `opensquilla/src/opensquilla/migration/openclaw.py`
- `opensquilla/src/opensquilla/cli/migrate_cmd.py`
- `opensquilla/tests/test_migration/test_openclaw_migration.py`
- `opensquilla/tests/test_migration/test_openclaw_e2e.py`
- `hermes-agent/hermes_cli/claw.py`
- `hermes-agent/hermes_cli/setup.py`
- `hermes-agent/optional-skills/migration/openclaw-migration/scripts/openclaw_to_hermes.py`

## 总结结论

OpenSquilla 的 OpenClaw 迁移比刚实现的 Hermes-to-OpenSquilla 迁移成熟很多，已经接近 Hermes Agent 的 OpenClaw 迁移器：有 dry-run/apply 分离、secrets opt-in、include/exclude/preset、技能冲突策略、item-level backup、report/summary、`MIGRATION_NOTES.md`、OpenClaw 品牌语义转换、内存 overflow 归档、技能 frontmatter 兼容性检查，以及大量测试覆盖。

但它和 Hermes Agent 的 OpenClaw 迁移仍有差距：

1. OpenSquilla 没有 Hermes Agent CLI wrapper 那层 apply 前完整 home 备份、冲突拒绝执行、setup wizard 主动引导。
2. Hermes Agent 覆盖的 OpenClaw runtime surface 更广，尤其是 WhatsApp/Signal、full-providers、deep-channels、browser/tools/approvals/session/gateway 等深层映射；OpenSquilla 有些是 archive-only 或 notes-only。
3. OpenSquilla report 结构还缺顶层 `warnings` / `next_steps`，虽然已经有 `MIGRATION_NOTES.md`。
4. OpenSquilla 是 OpenSquilla-native 目标，部分 Hermes 专属迁移项不应该照搬，但需要更清晰地标注“已 native map / 已 archive / 不支持 / 不适用”。

## 已经对齐的能力

### 1. 命令入口和 dry-run/apply 分离

OpenSquilla CLI：

- `opensquilla/src/opensquilla/cli/migrate_cmd.py:93` 定义 `migrate openclaw` 命令。
- `opensquilla/src/opensquilla/cli/migrate_cmd.py:108` 暴露 `--apply`，不传时只生成 dry-run report。
- `opensquilla/src/opensquilla/cli/migrate_cmd.py:142` 的命令说明是 “Migrate OpenClaw state into OpenSquilla-native files.”

OpenSquilla help 实际输出确认了参数面：

```powershell
uv run opensquilla migrate openclaw --help
```

包含 `--source`、`--config`、`--apply`、`--migrate-secrets`、`--overwrite`、`--preset`、`--include`、`--exclude`、`--skill-conflict`、`--json`。

Hermes Agent CLI：

- `hermes-agent/hermes_cli/claw.py:5` 到 `claw.py:8` 给出 `hermes claw migrate --dry-run`、`--yes`、`--overwrite --migrate-secrets`、`--no-backup` 示例。
- `hermes-agent/hermes_cli/claw.py:468` 在 dry-run 下停止。
- `hermes-agent/hermes_cli/claw.py:495` 提示执行时重跑 `hermes claw migrate --yes`。

结论：两边都有预览和执行分离。差异是 OpenSquilla 用 `--apply` 更适合自动化；Hermes Agent 用 `--dry-run`/确认/`--yes` 更适合交互式迁移。

### 2. secrets 都是显式 opt-in

OpenSquilla：

- `opensquilla/src/opensquilla/cli/migrate_cmd.py:112` 暴露 `--migrate-secrets`。
- `opensquilla/src/opensquilla/migration/openclaw.py:81` 定义可识别的 secret env keys。
- `opensquilla/src/opensquilla/migration/openclaw.py:843`、`openclaw.py:1095`、`openclaw.py:1110`、`openclaw.py:1165` 等位置都以 `self.options.migrate_secrets` 为条件。

Hermes Agent：

- `hermes-agent/optional-skills/migration/openclaw-migration/scripts/openclaw_to_hermes.py:36` 定义 `SUPPORTED_SECRET_TARGETS`。
- `openclaw_to_hermes.py:100` 明确 provider API keys 需要 `--migrate-secrets`。
- `openclaw_to_hermes.py:1374` 和 `openclaw_to_hermes.py:1508` 会提示用户重跑时加 `--migrate-secrets`。

结论：默认不搬 secrets 这一点是对齐的。

### 3. 都支持 preset/include/exclude 和 skill conflict

OpenSquilla：

- `opensquilla/src/opensquilla/migration/openclaw.py:74` 定义 `MIGRATION_OPTIONS`。
- `opensquilla/src/opensquilla/migration/openclaw.py:76` 定义 `MIGRATION_PRESETS`。
- `opensquilla/src/opensquilla/migration/openclaw.py:33` 定义 `SKILL_CONFLICT_MODES = {"skip", "overwrite", "rename"}`。
- `opensquilla/src/opensquilla/cli/migrate_cmd.py:57`、`:61` 校验 include/exclude。
- `opensquilla/src/opensquilla/cli/migrate_cmd.py:65` 校验 skill conflict。

Hermes Agent：

- `openclaw_to_hermes.py:187` 定义 `MIGRATION_PRESETS`。
- `openclaw_to_hermes.py:35` 定义 `SKILL_CONFLICT_MODES`。
- `openclaw_to_hermes.py:895` 到 `openclaw_to_hermes.py:955` 通过 `run_if_selected(...)` 执行所选迁移模块。

### 4. 都有 item-level backup

OpenSquilla：

- `opensquilla/src/opensquilla/migration/openclaw.py:550` 在目标存在且未 overwrite 时记录 `conflict`。
- `opensquilla/src/opensquilla/migration/openclaw.py:554` overwrite 前调用 `_backup_file(destination)`。
- `opensquilla/src/opensquilla/migration/openclaw.py:698` 技能 overwrite 前调用 `_backup_dir(target)`。
- `opensquilla/src/opensquilla/migration/openclaw.py:734` TTS assets overwrite 前调用 `_backup_dir(destination)`。
- `opensquilla/src/opensquilla/migration/openclaw.py:1440` 和 `openclaw.py:1444` 是 `_backup_file` / `_backup_dir` 实现。

Hermes Agent：

- `openclaw_to_hermes.py:385` 是 `backup_existing(path, backup_root)`。
- `openclaw_to_hermes.py:1094` 是 `maybe_backup(...)`。
- `openclaw_to_hermes.py:1122`、`:1185`、`:1299`、`:1711`、`:1860`、`:1970`、`:2174` 等路径在写入前调用备份。

结论：OpenSquilla OpenClaw 迁移已经比 Hermes-to-OpenSquilla 迁移强，具备 item-level backup。

### 5. 都有报告、summary、迁移 notes

OpenSquilla：

- `opensquilla/src/opensquilla/migration/openclaw.py:1462` 写 report files。
- `openclaw.py:1465` 写 `report.json`。
- `openclaw.py:1486` 写 `summary.md`。
- `openclaw.py:1487` 调用 `_write_migration_notes()`。
- `openclaw.py:1489` 到 `openclaw.py:1502` 写 `MIGRATION_NOTES.md`。

Hermes Agent：

- `openclaw_to_hermes.py:655` 是 `write_report(...)`。
- `openclaw_to_hermes.py:660` 写报告前先 redacted。
- `openclaw_to_hermes.py:685` 输出 warnings。
- `openclaw_to_hermes.py:702` 输出 next_steps。
- `openclaw_to_hermes.py:2845` 生成 `# OpenClaw -> Hermes Migration Notes`。
- `openclaw_to_hermes.py:2955` 写 `MIGRATION_NOTES.md`。

结论：两边都有迁移产物目录和人类可读 notes。Hermes Agent 的 report schema 更丰富，OpenSquilla 的 notes 机制已经存在但还可增强。

### 6. 都做 OpenClaw 品牌语义转换

OpenSquilla：

- `opensquilla/src/opensquilla/migration/openclaw.py:303` 是 `_rebrand_text(...)`。
- `openclaw.py:564` 和 `openclaw.py:610` 在 item details 中记录 `semantic_conversions = ["openclaw-branding"]`。
- 测试 `opensquilla/tests/test_migration/test_openclaw_migration.py:576` 断言语义转换被记录。

Hermes Agent：

- `openclaw_to_hermes.py:399` 到 `openclaw_to_hermes.py:407` 定义把 OpenClaw/ClawdBot/MoltBot 替换成 Hermes 的 rebrand 规则。
- `openclaw_to_hermes.py:430` 是 `rebrand_text(...)`。
- `openclaw_to_hermes.py:1140`、`:1154`、`:1165`、`:1910` 在迁移 persona/workspace/memory 时使用 `rebrand_text`。

结论：两边都意识到“直接复制 OpenClaw 自我描述会污染新运行时人设”，这点是对齐的。

## 关键差异

### 1. OpenSquilla 没有 Hermes Agent 的 apply 前完整 home 备份

Hermes Agent：

- `hermes-agent/hermes_cli/claw.py:501` 开始 pre-apply backup 阶段。
- `claw.py:511` 导入 `create_pre_migration_backup`。
- `claw.py:512` 调用 `create_pre_migration_backup(hermes_home=hermes_home)`。
- `claw.py:516` 打印备份大小。
- `claw.py:517` 打印 restore 命令。
- `claw.py:520` 到 `claw.py:524` 在备份失败时提示 `--no-backup` 或清理空间。

OpenSquilla：

- 有 item-level backup，但没有类似 “apply 前完整备份 `~/.opensquilla`” 的 wrapper 层。
- `opensquilla/src/opensquilla/migration/openclaw.py:1440` / `:1444` 只备份被覆盖的单个 file/dir。
- `opensquilla/src/opensquilla/migration/openclaw.py:1424` 调用 `persist_config(..., backup=True, restart_required=True)`，这对 config 有备份价值，但不是完整 home 级 snapshot。

结论：OpenSquilla 的 OpenClaw 迁移已经有局部可逆性，但还没有 Hermes Agent 那种“一次迁移前完整快照”的保险。

### 2. Hermes Agent CLI 会在冲突时拒绝 apply，OpenSquilla 目前更偏记录 conflict 后继续

Hermes Agent：

- `hermes-agent/hermes_cli/claw.py:472` 进入 “Refuse if the plan has conflicts and --overwrite is not set”。
- `claw.py:477` 判断 `preview_conflicts > 0 and not overwrite`。
- `claw.py:480` 打印 refusing to apply。
- `claw.py:484` 提示 `--overwrite` 和 item-level backups。

OpenSquilla：

- `opensquilla/src/opensquilla/migration/openclaw.py:550` 对目标已存在且未 overwrite 的项目记录 `conflict`。
- 迁移主流程 `openclaw.py:361` 继续执行后续可迁项目，最后返回 report。

结论：OpenSquilla 更适合“尽量迁能迁的项”，Hermes Agent 更偏“有冲突先停下来让用户明确选择”。作为一键迁移工具，OpenSquilla 可以考虑提供 `--strict-conflicts` 或默认 apply 阶段拒绝高风险冲突。

### 3. Hermes Agent 通过 setup wizard 主动引导 OpenClaw 迁移

Hermes Agent：

- `hermes-agent/hermes_cli/setup.py:2907` 在用户跳过时提示之后运行 `hermes claw migrate --dry-run`。
- `setup.py:2935` 在 setup 中创建 preview migrator。
- `setup.py:2968` 提示 `--dry-run` 和 `--preset minimal`。
- `setup.py:2980` setup 中执行迁移时使用 `overwrite=False` 保护已有 Hermes config。
- `setup.py:3003` 汇总冲突并提示 `--overwrite`。

OpenSquilla：

- 当前只有 `opensquilla migrate openclaw` 独立命令。
- 没有看到 first-run setup/dashboard/gateway 启动时检测 `~/.openclaw` 并提示 dry-run 的入口。

结论：OpenSquilla 的命令能力已经比较强，但 onboarding 发现能力弱。新用户如果不知道命令，就不会触发迁移。

### 4. Hermes Agent 的 OpenClaw option surface 更广

OpenSquilla option set：

- `opensquilla/src/opensquilla/migration/openclaw.py:38` 到 `openclaw.py:47` 是 user data options。
- `openclaw.py:49` 到 `openclaw.py:72` 是 runtime config options。
- 包含 `telegram-settings`、`discord-settings`、`slack-settings`，但没有 `whatsapp-settings`、`signal-settings`、`full-providers`、`deep-channels`、`messaging-settings`、`secret-settings`。

Hermes Agent option set：

- `openclaw_to_hermes.py:48` 到 `openclaw_to_hermes.py:184` 有更完整的 metadata。
- 明确包含 `messaging-settings`、`secret-settings`、`whatsapp-settings`、`signal-settings`、`full-providers`、`deep-channels`。
- 主流程 `openclaw_to_hermes.py:895` 到 `openclaw_to_hermes.py:955` 覆盖所有这些模块。

结论：Hermes Agent 对 OpenClaw 的渠道、Provider、深层 runtime 设置覆盖更广。OpenSquilla 不一定要照搬 Hermes 专属项，但应该有 parity matrix 明确说明“不适用 / 已归档 / 待支持”。

### 5. OpenSquilla 对部分 deep config 是 archive-only，Hermes Agent 有更多 native mapping

OpenSquilla：

- `opensquilla/src/opensquilla/migration/openclaw.py:1065` 有 `_migrate_tools_config`。
- `openclaw.py:1311` 有 `_archive_tts_config`。
- `openclaw.py:1335` 有 `_archive_unmapped_config`。
- `openclaw.py:1366` 有 `_archive_openclaw_artifacts`。
- `openclaw.py:1268` 对 WhatsApp/Signal 只写 note：检测到配置，但 OpenSquilla 还没有 native migrated channel entry。

Hermes Agent：

- `openclaw_to_hermes.py:2398` 有 `migrate_gateway_config`。
- `openclaw_to_hermes.py:2419` 有 `migrate_session_config`。
- `openclaw_to_hermes.py:2482` 有 `migrate_full_providers`。
- `openclaw_to_hermes.py:2556` 有 `migrate_deep_channels`。
- `openclaw_to_hermes.py:2644` 有 `migrate_browser_config`。
- `openclaw_to_hermes.py:2684` 有 `migrate_tools_config`。
- `openclaw_to_hermes.py:2728` 有 `migrate_approvals_config`。
- `openclaw_to_hermes.py:2807` 有 `migrate_logging_config`。

结论：OpenSquilla 的 OpenClaw 迁移已经会归档大量不直接支持的配置，但在 deep runtime native mapping 上少于 Hermes Agent。

### 6. OpenSquilla 有 OpenSquilla-specific 的优势

OpenSquilla 不是简单复制 Hermes 迁移器，它做了一些符合 OpenSquilla 目标系统的事情：

- `opensquilla/src/opensquilla/migration/openclaw.py:1424` 用 `persist_config(..., restart_required=True)` 写入 OpenSquilla config，符合 OpenSquilla gateway 配置生命周期。
- `openclaw.py:915` 到 `openclaw.py:962` 把 MCP server 转成 OpenSquilla `MCPServerEntry`。
- `openclaw.py:1145` 到 `openclaw.py:1280` 把 Telegram/Discord/Slack 转成 OpenSquilla channels，并把 OpenClaw admin users 映射到 `channel_admin_senders`。
- `openclaw.py:766` 到 `openclaw.py:810` 检查迁移后的 skills 是否具备 OpenSquilla 可加载 frontmatter。
- 测试 `opensquilla/tests/test_migration/test_openclaw_migration.py:713` 验证迁移后的 workspace 和可加载 skills 能被 OpenSquilla 消费。

结论：OpenSquilla 的优势是迁移目标更贴近 OpenSquilla runtime，而不是为了和 Hermes 的 config.yaml 完全同构。

## OpenSquilla 后续优化项

### P0：补齐迁移安全网

#### 1. 增加 apply 前完整 home snapshot

问题：

OpenSquilla 有 item-level backup，但没有 apply 前完整备份 `~/.opensquilla`。如果某次迁移写了多个文件、config、env、skills，用户还原时需要从多个备份点拼回去。

需要做的事情：

- 在 `MigrationOptions` 增加 `no_backup: bool = False`，CLI 增加 `--no-backup`。
- 默认 `--apply` 前创建 `~/.opensquilla/backups/pre-openclaw-migration-<timestamp>.zip`。
- 备份失败时在任何写入前中止。
- 在 `report.json`、`summary.md`、`MIGRATION_NOTES.md` 中记录 backup path 和 restore 指引。

验收标准：

- `opensquilla migrate openclaw --apply` 默认生成完整 pre-migration backup。
- 备份失败时不会部分写入。
- 用户能按 report 中的路径恢复。

#### 2. 增加 strict conflict 模式

问题：

当前 OpenSquilla 会记录 conflict 并继续迁移其他项目。这个行为适合批处理，但一键迁移时容易让用户误以为“全部完成”。

需要做的事情：

- 增加 `--strict-conflicts` 或 `--fail-on-conflict`。
- 在 apply 前先跑 preview plan；如果存在 conflict 且未 `--overwrite`，直接退出。
- JSON 输出中保留冲突列表。

验收标准：

- 用户可以选择 Hermes Agent 那种“有冲突不执行”的安全模式。
- 默认模式是否保持“尽量迁移”可以再按产品体验决定，但必须文档化。

### P1：补齐 runtime coverage 和 parity matrix

#### 3. 建 OpenClaw migration parity matrix

问题：

OpenSquilla 和 Hermes Agent 的 option set 不完全相同，有些差异是目标系统不同导致的，有些是真缺口。现在缺少一张表把这些差异说清楚。

需要做的事情：

- 新增矩阵列：
  - OpenClaw artifact / config path；
  - Hermes Agent behavior；
  - OpenSquilla behavior；
  - OpenSquilla status：native-map / archive-only / notes-only / unsupported / not-applicable；
  - 对应测试；
  - 下一步计划。
- 加测试确保 `MIGRATION_OPTIONS` 每个 option 都在矩阵中。

验收标准：

- 新增 option id 时必须同步文档和测试。
- 用户能明确知道哪些没迁、为什么没迁。

#### 4. WhatsApp/Signal 从 notes-only 提升到 archive 或 native mapping

问题：

OpenSquilla 在 `openclaw.py:1268` 检测到 WhatsApp/Signal 后只写 notes。Hermes Agent 则有 `migrate_whatsapp_settings` 和 `migrate_signal_settings`。

需要做的事情：

- 如果 OpenSquilla 还没有 native channel 类型，至少把 WhatsApp/Signal config archive 到 migration output。
- report item 不应只靠 `_note`，应该有 `whatsapp-settings` / `signal-settings` 或 `deep-channels` 对应 item。
- 如果 OpenSquilla 后续支持这些 channel，再升级为 native map。

验收标准：

- 检测到 WhatsApp/Signal 时，report 里有可检索 item。
- 原始设置不会只藏在 notes 文本里。

#### 5. full-providers / custom providers 支持

问题：

Hermes Agent 有 `full-providers`，能把 OpenClaw `models.providers` 中自定义 baseUrl/apiType/headers 映射到 Hermes `custom_providers`。OpenSquilla 当前主要通过 provider keys 和 model config 迁移常见 provider，缺少完整 custom provider 行为。

需要做的事情：

- 梳理 OpenSquilla provider model 是否支持 OpenAI-compatible custom endpoint。
- 对 OpenClaw `models.providers.*.baseUrl/baseURL/apiType/headers` 做 native map。
- 对不能安全迁移的 headers 做脱敏 archive 和 manual step。

验收标准：

- OpenClaw 自定义 provider 可以迁到 OpenSquilla 并通过 CLI/gateway smoke test。
- secrets 和 headers 不会明文进入 report。

#### 6. browser/session/gateway/approvals/logging 明确 map vs archive

问题：

OpenSquilla 已接受这些 option id，并有 archive 机制；但和 Hermes Agent 相比，native mapping 深度不足。

需要做的事情：

- `gateway-config`：映射 host/port/auth 中 OpenSquilla 有直接字段的部分。
- `session-config`：映射 OpenSquilla 有等价语义的 reset/retention；其余 archive。
- `browser-config`：如果 OpenSquilla 支持 browser tool，映射 enable/headless/cdpUrl；否则 archive 并 warning。
- `approvals-config`：映射 approval mode；复杂 rules archive。
- `logging-config`：归档 logging/diagnostics，并在 notes 里提示人工检查。

验收标准：

- 每个 option id 都能在 report 中看到明确 migrated/archived/skipped/conflict。
- 不存在用户传 `--include xxx` 但只得到隐性 no-op 的情况。

### P1：增强报告质量

#### 7. report 顶层增加 warnings 和 next_steps

问题：

OpenSquilla 已有 `MIGRATION_NOTES.md`，但 JSON report 没有 Hermes Agent 那种顶层 `warnings` / `next_steps`。这会影响自动化消费和 dashboard 展示。

需要做的事情：

- 在 `_report()` 中增加 `warnings`、`next_steps`。
- 从 `_notes`、conflict、skipped secrets、archive-only items 生成 warnings。
- 从迁移结果生成 next steps，例如启动 gateway、运行 CLI 对话、检查 `MIGRATION_NOTES.md`、处理未迁移 secrets。

验收标准：

- `--json` 能直接告诉上层 UI 是否需要人工处理。
- `summary.md` 和 `MIGRATION_NOTES.md` 使用同一份 warnings/next_steps 数据。

#### 8. 扩展脱敏为统一递归 redactor

问题：

OpenSquilla OpenClaw 迁移已有 `_redact_value`，并且测试覆盖 archive secret redaction。但报告写入前最好像 Hermes Agent 一样做统一兜底。

需要做的事情：

- 在写 `report.json` 和 stdout JSON 前统一递归 redaction。
- 保留按 key 和按 token-like value 的双重判断。
- 增加测试覆盖 nested details、notes、warnings、archived config summaries。

验收标准：

- 任何 report 输出路径都不会泄漏 token-like 明文。
- 新增 item details 时不需要每个调用点手动记得脱敏。

### P2：提升 onboarding 和真实 E2E

#### 9. first-run 主动检测 OpenClaw

问题：

Hermes Agent setup wizard 会发现 OpenClaw 并提示迁移。OpenSquilla 当前只有命令。

需要做的事情：

- 在 first-run setup/dashboard/gateway onboarding 中检测 `~/.openclaw`。
- 如果 `~/.opensquilla` 为空或未完成配置，提示先跑 dry-run。
- 明确告诉用户 secrets 不会默认迁移。

验收标准：

- 新用户首次启动 OpenSquilla 时能看到 OpenClaw 迁移入口。
- 不需要读文档才能发现迁移命令。

#### 10. 增加真实 gateway/CLI E2E harness

问题：

文件级迁移测试已经不少，但真实用户关心的是迁移后 OpenSquilla gateway 和 CLI 是否真的吃到 persona/config/skills。

需要做的事情：

- 增加 opt-in integration test。
- 使用 deterministic local OpenAI-compatible test server。
- 流程：构造 OpenClaw persona -> 迁移 -> 启 OpenSquilla gateway -> CLI 对话验证 persona marker。
- 清理临时 home、ports、进程。

验收标准：

- 一条命令证明 OpenClaw -> OpenSquilla 不只是文件写对，而是运行时可用。
- 不依赖真实外部模型 API。

## 验证记录

已尝试运行：

```powershell
uv run pytest tests/test_migration/test_openclaw_migration.py tests/test_migration/test_openclaw_e2e.py -q --basetemp ... -p no:cacheprovider
```

当前 Windows 环境下未得到有效业务测试结果。失败点是 pytest 创建/清理临时目录时触发 `PermissionError: [WinError 5] 拒绝访问`，路径包括：

- `C:\Users\12445\AppData\Local\Temp\pytest-of-12445`
- `D:\projects\agents\agents\opensource\opensquilla\.tmp-pytest-openclaw\basetemp-*`

这个失败发生在 pytest `tmp_path` fixture setup/cleanup 阶段，不是迁移代码断言失败。后续如果要拿 clean test signal，需要先清理/修复 Windows 临时目录 ACL 或换到 WSL2/POSIX 环境运行。

## 推荐执行顺序

1. 加 apply 前完整 pre-migration backup。
2. 加 `--strict-conflicts` / `--fail-on-conflict`。
3. 建 OpenClaw migration parity matrix，并让测试约束 `MIGRATION_OPTIONS`。
4. 把 WhatsApp/Signal 从 notes-only 升级为 archive item 或 native channel mapping。
5. 补 full-providers/custom providers 迁移。
6. 明确 browser/session/gateway/approvals/logging 的 native map vs archive 行为。
7. report 顶层增加 warnings/next_steps。
8. 统一 report/stdout JSON 递归脱敏。
9. first-run 检测 OpenClaw 并引导 dry-run。
10. 加 opt-in gateway/CLI 真实 E2E。

