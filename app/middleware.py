"""
中间件：请求日志 + 全局异常捕获 → 自动写入 ErrorLog 表
"""
import traceback as tb_module
import time
import logging
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from .database import async_session
from .models import ErrorLog

# 结构化日志替代 print()
logger = logging.getLogger("rag-system")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)


def _sanitize_traceback(traceback_text: str | None, max_length: int = 2000) -> str | None:
    """脱敏处理 traceback：去除内部绝对路径，限制长度"""
    if not traceback_text:
        return None
    import re
    # 替换 Windows 和 Unix 绝对路径为占位符
    sanitized = re.sub(r'[A-Za-z]:\\[^\s",]+', '[PROJECT]\\...', traceback_text)
    sanitized = re.sub(r'/[^\s",]+/([^/\s",]+\.py)', r'[PROJECT]/.../\1', sanitized)
    return sanitized[:max_length]


async def log_request_to_error_log(
    endpoint: str,
    method: str,
    error_message: str,
    traceback_text: str | None = None,
    client_ip: str | None = None,
):
    """将错误写入 ErrorLog 表（异步，不阻塞请求响应，traceback 脱敏处理）"""
    try:
        async with async_session() as db:
            entry = ErrorLog(
                endpoint=endpoint,
                method=method,
                error_message=str(error_message)[:2000],
                traceback=_sanitize_traceback(traceback_text),
                client_ip=client_ip,
            )
            db.add(entry)
            await db.commit()
    except Exception as e:
        logger.error(f"写入错误日志失败: {e}")


async def request_middleware(request: Request, call_next):
    """记录每个请求的信息，出现异常时自动写入错误日志"""
    start = time.time()
    client_ip = request.client.host if request.client else "unknown"

    try:
        response = await call_next(request)
        elapsed = (time.time() - start) * 1000
        logger.info(
            "%s %s → %d (%.0fms) [%s]",
            request.method, request.url.path,
            response.status_code, elapsed, client_ip,
        )
        return response
    except Exception as exc:
        elapsed = (time.time() - start) * 1000
        logger.error(
            "%s %s → 500 (%.0fms) [%s] — %s",
            request.method, request.url.path,
            elapsed, client_ip, str(exc),
        )
        await log_request_to_error_log(
            endpoint=request.url.path,
            method=request.method,
            error_message=str(exc),
            traceback_text=tb_module.format_exc(),
            client_ip=client_ip,
        )
        raise


async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理：捕获路由中未处理的异常，写入 ErrorLog"""
    logger.error(
        "未处理异常 %s %s — %s",
        request.method, request.url.path, str(exc),
    )
    await log_request_to_error_log(
        endpoint=request.url.path,
        method=request.method,
        error_message=str(exc),
        traceback_text=tb_module.format_exc(),
        client_ip=request.client.host if request.client else "unknown",
    )
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"},
    )


async def security_headers_middleware(request: Request, call_next):
    """为每个响应添加安全头（企业级配置）"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Cache-Control"] = "no-store, max-age=0"
    # HSTS — 强制 HTTPS（生产环境启用，开发环境注释掉）
    # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # CSP — XSS 最后防线
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return response
