# Local Sales AI MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 开发一个单机本地网页应用，让业务员可以导入 Excel 报价/合同、本地素材和优秀话术，并通过中文 AI 问答获得回复思路、标准回复、历史报价比对和素材推荐。

**Architecture:** 采用本地 FastAPI 服务 + SQLite 数据库 + 原生 HTML/CSS/JavaScript 页面。后端负责 Excel 导入、结构化存储、检索、AI 上下文组装和本地文件索引；前端只做本机页面交互，不做多人权限和外部聊天工具集成。

**Tech Stack:** Python 3.11+、FastAPI、SQLite、SQLAlchemy、Alembic、openpyxl、Jinja2、pytest、Playwright 或 FastAPI TestClient、可插拔 AI provider adapter。

---

## 0. 关键假设

- 当前项目是空项目，只有 `raw/` 原始资料和 `docs/prd-local-sales-ai.md`。
- 一期只服务单个业务员本机使用。
- 报价单和合同只支持固定 Excel 模板导入。
- AI 输出和客户标准回复都使用中文。
- 云端 AI 只接收当前问题相关片段，不上传整个知识库。
- 图片、视频、报告只做本地文件索引和打开，不做自动视觉识别。
- 话术学习不训练模型，只做“AI 总结 → 人工确认 → 生效”。

## 1. 里程碑安排

| 阶段 | 目标 | 验收 |
| --- | --- | --- |
| M1 基础工程 | 本地 Web 服务、数据库、测试框架可运行 | `pytest` 通过，首页可打开 |
| M2 Excel 导入 | 报价单、合同按模板导入并检索 | 可查客户历史价格和合同 |
| M3 素材库 | 图片/视频/报告可登记、搜索、打开 | 问答能返回推荐素材 |
| M4 AI 问答 | 基于知识片段生成中文回复结构 | 输出包含五段固定结构 |
| M5 新老订单比对 | 对客户新订单和历史记录做差异比对 | 能标出新增型号和配置变化 |
| M6 话术模板 | 聊天记录可总结、人工确认、生效 | 未确认模板不会用于问答 |
| M7 本地 UI 完整化 | 四个页面串通主流程 | 业务员可通过网页完成一期流程 |
| M8 打包与验收 | 本地启动说明、样例数据、验收用例完成 | 按 PRD 五个用例手工验收通过 |

## 2. 目标文件结构

```text
/Users/wgxxx/gitee/ai-qa/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── excel_importer.py
│   │   ├── quote_search.py
│   │   ├── material_search.py
│   │   ├── order_compare.py
│   │   ├── prompt_builder.py
│   │   ├── ai_provider.py
│   │   └── speech_template.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── pages.py
│   │   ├── qa.py
│   │   ├── imports.py
│   │   ├── materials.py
│   │   └── templates.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── knowledge.html
│   │   ├── materials.html
│   │   └── speech_templates.html
│   └── static/
│       ├── app.css
│       └── app.js
├── data/
│   ├── .gitkeep
│   ├── uploads/.gitkeep
│   └── materials/.gitkeep
├── tests/
│   ├── conftest.py
│   ├── test_excel_importer.py
│   ├── test_quote_search.py
│   ├── test_order_compare.py
│   ├── test_material_search.py
│   ├── test_prompt_builder.py
│   ├── test_speech_template.py
│   └── test_api_flows.py
├── scripts/
│   ├── create_sample_excels.py
│   └── import_raw_manual.py
├── docs/
│   ├── prd-local-sales-ai.md
│   ├── development-local-runbook.md
│   └── superpowers/plans/2026-07-07-local-sales-ai-mvp.md
├── pyproject.toml
├── README.md
└── .env.example
```

## 3. 数据模型

### 3.1 报价记录 `quote_records`

字段：

- `id`
- `customer_name`
- `country`
- `part_number`
- `replacement_numbers`
- `material_grade`
- `steel_thickness`
- `has_shim`
- `packaging`
- `quantity`
- `unit_price`
- `currency`
- `quote_date`
- `valid_until`
- `remark`
- `source_file`
- `created_at`

### 3.2 合同记录 `contract_records`

字段：

- `id`
- `contract_no`
- `customer_name`
- `country`
- `order_date`
- `part_number`
- `material_grade`
- `packaging`
- `quantity`
- `unit_price`
- `currency`
- `delivery_time`
- `payment_terms`
- `remark`
- `source_file`
- `created_at`

### 3.3 素材记录 `materials`

字段：

- `id`
- `name`
- `file_path`
- `material_type`
- `product_type`
- `scenario`
- `brand`
- `material_grade`
- `description`
- `recommended_script`
- `tags`
- `created_at`

### 3.4 话术模板 `speech_templates`

字段：

- `id`
- `scenario`
- `customer_question`
- `style_notes`
- `standard_reply`
- `forbidden_words`
- `recommended_material_ids`
- `status`
- `source_chat`
- `created_at`
- `confirmed_at`

`status` 只允许：

- `draft`：AI 已总结，未确认
- `confirmed`：人工确认，可用于问答
- `disabled`：已停用

## 4. 开发任务

### Task 1: 初始化 Python Web 工程

**Files:**

- Create: `/Users/wgxxx/gitee/ai-qa/pyproject.toml`
- Create: `/Users/wgxxx/gitee/ai-qa/.env.example`
- Create: `/Users/wgxxx/gitee/ai-qa/app/main.py`
- Create: `/Users/wgxxx/gitee/ai-qa/app/config.py`
- Create: `/Users/wgxxx/gitee/ai-qa/app/database.py`
- Create: `/Users/wgxxx/gitee/ai-qa/app/__init__.py`
- Create: `/Users/wgxxx/gitee/ai-qa/tests/conftest.py`
- Create: `/Users/wgxxx/gitee/ai-qa/tests/test_api_flows.py`

- [ ] **Step 1: 创建依赖配置**

  添加 FastAPI、Uvicorn、SQLAlchemy、openpyxl、Jinja2、pytest、httpx。

- [ ] **Step 2: 创建最小 FastAPI 应用**

  `GET /health` 返回：

  ```json
  {"status":"ok"}
  ```

- [ ] **Step 3: 写健康检查测试**

  测试 `GET /health` 返回 200 和 `status=ok`。

- [ ] **Step 4: 运行测试**

  Run:

  ```bash
  pytest tests/test_api_flows.py -v
  ```

  Expected: 健康检查测试通过。

- [ ] **Step 5: 验证本地服务启动**

  Run:

  ```bash
  uvicorn app.main:app --reload
  ```

  Expected: 浏览器访问 `http://127.0.0.1:8000/health` 返回 `{"status":"ok"}`。

### Task 2: 建立数据库模型和初始化流程

**Files:**

- Create: `/Users/wgxxx/gitee/ai-qa/app/models.py`
- Create: `/Users/wgxxx/gitee/ai-qa/app/schemas.py`
- Modify: `/Users/wgxxx/gitee/ai-qa/app/database.py`
- Modify: `/Users/wgxxx/gitee/ai-qa/app/main.py`
- Modify: `/Users/wgxxx/gitee/ai-qa/tests/conftest.py`
- Create: `/Users/wgxxx/gitee/ai-qa/tests/test_database_models.py`

- [ ] **Step 1: 写模型创建测试**

  测试应用启动时可以创建 `quote_records`、`contract_records`、`materials`、`speech_templates` 四张表。

- [ ] **Step 2: 实现 SQLite 连接**

  默认数据库路径为：

  ```text
  /Users/wgxxx/gitee/ai-qa/data/local-sales-ai.sqlite3
  ```

- [ ] **Step 3: 实现 ORM 模型**

  按第 3 节字段创建四个模型。

- [ ] **Step 4: 运行测试**

  Run:

  ```bash
  pytest tests/test_database_models.py -v
  ```

  Expected: 四张表创建成功，字段存在。

### Task 3: 实现报价单 Excel 导入

**Files:**

- Create: `/Users/wgxxx/gitee/ai-qa/app/services/excel_importer.py`
- Create: `/Users/wgxxx/gitee/ai-qa/app/routers/imports.py`
- Modify: `/Users/wgxxx/gitee/ai-qa/app/main.py`
- Create: `/Users/wgxxx/gitee/ai-qa/scripts/create_sample_excels.py`
- Create: `/Users/wgxxx/gitee/ai-qa/tests/test_excel_importer.py`

- [ ] **Step 1: 生成报价单样例 Excel**

  样例包含至少两条报价记录：

  - Ahmed / Libya / D1234 / A+ 半金属 / 1000 / 2.30 / USD
  - Ahmed / Libya / D5678 / AA / 500 / 3.10 / USD

- [ ] **Step 2: 写报价单导入测试**

  测试固定字段完整时导入成功，缺少 `客户名称` 或 `型号` 时返回明确错误。

- [ ] **Step 3: 实现字段映射**

  读取 PRD 中报价单字段，并转换为 `quote_records` 字段。

- [ ] **Step 4: 实现重复记录提示**

  同一 `customer_name + part_number + quote_date` 已存在时，不直接覆盖，返回 `duplicate` 状态。

- [ ] **Step 5: 增加导入接口**

  `POST /api/imports/quotes` 接收 Excel 文件并返回导入数量、失败行、重复行。

- [ ] **Step 6: 运行测试**

  Run:

  ```bash
  pytest tests/test_excel_importer.py -v
  ```

  Expected: 报价单导入、必填校验、重复检测测试通过。

### Task 4: 实现合同 Excel 导入

**Files:**

- Modify: `/Users/wgxxx/gitee/ai-qa/app/services/excel_importer.py`
- Modify: `/Users/wgxxx/gitee/ai-qa/app/routers/imports.py`
- Modify: `/Users/wgxxx/gitee/ai-qa/scripts/create_sample_excels.py`
- Modify: `/Users/wgxxx/gitee/ai-qa/tests/test_excel_importer.py`

- [ ] **Step 1: 生成合同样例 Excel**

  样例包含至少两条合同记录：

  - HT20260707001 / Ahmed / Libya / D1234 / A+ 半金属 / 2000 / 2.25 / USD
  - HT20260707002 / Carlos / Brazil / D8888 / AAA / 800 / 4.20 / USD

- [ ] **Step 2: 写合同导入测试**

  测试固定字段完整时导入成功，缺少 `合同编号`、`客户名称`、`型号` 时返回明确错误。

- [ ] **Step 3: 实现合同字段映射**

  读取 PRD 中合同字段，并转换为 `contract_records` 字段。

- [ ] **Step 4: 增加合同导入接口**

  `POST /api/imports/contracts` 接收 Excel 文件并返回导入数量、失败行、重复行。

- [ ] **Step 5: 运行测试**

  Run:

  ```bash
  pytest tests/test_excel_importer.py -v
  ```

  Expected: 报价单与合同导入测试全部通过。

### Task 5: 实现历史价格查询

**Files:**

- Create: `/Users/wgxxx/gitee/ai-qa/app/services/quote_search.py`
- Modify: `/Users/wgxxx/gitee/ai-qa/app/routers/qa.py`
- Create: `/Users/wgxxx/gitee/ai-qa/tests/test_quote_search.py`

- [ ] **Step 1: 写客户历史价格测试**

  输入 `customer_name=Ahmed`、`part_number=D1234`，期望返回报价记录和合同记录。

- [ ] **Step 2: 实现客户名模糊匹配**

  支持 `Ahmed` 匹配 `Ahmed Trading`，但结果中必须显示真实客户名。

- [ ] **Step 3: 实现型号精确匹配**

  `D1234` 必须优先精确匹配 `part_number`，再匹配 `replacement_numbers`。

- [ ] **Step 4: 增加查询接口**

  `GET /api/search/prices?customer=Ahmed&part_number=D1234` 返回历史报价和合同。

- [ ] **Step 5: 运行测试**

  Run:

  ```bash
  pytest tests/test_quote_search.py -v
  ```

  Expected: 客户历史价格、无记录提示、替换号码检索测试通过。

### Task 6: 实现新老订单比对

**Files:**

- Create: `/Users/wgxxx/gitee/ai-qa/app/services/order_compare.py`
- Create: `/Users/wgxxx/gitee/ai-qa/tests/test_order_compare.py`

- [ ] **Step 1: 写比对测试**

  输入客户 `Ahmed`，新订单型号 `D1234,D5678`，历史只有 `D1234` 时：

  - `D1234` 标记为历史型号
  - `D5678` 标记为新增型号
  - 配置不同项列入 `differences`

- [ ] **Step 2: 实现比对维度**

  按 PRD 比对型号、替换号码、材质、钢板厚度、减震片、包装、数量、币种、日期。

- [ ] **Step 3: 实现重新核价提示**

  只要材质、钢板厚度、包装、数量、币种或报价日期明显变化，就返回 `needs_requote=true`。

- [ ] **Step 4: 增加接口**

  `POST /api/orders/compare` 接收客户名和新订单型号列表，返回差异结构。

- [ ] **Step 5: 运行测试**

  Run:

  ```bash
  pytest tests/test_order_compare.py -v
  ```

  Expected: 新增型号、历史型号、配置差异、重新核价提示测试通过。

### Task 7: 实现本地素材库

**Files:**

- Create: `/Users/wgxxx/gitee/ai-qa/app/services/material_search.py`
- Create: `/Users/wgxxx/gitee/ai-qa/app/routers/materials.py`
- Create: `/Users/wgxxx/gitee/ai-qa/tests/test_material_search.py`

- [ ] **Step 1: 写素材登记测试**

  创建 HIQ 包装素材，字段包含文件路径、类型、产品类型、场景、品牌、描述、标签。

- [ ] **Step 2: 实现素材 CRUD**

  支持创建、列表、搜索、更新、禁用或删除素材记录。

- [ ] **Step 3: 实现场景检索**

  输入“客户想看 HIQ 包装效果”，返回品牌为 `HIQ`、场景包含 `包装` 的素材。

- [ ] **Step 4: 实现本地文件打开路径**

  API 返回本地文件路径，不复制或上传原始图片/视频。

- [ ] **Step 5: 运行测试**

  Run:

  ```bash
  pytest tests/test_material_search.py -v
  ```

  Expected: 素材登记、场景检索、标签检索测试通过。

### Task 8: 实现 AI 上下文组装和安全过滤

**Files:**

- Create: `/Users/wgxxx/gitee/ai-qa/app/services/prompt_builder.py`
- Create: `/Users/wgxxx/gitee/ai-qa/app/services/ai_provider.py`
- Create: `/Users/wgxxx/gitee/ai-qa/tests/test_prompt_builder.py`

- [ ] **Step 1: 写上下文最小化测试**

  当问题只涉及 `Ahmed D1234` 时，prompt 中只能包含 Ahmed 和 D1234 的相关记录，不能包含其他客户完整数据。

- [ ] **Step 2: 写敏感信息过滤测试**

  prompt 可以包含内部提醒，但最终 `标准回复` 不能包含报价公式、供应商成本、底价、利润空间。

- [ ] **Step 3: 实现上下文组装**

  上下文包括：

  - 当前问题
  - 相关报价/合同摘要
  - 相关素材摘要
  - 已确认话术模板
  - 安全规则

- [ ] **Step 4: 实现 AI provider adapter**

  定义统一接口：

  ```text
  generate_sales_answer(question, context) -> SalesAnswer
  ```

  本地测试默认使用 fake provider，真实 provider 后续通过环境变量启用。

- [ ] **Step 5: 运行测试**

  Run:

  ```bash
  pytest tests/test_prompt_builder.py -v
  ```

  Expected: 上下文最小化、敏感信息过滤、固定回答结构测试通过。

### Task 9: 实现中文 AI 问答接口

**Files:**

- Create: `/Users/wgxxx/gitee/ai-qa/app/routers/qa.py`
- Modify: `/Users/wgxxx/gitee/ai-qa/app/main.py`
- Modify: `/Users/wgxxx/gitee/ai-qa/tests/test_api_flows.py`

- [ ] **Step 1: 写问答接口测试**

  输入“客户问刹车片有没有噪音，怎么回复？”，期望返回：

  - `reply_thinking`
  - `standard_reply`
  - `references`
  - `recommended_materials`
  - `warnings`

- [ ] **Step 2: 实现 `POST /api/qa/ask`**

  接收 `question`，调用检索、素材推荐、话术模板、prompt builder 和 AI provider。

- [ ] **Step 3: 固定中文输出结构**

  API 返回结构化 JSON，页面再渲染为中文五段。

- [ ] **Step 4: 运行测试**

  Run:

  ```bash
  pytest tests/test_api_flows.py tests/test_prompt_builder.py -v
  ```

  Expected: 问答接口返回中文结构，且没有敏感内容。

### Task 10: 实现话术模板学习与人工确认

**Files:**

- Create: `/Users/wgxxx/gitee/ai-qa/app/services/speech_template.py`
- Create: `/Users/wgxxx/gitee/ai-qa/app/routers/templates.py`
- Create: `/Users/wgxxx/gitee/ai-qa/tests/test_speech_template.py`

- [ ] **Step 1: 写模板状态测试**

  上传聊天记录后生成 `draft` 模板，未确认时不能进入问答上下文。

- [ ] **Step 2: 实现聊天记录总结**

  fake provider 返回场景、客户问题、风格说明、标准回复、禁用词、推荐素材。

- [ ] **Step 3: 实现人工确认**

  `POST /api/templates/{id}/confirm` 将模板状态从 `draft` 改成 `confirmed`。

- [ ] **Step 4: 实现停用模板**

  `POST /api/templates/{id}/disable` 将模板状态改成 `disabled`，后续问答不引用。

- [ ] **Step 5: 运行测试**

  Run:

  ```bash
  pytest tests/test_speech_template.py tests/test_prompt_builder.py -v
  ```

  Expected: 未确认模板不生效，确认模板可进入问答上下文，停用模板不再引用。

### Task 11: 实现本地网页 UI

**Files:**

- Create: `/Users/wgxxx/gitee/ai-qa/app/routers/pages.py`
- Create: `/Users/wgxxx/gitee/ai-qa/app/templates/base.html`
- Create: `/Users/wgxxx/gitee/ai-qa/app/templates/index.html`
- Create: `/Users/wgxxx/gitee/ai-qa/app/templates/knowledge.html`
- Create: `/Users/wgxxx/gitee/ai-qa/app/templates/materials.html`
- Create: `/Users/wgxxx/gitee/ai-qa/app/templates/speech_templates.html`
- Create: `/Users/wgxxx/gitee/ai-qa/app/static/app.css`
- Create: `/Users/wgxxx/gitee/ai-qa/app/static/app.js`
- Modify: `/Users/wgxxx/gitee/ai-qa/app/main.py`

- [ ] **Step 1: 实现四个页面路由**

  - `/`：问答页
  - `/knowledge`：知识库管理页
  - `/materials`：素材管理页
  - `/speech-templates`：话术模板页

- [ ] **Step 2: 实现问答页**

  页面包含问题输入框、提交按钮、回复思路、标准回复、参考依据、推荐素材、注意事项、一键复制按钮。

- [ ] **Step 3: 实现知识库管理页**

  页面支持上传报价单 Excel、上传合同 Excel、显示导入结果。

- [ ] **Step 4: 实现素材管理页**

  页面支持新增素材、编辑描述、按场景搜索素材。

- [ ] **Step 5: 实现话术模板页**

  页面支持粘贴聊天记录、查看 AI 总结、编辑、确认、停用。

- [ ] **Step 6: 手工验证页面**

  Run:

  ```bash
  uvicorn app.main:app --reload
  ```

  Expected: 四个页面都能打开，主流程可从页面完成。

### Task 12: 导入现有谈单手册和素材目录

**Files:**

- Create: `/Users/wgxxx/gitee/ai-qa/scripts/import_raw_manual.py`
- Modify: `/Users/wgxxx/gitee/ai-qa/app/services/material_search.py`
- Create: `/Users/wgxxx/gitee/ai-qa/tests/test_raw_material_seed.py`

- [ ] **Step 1: 导入谈单手册文本**

  从 `/Users/wgxxx/gitee/ai-qa/raw/260706业务员谈单手册_v4.0.docx` 提取段落，保存为本地知识片段。

- [ ] **Step 2: 索引刹车片素材目录**

  扫描 `/Users/wgxxx/gitee/ai-qa/raw/2026.7.7刹车片/小片` 中图片和视频文件。

- [ ] **Step 3: 根据文件名生成初始标签**

  例如：

  - `A+半金属.mp4` → 材质 `A+半金属`
  - `A++陶瓷.mp4` → 材质 `A++陶瓷`
  - `普通半金属.mp4` → 材质 `普通半金属`

- [ ] **Step 4: 标记需要人工补充描述的素材**

  文件名无业务含义的素材，状态设为 `needs_description`，不自动作为高置信素材推荐。

- [ ] **Step 5: 运行测试**

  Run:

  ```bash
  pytest tests/test_raw_material_seed.py -v
  ```

  Expected: 手册段落可索引，素材文件可登记，低置信素材不会优先推荐。

### Task 13: 编写本地运行说明和样例数据

**Files:**

- Modify: `/Users/wgxxx/gitee/ai-qa/README.md`
- Create: `/Users/wgxxx/gitee/ai-qa/docs/development-local-runbook.md`
- Modify: `/Users/wgxxx/gitee/ai-qa/scripts/create_sample_excels.py`

- [ ] **Step 1: 写安装说明**

  说明 Python 版本、依赖安装、环境变量、数据库位置。

- [ ] **Step 2: 写启动说明**

  包含：

  ```bash
  uvicorn app.main:app --reload
  ```

- [ ] **Step 3: 写样例数据说明**

  说明如何生成报价单和合同样例 Excel。

- [ ] **Step 4: 写 AI 配置说明**

  `.env.example` 中只放示例变量，不提交真实密钥。

- [ ] **Step 5: 手工运行说明验证**

  从空数据库开始，按说明完成启动、导入、问答。

### Task 14: 一期验收测试

**Files:**

- Modify: `/Users/wgxxx/gitee/ai-qa/tests/test_api_flows.py`
- Modify: `/Users/wgxxx/gitee/ai-qa/docs/development-local-runbook.md`

- [ ] **Step 1: 验收用例一：常见问题回复**

  输入：

  ```text
  客户问刹车片有没有噪音，怎么回复？
  ```

  Expected: 返回中文回复思路、中文标准回复、推荐测试视频或检测报告。

- [ ] **Step 2: 验收用例二：历史价格查询**

  输入：

  ```text
  查一下 Ahmed 之前 D1234 的价格。
  ```

  Expected: 返回型号、材质、数量、单价、币种、日期；没有记录时明确说明未找到。

- [ ] **Step 3: 验收用例三：新老订单比对**

  输入：

  ```text
  Ahmed 这次要 D1234 和 D5678，帮我和上次订单比一下。
  ```

  Expected: 区分历史型号和新增型号，标出配置变化，提醒需要重新核价的项目。

- [ ] **Step 4: 验收用例四：素材推荐**

  输入：

  ```text
  客户想看 HIQ 包装效果。
  ```

  Expected: 推荐 HIQ 包装相关素材，并给出中文搭配话术。

- [ ] **Step 5: 验收用例五：话术模板确认**

  输入一段成功聊天记录。

  Expected: AI 总结模板默认 `draft`，确认后变成 `confirmed`，后续问答才能引用。

- [ ] **Step 6: 全量测试**

  Run:

  ```bash
  pytest -v
  ```

  Expected: 所有自动化测试通过。

## 5. 风险与处理

| 风险 | 处理 |
| --- | --- |
| Excel 表头不统一 | 一期只支持固定模板，导入时明确报缺失字段 |
| 历史价格被错误沿用 | 价格输出必须附带配置差异和重新核价提示 |
| AI 输出泄露内部成本 | prompt builder 和结果过滤都检查敏感词 |
| 素材文件名无意义 | 先登记为低置信素材，要求人工补描述 |
| 云端调用上传过多资料 | 检索先缩小到相关客户、型号、素材摘要 |
| 话术学习失控 | 未确认模板不进入正式问答上下文 |

## 6. PRD 覆盖检查

| PRD 要求 | 对应任务 |
| --- | --- |
| 本地网页应用 | Task 1、Task 11 |
| 中文回复思路和标准回复 | Task 8、Task 9、Task 14 |
| Excel 报价单导入 | Task 3 |
| Excel 合同导入 | Task 4 |
| 历史价格查询 | Task 5 |
| 新老订单比对 | Task 6 |
| 图片/视频素材推荐 | Task 7、Task 12 |
| 话术模板人工确认 | Task 10 |
| 不上传整个知识库 | Task 8 |
| 不泄露内部成本和报价公式 | Task 8、Task 14 |
| 一期验收用例 | Task 14 |

## 7. 推荐开发顺序

1. Task 1-2：先把工程和数据库跑起来。
2. Task 3-6：先完成结构化数据导入、查询、比对，这是业务价值核心。
3. Task 7-9：再接素材库和 AI 问答。
4. Task 10：补话术模板确认机制。
5. Task 11：最后补全网页 UI，避免前期被页面细节拖慢。
6. Task 12-14：导入真实素材、写说明、按 PRD 验收。

