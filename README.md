# huijiang-assistant

汇江助手规则库｜只读｜以MD为准，PDF为辅｜仅记录差异更新

## 工资结算 Skill（Python 工程骨架）

### 目录结构

- `wage/`：工资结算逻辑入口（当前仅占位）。
- `tools/`：命令行工具示例。
- `tests/`：pytest 测试入口。
- `data/`：示例数据目录（推荐把本次 CSV 拖到 `data/当前/`；历史 CSV 放 `data/归档/`；文件名随意）。

为方便中文路径使用，已提供以下软链接：

- `工资` -> `wage`
- `工具` -> `tools`
- `测试` -> `tests`
- `数据` -> `data`

### 本地运行

- `python3 -m pytest -q`
- `python3 -m tools.demo_settle_person`（推荐把本次文件拖到 `数据/当前/`；历史放 `数据/归档/`）
- `python3 -m tools.demo_settle_project`（项目结算批量出单，CSV 放 `数据/当前/`）
- 在 `数据/当前/口令.txt`（UTF-8）中填写口令，例如：
  - `工资：王怀宇 组长 项目已结束=是 项目=溧马一溧芜设标-凌云`
  - `项目结算：项目=溧马一溧芜设标-凌云 项目已结束=是`

### PR 审查提示（可选但建议）

仓库已内置 PR 模板，默认在描述中包含 `@codex review`，用于触发准自动审查（无需升级套餐）。
