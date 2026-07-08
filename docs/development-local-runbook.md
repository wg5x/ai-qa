# 本地开发运行手册

## 1. 安装

```bash
cd /Users/wgxxx/gitee/ai-qa
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 2. 环境变量

复制示例文件：

```bash
cp .env.example .env
```

常用变量：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `APP_NAME` | 应用名称 | `Local Sales AI` |
| `APP_ENV` | 运行环境 | `development` |
| `DATABASE_URL` | SQLite 连接 | `sqlite:///./data/local-sales-ai.sqlite3` |

数据库文件会自动创建在 `data/` 目录。

## 3. 启动服务

```bash
uvicorn app.main:app --reload
```

访问 http://127.0.0.1:8000/

## 4. 生成样例数据

```bash
python scripts/create_sample_excels.py
```

生成文件：

- `data/samples/quotes-sample.xlsx`
- `data/samples/contracts-sample.xlsx`

在「知识库」页面上传这两个文件即可完成基础导入。

## 5. 导入原始资料

```bash
python scripts/import_raw_manual.py
```

默认导入：

- 谈单手册：`raw/260706业务员谈单手册_v4.0.docx`
- 刹车片素材：`raw/2026.7.7刹车片/小片`

说明：

- 手册段落会保存为 `material_type=knowledge` 的知识片段
- 文件名含材质信息（如 `A+半金属.mp4`）的素材可直接推荐
- 哈希文件名或微信图片会自动标记 `needs_description`，需人工补充描述

可选参数：

```bash
python scripts/import_raw_manual.py --skip-manual
python scripts/import_raw_manual.py --skip-media
python scripts/import_raw_manual.py --manual /path/to/manual.docx --media-dir /path/to/media
```

## 6. 页面主流程

### 6.1 知识库

1. 打开 `/knowledge`
2. 上传报价单 Excel
3. 上传合同 Excel
4. 查看导入结果（成功数、失败行、重复行）

### 6.2 素材

1. 打开 `/materials`
2. 新增素材或运行导入脚本
3. 用关键词搜索，例如 `HIQ 包装`

### 6.3 话术模板

1. 打开 `/speech-templates`
2. 粘贴成功聊天记录
3. AI 生成 `draft` 模板
4. 编辑后点击「确认生效」
5. 只有 `confirmed` 模板会进入问答上下文

### 6.4 AI 问答

1. 打开 `/`
2. 输入中文问题
3. 查看五段结果：回复思路、标准回复、参考依据、推荐素材、注意事项
4. 点击「复制标准回复」

## 7. API 速查

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/health` | GET | 健康检查 |
| `/api/qa/ask` | POST | AI 问答 |
| `/api/search/prices` | GET | 历史价格查询 |
| `/api/orders/compare` | POST | 新老订单比对 |
| `/api/imports/quotes` | POST | 导入报价单 |
| `/api/imports/contracts` | POST | 导入合同 |
| `/api/materials` | GET/POST | 素材列表/新增 |
| `/api/materials/search` | GET | 素材搜索 |
| `/api/templates/summarize` | POST | 聊天记录总结 |
| `/api/templates/{id}/confirm` | POST | 确认模板 |

## 8. 测试

```bash
pytest -v
```

重点测试文件：

- `tests/test_api_flows.py`：健康检查和问答接口
- `tests/test_excel_importer.py`：Excel 导入
- `tests/test_raw_material_seed.py`：原始资料导入

## 9. AI 配置

默认使用 fake provider，不依赖外部 API。

如需接入真实 provider：

1. 在 `.env` 中配置 `SALES_AI_PROVIDER=openai`、`OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`
2. 不要提交真实密钥到 git
3. 云端 AI 只接收当前问题相关片段，不上传整个知识库

## 10. 一期验收用例

1. **常见问题回复**：`客户问刹车片有没有噪音，怎么回复？`
2. **历史价格查询**：`查一下 Ahmed 之前 D1234 的价格。`
3. **新老订单比对**：`Ahmed 这次要 D1234 和 D5678，帮我和上次订单比一下。`
4. **素材推荐**：`客户想看 HIQ 包装效果。`
5. **话术模板确认**：上传聊天记录 → draft → confirm → 问答可引用

验收前建议顺序：

```bash
pytest -v
python scripts/create_sample_excels.py
uvicorn app.main:app --reload
```

然后在网页中按上述 5 个用例手工验证。
