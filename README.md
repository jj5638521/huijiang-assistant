# huijiang-assistant

汇江助手规则库｜只读｜以MD为准，PDF为辅｜仅记录差异更新

## 工资结算 Skill（Python 工程骨架）

### 目录结构

- `wage/`：工资结算逻辑入口（当前仅占位）。
- `tools/`：命令行工具示例。
- `tests/`：pytest 测试入口。
- `data/`：示例数据目录（本仓库忽略实际 CSV 文件；直接拖到 `data/`，文件名随意）。

为方便中文路径使用，已提供以下软链接：

- `工资` -> `wage`
- `工具` -> `tools`
- `测试` -> `tests`
- `数据` -> `data`

### 本地运行

- `python3 -m pytest -q`
- `python3 -m tools.demo_settle_person`
