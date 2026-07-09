# 私有文档智能问答系统 — 项目开发全记录

> **适用场景**：简历项目经历 | 面试准备 | 技术复盘

---

## 一、项目概述

### 1.1 项目简介

基于 **LangChain + FastAPI + ChromaDB** 构建的私有化文档智能问答系统（RAG, Retrieval-Augmented Generation）。用户上传自有文档（TXT / PDF / DOCX），系统自动构建本地向量知识库，通过**DeepSeek**大模型实现基于文档内容的精准问答。

### 1.2 核心价值

| 维度 | 说明 |
|------|------|
| **数据安全** | 所有文档本地存储，不上传到第三方平台 |
| **即传即问** | 文档上传后自动索引，无需重启服务即可查询 |
| **多格式支持** | .txt / .pdf / .docx 三种常见文档格式 |
| **国内可用** | 针对网络环境优化，从 ModelScope 下载模型，使用 DeepSeek API |

### 1.3 技术栈

| 层级 | 技术选型 | 版本 |
|------|----------|------|
| Web 框架 | FastAPI | 0.104.1 |
| 异步服务器 | Uvicorn | 0.24.0 |
| AI 编排框架 | LangChain | 0.1.20 |
| 社区集成 | LangChain-Community | 0.0.38 |
| 向量数据库 | ChromaDB | 0.4.24 |
| 文本嵌入模型 | sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2) | 2.7.0 |
| 大语言模型 | DeepSeek (deepseek-chat) | — |
| 文档解析 | PyPDF + python-docx | 3.17.4 / 1.1.0 |
| 环境变量 | python-dotenv | 1.0.0 |
| 模型下载 | ModelScope | 1.37.1 |

---

## 二、项目架构

```
my-rag-project/
├── app/
│   ├── __init__.py          # Python 包声明
│   ├── main.py              # FastAPI 应用入口 (路由 + 生命周期)
│   └── rag_chain.py         # RAG 核心逻辑 (文档加载、向量库、问答链)
├── docs/                    # 用户上传的文档存储目录
│   ├── test.txt
│   └── new_product.txt
├── chroma_db/               # ChromaDB 向量数据库持久化目录
├── models/                  # 本地 Embedding 模型
│   └── sentence-transformers/
│       └── paraphrase-multilingual-MiniLM-L12-v2/
├── .env                     # 环境变量 (API Key 等)
├── requirements.txt         # Python 依赖清单
└── PROJECT_GUIDE.md         # 本文档
```

### 系统架构图

```
                   ┌─────────────┐
                   │   浏览器/curl │
                   └──────┬──────┘
                          │ HTTP
                   ┌──────▼──────┐
                   │   FastAPI   │
                   │  (Uvicorn)   │
                   └──┬──────┬───┘
          ┌───────────┤      └──────────┐
          ▼           ▼                 ▼
   POST /upload/  GET /ask/     POST /rebuild/
   ┌──────────┐ ┌──────────┐  ┌──────────────┐
   │文件上传+ │ │语义检索+ │  │删除旧向量库+ │
   │自动索引  │ │LLM 生成  │  │全量重建索引  │
   └────┬─────┘ └────┬─────┘  └──────┬───────┘
        │            │               │
        ▼            ▼               │
   ┌────────────────────────────────┐ │
   │       RAG Chain (LangChain)    │◄┘
   │  ┌──────────┐ ┌─────────────┐  │
   │  │ ChromaDB │ │ DeepSeek LLM │  │
   │  │ 向量存储  │ │  (deepseek-chat) │  │
   │  └──────────┘ └─────────────┘  │
   │  ┌──────────────────────────┐  │
   │  │ Sentence-Transformer     │  │
   │  │ (Embedding Model)        │  │
   │  └──────────────────────────┘  │
   └────────────────────────────────┘
```

---

## 三、API 接口说明

### 3.1 `GET /` — 健康检查

```
GET http://127.0.0.1:8888/

→ { "status": "running", "message": "私有文档智能问答系统", "docs": "..." }
```

### 3.2 `GET /docs` — Swagger 交互式文档

浏览器直接打开 `http://127.0.0.1:8888/docs` 可在线测试所有接口。

### 3.3 `POST /upload/` — 上传文档 + 自动索引

- **请求**：`multipart/form-data`，字段名 `file`
- **支持格式**：`.txt`, `.pdf`, `.docx`
- **行为**：文件保存到 `docs/` 目录，自动分块、向量化并加入知识库，**无需重启**

```
curl -F "file=@产品说明书.txt" http://127.0.0.1:8888/upload/

→ { "message": "文件 '产品说明书.txt' 上传成功，已索引 1 个文本块，现在即可查询！", "chunks": 1 }
```

### 3.4 `GET /ask/` — 智能问答

- **请求**：Query 参数 `question`
- **行为**：在向量库中检索 Top-3 相关文本块，拼接为上下文，调用 deepseek-chat 生成答案

```
curl --get --data-urlencode "question=神舟T800配置是什么？" http://127.0.0.1:8888/ask/

→ { "question": "...", "answer": "神舟T800配置为Intel i9-14900HX...", "sources": ["./docs/new_product.txt"] }
```

### 3.5 `POST /rebuild/` — 全量重建索引

删除 `chroma_db/` 并重新扫描 `docs/` 目录所有文档重建向量库。

---

## 四、核心功能实现

### 4.1 多格式文档加载器

```python
# app/rag_chain.py

def load_document(file_path):
    if file_path.endswith('.txt'):
        return TextLoader(file_path, encoding='utf-8').load()
    elif file_path.endswith('.pdf'):
        return PyPDFLoader(file_path).load()
    elif file_path.endswith('.docx'):
        return Docx2txtLoader(file_path).load()
    else:
        raise ValueError("不支持的文件格式")
```

### 4.2 文档分块策略

使用 `RecursiveCharacterTextSplitter`，**chunk_size=500** 字符，**chunk_overlap=50** 字符。这种策略兼顾语义完整性和检索精度——500 字符足够承载一个完整的语义单元，50 字符的重叠避免关键信息在分界处被截断。

### 4.3 向量化方案

选用 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` 模型：
- **多语言**：对中英文混合文档都能良好处理
- **轻量**：仅 449MB，可在 CPU 上高效推理，无需 GPU
- **语义匹配**：基于对比学习训练，擅长句子级语义相似度计算

### 4.4 增量索引（核心亮点）

**问题**：传统方案每次上传新文档都需要全量重建索引，效率极低。

**方案**：通过 ChromaDB 的 `add_documents()` 方法实现增量更新，新文档上传后**仅对新文档分块 + 向量化 + 追加**，不影响已有索引。

```python
def add_document_to_vectorstore(file_path):
    # 1. 加载新文档
    documents = load_document(file_path)
    # 2. 分块
    chunks = text_splitter.split_documents(documents)
    # 3. 追加到现有向量库（增量，非全量重建）
    vector_store.add_documents(chunks)
```

### 4.5 FastAPI Lifespan 生命周期管理

使用 `@asynccontextmanager` 在应用启动时自动初始化 RAG 系统，并在退出时清理资源。**避免了模块级别立即执行初始化代码**导致的"导入即崩溃"问题。

### 4.6 检索增强生成（RAG）问答链

```
用户问题 → Embedding 向量化 → ChromaDB 相似度检索 (Top-3)
→ 拼接上下文 Prompt → DeepSeek 生成答案 → 返回答案 + 引用来源
```

---

## 五、遇到的错误及解决方案（面试重点）

### 错误 1：langsmith 版本不存在

**现象**：
```
ERROR: Could not find a version that satisfies the requirement langsmith==0.0.98
```

**根因**：`requirements.txt` 中固定了 `langsmith==0.0.98`，该版本在 PyPI 中根本不存在（0.0.92 之后直接跳到 0.1.0）。

**解决方案**：移除 `langsmith` 的显式版本固定，由 pip 依赖解析器自动选择兼容版本。langsmith 是 langchain 的传递依赖，不需要显式声明。

---

### 错误 2：langchain 与 langchain-community 版本冲突

**现象**：
```
ERROR: Cannot install langchain==0.1.0 and langsmith==0.0.92 because...
  langchain 0.1.0 depends on langsmith<0.1.0, >=0.0.77
  langchain-community 0.0.34 depends on langsmith>=0.1.0
```

**根因**：`langchain==0.1.0` 要求 `langsmith < 0.1.0`，而 `langchain-community==0.0.34` 要求 `langsmith >= 0.1.0`，**两个约束不可调和**。

**解决方案**：同步升级两个包到互相兼容的版本：
```
langchain==0.1.20          (原 0.1.0)
langchain-community==0.0.38  (原 0.0.34)
langchain-text-splitters==0.0.2  (原 0.0.1)
```

**经验教训**：LangChain 早期版本生态的包版本耦合度高，需要查阅 PyPI 发布时间线确保版本兼容。

---

### 错误 3：sentence-transformers 在 Windows 上编译失败

**现象**：`sentence-transformers==2.2.2` 仅有 sdist 源码包，Windows 上需要 C++ 编译器构建，缺少工具链导致失败。

**根因**：sentence-transformers 早期版本未提供 Windows 的预编译 wheel。

**解决方案**：升级到 `sentence-transformers==2.7.0`，该版本提供了 cp310-win_amd64 wheel，可直接安装无需编译。

---

### 错误 4：缺少 python-multipart 依赖

**现象**：
```
RuntimeError: Form data requires "python-multipart" to be installed.
```

**根因**：FastAPI 的 `UploadFile` 依赖 `python-multipart` 解析 multipart/form-data，但 `requirements.txt` 中未声明。

**解决方案**：添加 `python-multipart==0.0.32` 到 `requirements.txt`。

**经验教训**：FastAPI 的文档中明确提示但容易被忽略——任何使用 `File()` / `UploadFile` 的接口都必须安装 `python-multipart`。

---

### 错误 5：HuggingFace.co 在国内无法访问

**现象**：
```
ConnectTimeoutError: Connection to huggingface.co timed out
OSError: We couldn't connect to 'https://huggingface.co' to load the files
```

**根因**：`sentence-transformers` 首次使用时会自动从 huggingface.co 下载模型文件，该域名在国内被墙。

**解决方案**（三步走）：

| 尝试 | 方案 | 结果 |
|------|------|------|
| 1 | 设置 `HF_ENDPOINT=https://hf-mirror.com` | ❌ 镜像站限流 429 Too Many Requests |
| 2 | ModelScope (`modelscope`) 下载模型到本地 | ✅ 成功，下载速度 7-13 MB/s |
| 3 | 代码中优先使用本地模型路径 | ✅ 永久解决，不再依赖外部网络 |

代码实现：
```python
_LOCAL_MODEL_PATH = os.path.join(_BASE_DIR, "models", "sentence-transformers",
                                  "paraphrase-multilingual-MiniLM-L12-v2")
if os.path.exists(_LOCAL_MODEL_PATH):
    MODEL_NAME = _LOCAL_MODEL_PATH       # 使用本地模型
else:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"  # 备用镜像
    MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
```

**经验教训**：在国内开发 AI 应用，**网络可达性是首要考量**——HuggingFace / OpenAI / Google 等境外服务均不可靠，需要提前准备镜像源或离线方案。

---

### 错误 6：模块导入时立即初始化导致启动崩溃

**现象**：运行 `from app.main import app` 时，即使只是导入模块也会触发 RAG 系统初始化，文档目录为空时直接抛出 `ValueError` 崩溃。

**根因**：`rag_chain.py` 在模块底部写了：

```python
# ❌ 错误的做法：模块导入时立即执行
vector_store = get_vectorstore()
qa_chain = get_qa_chain(vector_store)
```

Python 模块被 import 时，**所有顶层代码都会被执行**。

**解决方案**：将初始化逻辑包装为函数，通过 FastAPI 的 **Lifespan 事件**在应用启动时调用：

```python
# ✅ 正确的做法：延迟初始化

# rag_chain.py - 顶层只定义变量，不执行初始化
vector_store = None
qa_chain = None

def initialize_rag():
    global vector_store, qa_chain
    vector_store = get_vectorstore()
    qa_chain = get_qa_chain(vector_store)

# main.py - 在 lifespan 事件中调用
@asynccontextmanager
async def lifespan(app: FastAPI):
    rag_chain.initialize_rag()
    yield
```

---

### 错误 7：Python 模块引用的"值快照"陷阱

**现象**：RAG 系统明明初始化成功了（`vector_store: True, qa_chain: True`），但 API 接口中 `qa_chain` 始终是 `None`。

**根因**：Python 的 `from .rag_chain import qa_chain` 导入的是**变量的初始值**（`None`），后续 `initialize_rag()` 给 `rag_chain.qa_chain` 赋新值，但 `main.py` 中的局部引用 `qa_chain` 不会自动更新。

```python
# ❌ 值快照 — qa_chain 永远是 None
from .rag_chain import qa_chain

# ✅ 模块引用 — 每次读取 rag_chain.qa_chain 都取最新值
from . import rag_chain
# 使用时：rag_chain.qa_chain
```

**经验教训**：Python 中 `from module import variable` 是**引用传递**（对可变对象）或**值拷贝**（对不可变对象）。对于需要动态更新的全局状态，应使用 `import module` 并通过 `module.variable` 访问。

---

### 错误 8：上传文档后检索不到内容（根本性设计缺陷）

**现象**：用户通过 API 上传新文档，但无论重启服务多少次，提问时 **永远只检索到初始文档，新文档被完全忽略**。

**根因**：`get_vectorstore()` 的判断逻辑有缺陷：

```python
# ❌ 错误的判断
if os.path.exists(persist_dir) and os.listdir(persist_dir):
    # 只要 chroma_db/ 目录存在且有文件，就直接加载
    # 完全不管 docs/ 里有没有新文件！
    return Chroma(persist_directory=persist_dir, ...)
```

当初次启动创建了 `chroma_db/` 后，后续所有启动都走"加载已有库"分支，`docs/` 中的新文档永远不会被重新索引。

**解决方案**：两处关键修复：

1. **判断依据从"目录非空"改为"sqlite3 文件存在"**，更精确地检测数据完整性：
```python
if os.path.exists(persist_dir) and os.path.isfile(os.path.join(persist_dir, "chroma.sqlite3")):
```

2. **上传接口改为增量索引**，不再需要重启：
```python
def add_document_to_vectorstore(file_path):
    chunks = text_splitter.split_documents(load_document(file_path))
    vector_store.add_documents(chunks)  # 直接追加到现有向量库
```

---

### 错误 9：Windows 端口 8000 被占用 (WinError 10048 / 10013)

**现象**：
```
ERROR: [WinError 10048] 通常每个套接字地址(协议/网络地址/端口)只允许使用一次。
ERROR: [WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试。
```

**根因**：8000 是 Windows 上的常用端口，可能被其他程序占用；10013 通常是因为非管理员用户绑定了保留端口。

**解决方案**：使用非保留端口 8888，并通过 `netstat -ano | grep ":8888"` 检查并终止占用进程。

---

### 错误 10：NumPy 2.x 与 chromadb 0.4.24 不兼容 — RAG 初始化静默失败

**现象**：
```
POST /ask/  →  HTTP 503: "RAG 系统尚未初始化，请检查服务启动日志"
POST /upload/ → HTTP 500: "文档索引失败: 向量数据库尚未初始化，无法添加文档"
```

同时服务启动日志中可见：
```
AttributeError: `np.float_` was removed in the NumPy 2.0 release. Use `np.float64` instead.
```

**根因**：完整的错误链如下：

```
FastAPI 启动 → lifespan 事件 → initialize_rag()
  → get_vectorstore()
    → Chroma(persist_directory=..., embedding_function=...)  # 加载已有 ChromaDB
      → import chromadb
        → chromadb/api/types.py:102:
            ImageDType = Union[np.uint, np.int_, np.float_]  ← 使用了 np.float_
                                         ↑
            numpy.__init__.py → __getattr__ → AttributeError
            NumPy 2.0 正式移除了 np.float_ 等旧别名
```

版本冲突：
| 包 | 版本 | 问题 |
|---|---|---|
| numpy | 2.2.6 | 移除了 `np.float_` / `np.int_` / `np.uint` 等别名 |
| chromadb | 0.4.24 | `api/types.py` 仍在用 `np.float_` (NumPy 1.x 语法) |

由于 `initialize_rag()` 的异常被 `lifespan` 中的 `try/except` 捕获后只打印警告，不会阻止服务启动，因此：

- FastAPI 进程存活，`GET /` 返回正常
- 但 `rag_chain.vector_store` 和 `rag_chain.qa_chain` 仍为 `None`
- 所有依赖 RAG 的接口返回 "尚未初始化" 的误导性错误

**解决方案**：降级 NumPy 到 1.x 系列，维持与 chromadb 0.4.24 的兼容：

```bash
pip install "numpy<2"
# 结果: numpy 2.2.6 → 1.26.4
```

> **备选方案**：升级 chromadb 到 ≥1.0.0（已适配 NumPy 2.x），但 chromadb 0.4→1.x 跨越多个大版本，API 和持久化格式有 breaking changes，langchain_community 的 Chroma 封装也需要同步验证，风险更高。降级 numpy 是改动最小、最安全的路径。

**验证**：
```python
from app import rag_chain
vs, qa = rag_chain.initialize_rag()
# → 成功加载已有向量数据库
# → RAG 系统初始化完成！
```

**经验教训**：
1. **NumPy 2.0 是一个破坏性升级**——移除了 `np.float_`、`np.int_`、`np.bool_` 等沿用十余年的别名，大量 2024 年之前发布的库（如 chromadb ≤0.5.x）仍在使用这些别名
2. **启动时异常被静默吞掉是隐患**——`lifespan` 中的 `try/except` 打印警告后继续运行，表面看服务正常，实际上核心功能已瘫痪。应当在关键初始化失败时让服务明确报错退出，或提供 `/health` 接口暴露各组件状态
3. **版本锁定很重要**——`requirements.txt` 中应明确 `numpy<2` 约束，避免 pip 自动拉取不兼容的最新版

---

## 六、关键设计决策

| 决策 | 选项 A | 选项 B | 选择 | 理由 |
|------|--------|--------|------|------|
| 向量数据库 | FAISS | ChromaDB | **ChromaDB** | 轻量级、Python 原生、支持自动持久化 |
| 模型来源 | HuggingFace 在线 | ModelScope 离线 | **ModelScope + 本地缓存** | 国内网络不可靠，离线方案更稳定 |
| 初始化时机 | 模块导入时 | Lifespan 事件 | **Lifespan 事件** | 避免导入即崩溃，启动失败可优雅降级 |
| 索引策略 | 全量重建 | 增量更新 | **增量更新** | 用户上传后即时可查，无需等待 |
| LLM 服务 | OpenAI | DeepSeek | **DeepSeek (deepseek-chat)** | 性价比高、中文效果好、兼容 OpenAI 格式 |

---

## 七、快速启动

```bash
# 1. 进入项目目录
cd D:\Fastapi\my-rag-project

# 2. 安装依赖
pip install -r requirements.txt

# 3. 下载 Embedding 模型 (首次，如已下载可跳过)
python -c "from modelscope import snapshot_download; snapshot_download('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='./models')"

# 4. 在 docs/ 目录放置要索引的文档

# 5. 配置 API Key（编辑 .env 文件）
# DEEPSEEK_API_KEY=你的真实Key

# 6. 启动服务
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8888

# 7. 浏览器打开
# http://127.0.0.1:8888/docs
```

---

## 八、项目亮点总结（简历可用）

1. **独立设计并实现了完整的 RAG（检索增强生成）系统**，打通"文档上传 → 向量化 → 语义检索 → LLM 生成"全链路
2. **解决了 10 个工程化问题**，涵盖依赖冲突、网络不可达、Python 引用陷阱、Windows 环境适配、NumPy 版本兼容等实际场景
3. **实现了增量索引机制**，利用 ChromaDB 的 `add_documents` 实现上传即索引，避免全量重建的开销
4. **针对国内网络环境优化**，通过 ModelScope 离线缓存 Embedding 模型，解耦对 HuggingFace 的运行时依赖
5. **采用 FastAPI Lifespan 生命周期管理**，将重量级初始化从模块导入时延后到应用启动阶段，实现优雅的起停控制
6. **遵循 RESTful API 设计规范**，提供 Swagger 交互式文档，接口语义清晰、错误码规范

---

*文档最后更新：2026-06-23*
