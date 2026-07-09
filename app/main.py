import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import shutil
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ── 安全常量 ─────────────────────────────────────────────────
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx"}
ALLOWED_MIMES = {
    "text/plain",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
# 魔术字节签名
MAGIC_BYTES = {
    b"%PDF": ".pdf",
    b"PK\x03\x04": ".docx",  # .docx 是 ZIP 格式
}
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from . import rag_chain
from .database import get_db, engine
from .models import Base, UsageRecord, ErrorLog, AuditLog
from .auth import verify_admin_key
from .middleware import request_middleware, global_exception_handler, security_headers_middleware

UPLOAD_DIR = "./docs"


# ── 审计日志工具函数 ──────────────────────────────────────────
async def _write_audit_log(
    db: AsyncSession,
    action: str,
    endpoint: str,
    method: str,
    client_ip: str,
    details: dict | None = None,
    result: str = "success",
):
    """写入审计日志（异步，不阻塞主流程）"""
    try:
        entry = AuditLog(
            action=action,
            endpoint=endpoint,
            method=method,
            client_ip=client_ip,
            details=json.dumps(details, ensure_ascii=False) if details else None,
            result=result,
        )
        db.add(entry)
        await db.commit()
    except Exception:  # nosec B110 — 审计日志失败不应阻断业务
        pass


# ── 数据库自动建表 ──────────────────────────────────────────
async def init_database():
    """启动时自动创建表（零配置 SQLite）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── 生命周期 ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化 RAG 系统 + 数据库"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # 初始化数据库表
    try:
        await init_database()
        print("数据库已就绪（SQLite）。")
    except Exception as e:
        print(f"警告: 数据库初始化失败: {e}")

    # 初始化 RAG 系统
    try:
        rag_chain.initialize_rag()
    except Exception as e:
        print(f"警告: RAG 系统初始化失败: {e}")
        print("请确保: 1) docs/ 目录中有文档  "
              "2) 模型已下载到 models/  3) .env 中配置了 DEEPSEEK_API_KEY")
    yield
    # ── 关闭时清理 ──
    await engine.dispose()


# ── App 实例 ────────────────────────────────────────────────
app = FastAPI(title="私有文档智能问答系统", lifespan=lifespan)

# Rate limiting — 保护公开接口（代理感知 X-Forwarded-For）
def _get_client_key(request: Request) -> str:
    """获取真实客户端标识：优先 X-Forwarded-For，回退到直连 IP"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

limiter = Limiter(key_func=_get_client_key, default_limits=["60/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — 允许前端跨域访问（最小权限原则）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# 注册中间件和全局异常处理
app.middleware("http")(security_headers_middleware)
app.middleware("http")(request_middleware)
app.add_exception_handler(Exception, global_exception_handler)


# ══════════════════════════════════════════════════════════════
# 公开接口
# ══════════════════════════════════════════════════════════════

@app.get("/")
def root():
    """根路径 — 健康检查"""
    return {"status": "ok"}


@app.get("/ask/")
@limiter.limit("10/minute")
async def ask_question(
    request: Request,
    question: str = Query(..., min_length=1, max_length=2000),
    db: AsyncSession = Depends(get_db),
):
    """智能问答接口 — 自动记录使用日志（输入校验由 Query 参数完成）"""
    if rag_chain.qa_chain is None:
        raise HTTPException(status_code=503, detail="RAG 系统尚未初始化，请检查服务启动日志")

    client_ip = request.client.host if request.client else "unknown"

    try:
        result = rag_chain.qa_chain({"query": question})
        answer = result['result']
        sources = [doc.metadata.get('source', '未知来源') for doc in result['source_documents']]
        unique_sources = list(set(sources))

        # 写入使用记录
        record = UsageRecord(
            question=question,
            answer=answer,
            sources=json.dumps(unique_sources, ensure_ascii=False),
            client_ip=client_ip,
        )
        db.add(record)
        await db.commit()

        return JSONResponse(content={
            "question": question,
            "answer": answer,
            "sources": unique_sources,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail="问答服务暂时不可用，请稍后重试")


# ══════════════════════════════════════════════════════════════
# 需鉴权的管理接口
# ══════════════════════════════════════════════════════════════

def _secure_filename(filename: str) -> str:
    """生成安全文件名：随机 UUID + 保留原始扩展名（防路径遍历 + 防特殊字符）"""
    # 1. 基础防护：只取文件名（去掉任何路径前缀）
    safe_basename = os.path.basename(filename)
    if not safe_basename or safe_basename != filename:
        raise HTTPException(status_code=400, detail="文件名包含非法字符")

    # 2. 特殊字符/编码绕过检测
    if not rag_chain._validate_filename(safe_basename):
        raise HTTPException(status_code=400, detail="文件名包含不被允许的字符")

    # 3. 扩展名白名单
    _, ext = os.path.splitext(safe_basename)
    ext = ext.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的文件格式")

    return f"{uuid.uuid4().hex}{ext}"


def _validate_magic_bytes(content: bytes, filename: str) -> bool:
    """通过魔术字节验证文件类型，不能只靠扩展名"""
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    # .txt 无固定魔术字节，跳过
    if ext == ".txt":
        return True
    for magic, expected_ext in MAGIC_BYTES.items():
        if content.startswith(magic):
            return ext == expected_ext
    return False  # 未匹配到任何已知魔术字节


@app.post("/upload/")
@limiter.limit("10/minute")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(verify_admin_key),
):
    """上传文档 — 自动索引到知识库（需 Admin Key + 安全审查）"""
    client_ip = request.client.host if request.client else "unknown"

    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    # ── 文件类型校验 ──
    _, ext = os.path.splitext(file.filename)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        await _write_audit_log(db, "upload_blocked", "/upload/", "POST",
                               client_ip, {"filename": file.filename, "reason": "extension"}, "blocked")
        raise HTTPException(status_code=400, detail="仅支持 .txt, .pdf, .docx 格式")

    # ── 读取并校验 ──
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        await _write_audit_log(db, "upload_blocked", "/upload/", "POST",
                               client_ip, {"filename": file.filename, "reason": "size"}, "blocked")
        raise HTTPException(status_code=400, detail="文件大小不能超过 10 MB")
    if not _validate_magic_bytes(content, file.filename):
        await _write_audit_log(db, "upload_blocked", "/upload/", "POST",
                               client_ip, {"filename": file.filename, "reason": "magic_bytes"}, "blocked")
        raise HTTPException(status_code=400, detail="文件类型与扩展名不匹配")
    if not file.content_type or file.content_type not in ALLOWED_MIMES:
        await _write_audit_log(db, "upload_blocked", "/upload/", "POST",
                               client_ip, {"filename": file.filename, "reason": "mime"}, "blocked")
        raise HTTPException(status_code=400, detail="不支持的文件类型")

    # ── 文件名安全化 ──
    safe_name = _secure_filename(file.filename)
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, "wb") as buffer:
        buffer.write(content)

    # ── 内容安全审查 ──
    findings = rag_chain._validate_document_content(file_path)
    if findings:
        os.remove(file_path)  # 删除不安全文件
        await _write_audit_log(db, "upload_blocked", "/upload/", "POST",
                               client_ip, {
                                   "filename": file.filename,
                                   "reason": "content_security",
                                   "findings": findings[:5],
                               }, "blocked")
        raise HTTPException(status_code=400, detail=f"文档内容审查未通过，可能包含可疑的指令性内容")

    # ── 索引到知识库 ──
    try:
        chunk_count = rag_chain.add_document_to_vectorstore(file_path)
        await _write_audit_log(db, "upload", "/upload/", "POST",
                               client_ip, {
                                   "original_filename": file.filename,
                                   "saved_filename": safe_name,
                                   "chunks": chunk_count,
                                   "size_bytes": len(content),
                               }, "success")
        return JSONResponse(content={
            "message": f"文件 '{file.filename}' 上传成功，已索引 {chunk_count} 个文本块",
            "chunks": chunk_count,
        })
    except ValueError as e:
        # 内容审查不通过
        os.remove(file_path)
        await _write_audit_log(db, "upload_blocked", "/upload/", "POST",
                               client_ip, {"filename": file.filename, "reason": str(e)}, "blocked")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await _write_audit_log(db, "upload", "/upload/", "POST",
                               client_ip, {"filename": file.filename, "error": str(e)}, "failure")
        raise HTTPException(status_code=500, detail="文档索引失败，请稍后重试")


@app.post("/rebuild/")
@limiter.limit("5/minute")
async def rebuild_index(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(verify_admin_key),
):
    """手动重建整个向量库（需 Admin Key）"""
    client_ip = request.client.host if request.client else "unknown"

    try:
        rag_chain.rebuild_vectorstore()
        await _write_audit_log(db, "rebuild", "/rebuild/", "POST",
                               client_ip, result="success")
        return JSONResponse(content={"message": "向量库已完全重建！"})
    except Exception as e:
        await _write_audit_log(db, "rebuild", "/rebuild/", "POST",
                               client_ip, {"error": str(e)}, "failure")
        raise HTTPException(status_code=500, detail="重建索引失败，请稍后重试")


# ══════════════════════════════════════════════════════════════
# Admin Dashboard API
# ══════════════════════════════════════════════════════════════

@app.get("/admin/stats")
@limiter.limit("30/minute")
async def admin_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(verify_admin_key),
):
    """Dashboard 统计数据（需 Admin Key）"""
    # 总问答数
    total_questions = (await db.execute(
        select(func.count(UsageRecord.id))
    )).scalar() or 0

    # 今日问答数
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_questions = (await db.execute(
        select(func.count(UsageRecord.id)).where(UsageRecord.created_at >= today_start)
    )).scalar() or 0

    # 总错误数
    total_errors = (await db.execute(
        select(func.count(ErrorLog.id))
    )).scalar() or 0

    # 被拦截的上传次数
    blocked_uploads = (await db.execute(
        select(func.count(AuditLog.id)).where(AuditLog.result == "blocked")
    )).scalar() or 0

    # 文档数（仅统计合法扩展名的文件）
    doc_count = len([
        f for f in os.listdir(UPLOAD_DIR)
        if os.path.isfile(os.path.join(UPLOAD_DIR, f))
        and os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS
    ]) if os.path.exists(UPLOAD_DIR) else 0

    return {
        "total_questions": total_questions,
        "today_questions": today_questions,
        "total_errors": total_errors,
        "blocked_uploads": blocked_uploads,
        "document_count": doc_count,
    }


@app.get("/admin/usage-records")
@limiter.limit("30/minute")
async def admin_usage_records(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=200),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(verify_admin_key),
):
    """分页获取使用记录（需 Admin Key）"""
    client_ip = request.client.host if request.client else "unknown"
    await _write_audit_log(db, "query_usage", "/admin/usage-records", "GET",
                           client_ip, {"page": page, "search": search[:50] if search else None})

    base_q = select(UsageRecord)
    count_q = select(func.count(UsageRecord.id))

    if search:
        search_filter = UsageRecord.question.contains(search)
        base_q = base_q.where(search_filter)
        count_q = count_q.where(search_filter)

    total = (await db.execute(count_q)).scalar() or 0

    records = (await db.execute(
        base_q
        .order_by(desc(UsageRecord.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": [
            {
                "id": r.id,
                "question": r.question,
                "answer": r.answer,
                "sources": json.loads(r.sources) if r.sources else [],
                "client_ip": r.client_ip,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
    }


@app.get("/admin/error-logs")
@limiter.limit("30/minute")
async def admin_error_logs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=200),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(verify_admin_key),
):
    """分页获取错误日志（需 Admin Key）"""
    client_ip = request.client.host if request.client else "unknown"
    await _write_audit_log(db, "query_errors", "/admin/error-logs", "GET",
                           client_ip, {"page": page, "search": search[:50] if search else None})

    base_q = select(ErrorLog)
    count_q = select(func.count(ErrorLog.id))

    if search:
        search_filter = or_(
            ErrorLog.error_message.contains(search),
            ErrorLog.endpoint.contains(search),
        )
        base_q = base_q.where(search_filter)
        count_q = count_q.where(search_filter)

    total = (await db.execute(count_q)).scalar() or 0

    logs = (await db.execute(
        base_q
        .order_by(desc(ErrorLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": [
            {
                "id": l.id,
                "endpoint": l.endpoint,
                "method": l.method,
                "error_message": l.error_message,
                "has_traceback": bool(l.traceback),
                "client_ip": l.client_ip,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }


@app.get("/admin/error-logs/{log_id}")
@limiter.limit("30/minute")
async def admin_error_log_detail(
    request: Request,
    log_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(verify_admin_key),
):
    """获取单条错误日志详情，包含完整堆栈（需 Admin Key）"""
    client_ip = request.client.host if request.client else "unknown"
    await _write_audit_log(db, "query_error_detail", f"/admin/error-logs/{log_id}", "GET",
                           client_ip, {"log_id": log_id})

    log = (await db.execute(
        select(ErrorLog).where(ErrorLog.id == log_id)
    )).scalar_one_or_none()

    if log is None:
        raise HTTPException(status_code=404, detail="错误日志不存在")

    return {
        "id": log.id,
        "endpoint": log.endpoint,
        "method": log.method,
        "error_message": log.error_message,
        "traceback": log.traceback,
        "client_ip": log.client_ip,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


# ── 审计日志查询接口 ──────────────────────────────────────────
@app.get("/admin/audit-logs")
@limiter.limit("30/minute")
async def admin_audit_logs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: str = Query("", max_length=50),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(verify_admin_key),
):
    """分页获取审计日志（需 Admin Key）"""
    base_q = select(AuditLog)
    count_q = select(func.count(AuditLog.id))

    if action:
        base_q = base_q.where(AuditLog.action == action)
        count_q = count_q.where(AuditLog.action == action)

    total = (await db.execute(count_q)).scalar() or 0

    logs = (await db.execute(
        base_q
        .order_by(desc(AuditLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": [
            {
                "id": l.id,
                "action": l.action,
                "endpoint": l.endpoint,
                "method": l.method,
                "client_ip": l.client_ip,
                "details": json.loads(l.details) if l.details else None,
                "result": l.result,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }
