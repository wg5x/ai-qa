# 本地销售 AI 助手

单机本地网页应用，帮助外贸业务员导入 Excel 报价/合同、本地素材和优秀话术，并通过中文 AI 问答获得回复思路、标准回复、历史报价比对和素材推荐。

## 环境要求

- Python 3.11+
- macOS / Windows / Linux 本地运行

## 快速开始

```bash
# 1. 安装依赖
pip install -e .

# 2. 复制环境变量示例（可选）
cp .env.example .env

# 3. 生成样例 Excel
python scripts/create_sample_excels.py

# 4. 启动服务
uvicorn app.main:app --reload
```

浏览器打开：

- 问答页：http://127.0.0.1:8000/
- 知识库：http://127.0.0.1:8000/knowledge
- 素材管理：http://127.0.0.1:8000/materials
- 话术模板：http://127.0.0.1:8000/speech-templates

健康检查：http://127.0.0.1:8000/health

## 主要功能

1. **AI 问答**：输入客户问题，获取回复思路、标准回复、参考依据和推荐素材
2. **知识库导入**：上传固定模板 Excel 导入报价单和合同
3. **素材管理**：登记本地图片/视频/报告，按场景搜索
4. **话术模板**：粘贴聊天记录，AI 总结为模板，人工确认后生效

## 导入原始资料

```bash
# 导入谈单手册和 raw/ 目录下的刹车片素材
python scripts/import_raw_manual.py
```

## 运行测试

```bash
pytest -v
```

## 文档

- [PRD](docs/prd-local-sales-ai.md)
- [本地开发运行手册](docs/development-local-runbook.md)
- [实现计划](docs/superpowers/plans/2026-07-07-local-sales-ai-mvp.md)

## 数据位置

- SQLite 数据库：`data/local-sales-ai.sqlite3`
- 样例 Excel：`data/samples/`
- 原始资料：`raw/`

## AI 配置

默认使用内置 fake provider，适合本地开发和测试。启用真实 AI 时，在 `.env` 中配置 provider 相关变量（不要提交真实密钥）。
