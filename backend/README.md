# DocGen MVP（精简可跑版后端）

基于私有素材库，用大模型自动生成结构化文档。这是原 `server/` 的重写版本：
**SQLite + 进程内后台任务 + 本地文件存储**，零外部依赖即可端到端跑通；
LLM 走 OpenAI 兼容接口，**没配 key 时自动降级到本地实现**。

接口与原版完全一致，现有 `my-app/` 前端无需改动即可对接（监听 :8002）。

## 相比原版的改进

| 问题（原 `server/`） | 本版处理 |
|---|---|
| 算了 embedding 却没存，pgvector 形同虚设 | `material_chunks.embedding` 真正落库 |
| `TopicChunk.score` 恒为 1.0，排序无效 | score = chunk 向量与主题质心的**余弦相似度** |
| `unstructured` / `sklearn` 未声明依赖 | 移除重依赖，自带轻量切分 + numpy 计算 |
| `services/` 全是空壳，逻辑堆在 tasks/api | 真正落地 `services/`（parser/embedding/llm/indexer/topics/generator）分层 |
| 必须起 Postgres+Redis+MinIO+Celery+Ark | 默认 SQLite + 进程内任务 + 本地存储，开箱即跑 |
| 模型写死 R1（推理模型做摘要，错配） | 统一快模型，OpenAI 兼容、模型 ID 走配置 |

## 快速开始

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .                      # 基础依赖
# 可选：真实语义向量
# pip install -e ".[embeddings]"

uvicorn app.main:app --reload --port 8002
```

健康检查：`curl http://localhost:8002/health`
会返回当前 LLM 模式（remote / local-fallback）与向量后端（sentence-transformers / hash）。

前端：
```bash
cd ../my-app
npm install
npm run dev   # http://localhost:3000
```

## 配置

全部可选，见 [.env.example](.env.example)。要接真实模型，最少只需：

```env
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

## 工作流程

1. 注册/登录（JWT）
2. 素材库：建文件夹 → 上传 PDF/TXT/MD → 后台解析·切块·摘要·向量化 → `indexed`
3. 创建项目：选一个已就绪的素材库
4. AI 共创讨论：填主题 → 系统用「主题 + 素材库全部摘要」开场 → 多轮对话（维护上下文）
5. 形成写作方案：由讨论凝练核心观点/范围/组织思路（可编辑）
6. 结构树：由方案生成，可增删/重命名节点
7. 素材挂载：把素材片段挂到结构树节点（片段级）
8. 文章生成：逐节点按挂载片段撰写 → 拼成 Markdown → 下载

## 架构

```
app/
  core/      config / db / security / deps / storage
  models/    user / material(folder,material,chunk) / project(conversation,message,tree,document)
  schemas/   pydantic 出入参
  services/  parser  embedding  llm          ← 基础能力（含本地降级）
             indexer chat  authoring  generator  ← 入库 / 共创 / 方案·结构树 / 文章
  api/       auth / materials / projects      ← 路由
```

## 升级到生产

- **数据库**：`pip install -e ".[postgres]"`，把 `DATABASE_URL` 换成 `postgresql+asyncpg://...`
- **真实检索质量**：`pip install -e ".[embeddings]"` 启用 BGE 向量
- **任务队列**：进程内 BackgroundTask 适合 MVP；高并发时可把 `services/{indexer,topics,generator}` 的入口换接 Celery/RQ
- **对象存储**：`core/storage.py` 的 `LocalStorage` 可替换为 S3/MinIO 客户端，接口不变
