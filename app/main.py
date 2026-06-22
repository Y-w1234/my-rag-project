from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import shutil
import os
from . import rag_chain

UPLOAD_DIR = "./docs"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化 RAG 系统"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    try:
        rag_chain.initialize_rag()
    except Exception as e:
        print(f"警告: RAG 系统初始化失败: {e}")
        print("请确保: 1) docs/ 目录中有文档  2) 模型已下载到 models/  3) .env 中配置了 DASHSCOPE_API_KEY")
    yield


app = FastAPI(title="私有文档智能问答系统", lifespan=lifespan)


@app.get("/")
def root():
    """根路径 — 健康检查"""
    return {
        "status": "running",
        "message": "私有文档智能问答系统",
        "docs": "http://127.0.0.1:8888/docs"
    }


@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    """上传文档 — 自动索引到知识库"""
    if not file.filename.endswith(('.txt', '.pdf', '.docx')):
        raise HTTPException(status_code=400, detail="仅支持 .txt, .pdf, .docx 格式")

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 自动将新文档加入向量库，无需重启！
    try:
        chunk_count = rag_chain.add_document_to_vectorstore(file_path)
        return JSONResponse(content={
            "message": f"文件 '{file.filename}' 上传成功，已索引 {chunk_count} 个文本块，现在即可查询！",
            "chunks": chunk_count
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文档索引失败: {str(e)}")


@app.get("/ask/")
async def ask_question(question: str):
    """智能问答接口"""
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    if rag_chain.qa_chain is None:
        raise HTTPException(status_code=503, detail="RAG 系统尚未初始化，请检查服务启动日志")

    try:
        result = rag_chain.qa_chain({"query": question})
        answer = result['result']
        sources = [doc.metadata.get('source', '未知来源') for doc in result['source_documents']]

        return JSONResponse(content={
            "question": question,
            "answer": answer,
            "sources": list(set(sources))
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"问答失败: {str(e)}")


@app.post("/rebuild/")
async def rebuild_index():
    """手动重建整个向量库（从 docs/ 目录重新索引所有文档）"""
    try:
        rag_chain.rebuild_vectorstore()
        return JSONResponse(content={"message": "向量库已完全重建！"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重建失败: {str(e)}")
