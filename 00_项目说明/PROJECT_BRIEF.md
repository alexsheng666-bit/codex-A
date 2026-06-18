# Project Brief

Project: A股短线助手
Owner: alexsheng
Start date: 2026-06-15
Target delivery date: 待确认
Status: Active

## Goal

建立「A股短线助手」项目的正式工作区，并为后续产品规划、资料整理、代码开发、交付和复盘提供统一目录。

## Background

用户已创建 GitHub 仓库：

`https://github.com/alexsheng666-bit/codex-A`

本地项目文件夹尚未建立，因此按全局工作台规则创建项目 `P002_A股短线助手`。

## Scope

- 创建符合工作区 SOP 的标准项目目录。
- 记录项目启动信息、仓库地址和关键约束。
- 为后续代码开发、产品文档、市场资料和交付物预留位置。

## Inputs

- GitHub 仓库地址：`https://github.com/alexsheng666-bit/codex-A`
- 工作区规范：`GLOBAL_WORKBENCH.md`
- 新项目 SOP：`NEW_PROJECT_SOP.md`

## Outputs

- 标准项目目录结构。
- 项目启动说明。
- 基础 README。
- 基础 Git 忽略规则。

## Constraints

- 项目文件应集中保存在本项目目录内。
- 原始资料应放入 `01_原始资料`，不得直接覆盖。
- 最终交付物只放入 `03_交付物`。
- 涉及 A 股、行情、交易策略或金融判断时，必须关注数据来源、时效性和合规边界；项目输出不应被表述为投资建议。
- 不在公开仓库中保存 API Key、交易账户、Token、Cookie 或其他敏感凭据。

## Decisions

- 项目编号：`P002`
- 项目目录：`/Users/alexsheng/Documents/Codex/Workspace/projects/P002_A股短线助手`
- 项目仓库：`https://github.com/alexsheng666-bit/codex-A`
- 初始状态：`Active`
- 第一版产品方向：盘后候选池整理助手，优先做可解释筛选、风险提示、次日观察和复盘记录。
- 第一版数据路线：CSV 优先，AKShare 作为自动化适配器，Tushare 作为后续增强。
- 第一版股票池：上证主板 + 深证主板，剔除 ST、*ST、创业板、科创板、北交所、B 股和退市整理股票。
- 第一版重点主题：电力股、科技股、商业航天、半导体、PCB 概念。
- 第一版候选池：A 池重点关注、B 池观察候补、C 池题材异动记录，每只股票必须有入池原因、风险标签和次日验证条件。
- 第一版策略框架：14:50 生成尾盘第一版推荐，14:55 用最新价格、成交量、换手率等数据校验并形成最终推荐后模拟买入；次日优先按纪律处理，单票仓位不超过总资金 10%-15%，止损约 -2% 到 -3%。
- 第一版规则表达：用 `STRATEGY_RULE_TABLE.md` 保存人工可读规则，用 `work/rules/strategy_rules.json` 保存机器可读草案。
- 第一版可运行原型：用 `sample_market_data.csv` 作为 CSV 模板，用 `work/scripts/screen_candidates.py` 生成标准化候选池、卡片式 Markdown 报告和静态 HTML 报告。
- 第一版本地看板：用 `work/scripts/build_dashboard.py` 生成 `dashboard/index.html`，用 `work/scripts/serve_dashboard.py` 启动本地服务。

## Open Questions

- GitHub 仓库当前是公开仓库还是私有仓库？
- 第一阶段要优先做产品需求文档、数据分析脚本、前端页面、后端服务，还是完整应用原型？
- 是否已有目标数据源、行情接口或选股规则？
- 是否需要部署到网页、本地桌面应用、小程序，或只作为个人工具使用？
