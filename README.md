# 私有文档智能问答系统 (Private RAG System)

基于 **LangChain + FastAPI + ChromaDB** 的私有化文档智能问答系统（RAG, Retrieval-Augmented Generation）。上传文档后自动建立本地向量知识库，通过阿里通义千问（qwen-max）大模型实现基于文档内容的精准问答。

## 核心特性

| 特性 | 说明 |
|------|------|
| **数据安全** | 文档本地存储，不上传第三方平台 |
| **即传即问** | 上传后自动索引，无需重启 |
| **多格式支持** | .txt / .pdf / .docx |
| **增量索引** | 新文档仅追加索引，不重建全库 |
| **国内可用** | ModelScope 下载模型，通义千问 API |

## 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| Web 框架 | FastAPI | 0.104.1 |
| 服务器 | Uvicorn | 0.24.0 |
| AI 编排 | LangChain | 0.1.20 |
| 向量数据库 | ChromaDB | 0.4.24 |
| Embedding | sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2) | 2.7.0 |
| LLM | 阿里云通义千问 (qwen-max) | — |
| 文档解析 | PyPDF + python-docx | — |

## 快速启动

```bash
# 1. 克隆项目
git clone <your-repo-url>
cd my-rag-project

# 2. 创建虚拟环境
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # Mac/Linux

# 3. 安装依赖
pip install -r requirements.txt

# 4. 下载 Embedding 模型
python -c "from modelscope import snapshot_download; snapshot_download('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='./models')"

# 5. 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 DASHSCOPE_API_KEY
# 获取地址：https://bailian.console.aliyun.com/

# 6. 启动服务
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8888

# 7. 浏览器打开
# http://127.0.0.1:8888/docs
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 健康检查 |
| GET | `/docs` | Swagger 交互文档 |
| POST | `/upload/` | 上传文档并自动索引 |
| GET | `/ask/?question=...` | 智能问答 |
| POST | `/rebuild/` | 全量重建索引 |

详细说明见 [PROJECT_GUIDE.md](PROJECT_GUIDE.md)。
