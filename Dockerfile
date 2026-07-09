# ── Stage 1: 下载 Embedding 模型 ──────────────────────────
FROM python:3.10-slim AS model-downloader
RUN pip install --no-cache-dir modelscope
RUN python -c "from modelscope import snapshot_download; snapshot_download('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='/models')"

# ── Stage 2: 生产镜像 ──────────────────────────────────────
FROM python:3.10-slim

LABEL org.opencontainers.image.title="my-rag-project"
LABEL org.opencontainers.image.description="私有文档智能问答系统 (RAG)"

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制模型 (从 stage 1)
COPY --from=model-downloader /models /app/models

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p /app/docs /app/chroma_db /app/data

# 非 root 用户运行
RUN useradd -m -u 1000 app && chown -R app:app /app
USER app

# 暴露端口
EXPOSE 8888

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8888/')" || exit 1

# 启动
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8888"]
