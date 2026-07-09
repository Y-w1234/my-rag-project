"""
Admin API Key 鉴权模块。
通过 X-Admin-API-Key 请求头验证管理员身份。
使用 secrets.compare_digest 防止时序侧信道攻击。
"""
import os
import secrets
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader
from dotenv import load_dotenv

load_dotenv()

_api_key_header = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)

# 缓存，避免每次请求都读环境变量
_EXPECTED_KEY: str | None = os.getenv("ADMIN_API_KEY")


def verify_admin_key(api_key: str | None = Security(_api_key_header)) -> str:
    """FastAPI 依赖：校验 Admin API Key（恒定时间比较）。不通过则返回 403。"""
    if not _EXPECTED_KEY:
        raise HTTPException(status_code=500, detail="服务端未配置 ADMIN_API_KEY")
    if not api_key or not secrets.compare_digest(api_key, _EXPECTED_KEY):
        raise HTTPException(status_code=403, detail="鉴权失败")
    return api_key
