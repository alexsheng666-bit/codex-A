# Strategy Config Guide

Version: 0.1
Date: 2026-06-16
Status: Draft

## 目的

这份说明用于日常调整 `work/rules/strategy_rules.json`，不需要改代码。

当前配置会同时影响：

- 数据采集时的重点主题识别。
- 候选筛选时的主题标签和入池上限。
- 看板侧边栏的“规则配置”显示。
- 启动窗口里的“规则配置”状态检查。

## 调整入池上限

修改前建议先备份：

```bash
python3 work/scripts/backup_strategy_rules.py
```

备份会保存到：

```text
work/rules/backups
```

查看已有备份：

```bash
python3 work/scripts/restore_strategy_rules.py
```

恢复某个备份：

```bash
python3 work/scripts/restore_strategy_rules.py --restore strategy_rules_20260616_004801.json --yes
```

恢复前脚本会自动再备份一次当前规则文件，避免误覆盖。

配置位置：

```json
"pool_caps": {
  "A": 5,
  "B": 10,
  "C": 20
}
```

含义：

- `A`：重点关注，建议保持少而精。
- `B`：观察候补，适合保留次一级机会。
- `C`：题材异动记录，适合复盘和观察，不应过多干扰主看板。

常见改法：

- 如果 A 池太少：把 `"A": 5` 改成 `"A": 8`。
- 如果 C 池太吵：把 `"C": 20` 改成 `"C": 10`。
- 不建议把 A 池开得太大，否则“重点关注”会失去筛选意义。

## 调整重点主题

配置位置：

```json
"theme_keywords": {
  "电力": ["电力", "火电", "水电"],
  "科技": ["科技", "软件", "人工智能"]
}
```

每个主题由“主题名”和“关键词列表”组成。主题匹配只允许使用可信行业、概念或人工验证主题字段；禁止使用股票名称、股票简称或股票代码推断行业/主题。

## 标签来源纪律

- 禁止凭股票名称、股票简称、代码前缀或代码段直接猜测行业、板块或题材。
- 股票名称和代码只能用于展示、搜索、主板范围过滤、ST/退市风险识别，不能参与主题关键词匹配。
- 新增或修正行业标签前，必须优先联网查该股票最新主营业务构成、公司公告/年报/交易所资料或可靠金融数据源。
- 行业归类以实际主营业务匹配申万一级行业为准；资料不足时行业/主题留空，等待人工核对，不做兜底猜测。

示例：给科技主题增加机器人关键词：

```json
"科技": ["科技", "软件", "人工智能", "机器人"]
```

示例：新增低空经济主题：

```json
"低空经济": ["低空经济", "eVTOL", "飞行汽车", "无人机"]
```

## 替换还是追加默认主题

配置项：

```json
"replace_theme_keywords": false
```

建议保持 `false`。

- `false`：在默认主题基础上覆盖或追加配置，最稳。
- `true`：完全使用配置文件里的主题，适合后续做独立策略版本。

## 修改后如何检查

推荐检查：

```bash
python3 work/scripts/status_check.py
```

看这几行：

```text
规则配置: 正常 (work/rules/strategy_rules.json)
入池上限: A5 | B10 | C20
重点主题: 电力，科技，商业航天，半导体，PCB
```

如果 JSON 写错或主题为空，会看到“需检查”和具体提醒。

## 修改后如何生效

方式一：双击先刷新再查看：

```text
start_dashboard_refresh.command
```

方式二：看板右上角点击“刷新数据”。

方式三：命令行刷新：

```bash
python3 work/scripts/refresh_dashboard_data.py
```

## 注意事项

- JSON 里的英文逗号、双引号不能漏。
- 池子上限只能填非负整数。
- 关键词越宽，命中的股票越多，候选池会更吵。
- 关键词越窄，候选池更干净，但可能漏掉相关股票。
- 每次大改配置前，先运行 `python3 work/scripts/backup_strategy_rules.py`。
- 如果要恢复旧配置，先运行 `python3 work/scripts/restore_strategy_rules.py` 查看可用备份。
- 本项目只做复盘和候选整理，不构成投资建议。
