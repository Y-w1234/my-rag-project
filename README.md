# 📚 私有文档智能问答系统 (Private RAG Q&A System)

> 基于 FastAPI + LangChain + ChromaDB 的私有知识库问答系统  
> 上传你的文档，用自然语言提问，DeepSeek AI 帮你找到答案。

[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688)](https://fastapi.tiangolo.com)
[![LangChain](https://img.shields.io/badge/LangChain-0.1.20-green)](https://langchain.com)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-0.4.24-FF8800)](https://trychroma.com)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## 🎯 功能

- 📄 **文档上传** — 支持 PDF、Word、TXT，自动分块向量化
- 🔍 **智能问答** — 基于 RAG 检索增强生成，返回答案 + 原文溯源
- ➕ **增量索引** — 新文档上传即索引，无需重建全库
- 🔒 **安全机制** — API Key 鉴权、速率限制、文件魔术字节 + MIME 双重校验
- 📊 **管理后台** — 使用统计、分页查询、错误日志详情
- 🐳 **本地部署** — 文档本地存储，不上传第三方平台

## 🏗️ RAG 架构

```
用户上传文档
      ↓
FastAPI → LangChain 文档加载器（PDF / Word / TXT）
      ↓
RecursiveCharacterTextSplitter 文本分块（500 字符 + 50 重叠）
      ↓
HuggingFace Embedding（paraphrase-multilingual-MiniLM-L12-v2）
      ↓
ChromaDB 向量存储（本地持久化）
      ↓
用户提问 → 向量检索（Top-3）→ 上下文拼接
      ↓
DeepSeek Chat → 答案 + 来源文档
```

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/Y-w1234/my-rag-project.git
cd my-rag-project
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 下载 Embedding 模型

```bash
python -c "from modelscope import snapshot_download; snapshot_download('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='./models')"
```

### 4. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

| 变量 | 必填 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API Key ([获取地址](https://platform.deepseek.com/api_keys)) |
| `ADMIN_API_KEY` | ✅ | 管理员密钥（管理接口鉴权用） |
| `HF_ENDPOINT` | ❌ | HuggingFace 镜像站（默认 `hf-mirror.com`） |

### 5. 启动服务

```bash
# 直接运行
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8888

# 浏览器打开 → http://127.0.0.1:8888/docs
```

访问 Swagger 交互文档，在线测试所有接口。

## 📡 API 接口

### 公开接口

| 接口 | 方法 | 说明 | 速率限制 |
|------|------|------|---------|
| `/` | GET | 健康检查 | — |
| `/ask/` | GET | 智能问答（`?question=...`） | 10 次/分钟 |

### 管理接口（需 X-Admin-API-Key 请求头）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/upload/` | POST | 上传文档，自动索引到知识库 |
| `/rebuild/` | POST | 全量重建向量库 |
| `/admin/stats` | GET | 系统统计（问答数/错误数/文档数） |
| `/admin/usage-records` | GET | 分页查询使用记录（支持关键词搜索） |
| `/admin/error-logs` | GET | 分页查询错误日志（支持关键词搜索） |
| `/admin/error-logs/{id}` | GET | 单条错误日志详情（含完整堆栈） |

## 🛡️ 安全设计

| 层级 | 措施 |
|------|------|
| **文件上传** | 扩展名白名单 + MIME 类型校验 + 魔术字节验证（防伪造） |
| **文件大小** | 10 MB 上限 |
| **接口防护** | 全局限流 60 次/分钟，问答接口 10 次/分钟 |
| **鉴权** | 管理接口 X-Admin-API-Key 请求头校验 |
| **安全头** | X-Content-Type-Options, X-Frame-Options, XSS Protection, Referrer-Policy |
| **敏感信息** | `.env` 不入库，`.env.example` 仅含占位符 |

## 🛠️ 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| Web 框架 | FastAPI | 0.104.1 |
| 服务器 | Uvicorn | 0.24.0 |
| AI 编排 | LangChain + LangChain Community | 0.1.20 |
| 向量数据库 | ChromaDB | 0.4.24 |
| Embedding | paraphrase-multilingual-MiniLM-L12-v2 | 2.7.0 |
| LLM | DeepSeek Chat（OpenAI 兼容接口） | — |
| 文档解析 | PyPDF + python-docx + docx2txt | — |
| 数据库 | SQLite + SQLAlchemy 2.0 + aiosqlite | — |
| 模型下载 | ModelScope（国内可用） | ≥1.0.0 |

## 📁 项目结构

```
my-rag-project/
├── app/
│   ├── main.py            # FastAPI 入口，全部 API 路由
│   ├── rag_chain.py       # RAG 核心：文档加载→分块→向量化→检索→生成
│   ├── auth.py            # Admin API Key 鉴权
│   ├── database.py        # SQLite 异步引擎 + 会话管理
│   ├── models.py          # UsageRecord + ErrorLog 数据模型
│   └── middleware.py       # 请求日志 + 全局异常捕获 + 安全头
├── docs/                  # 示例文档（RAG 知识库的数据源）
├── requirements.txt
├── .env.example           # 环境变量模板（无真实 Key）
└── README.md
```

## 📝 License

MIT
