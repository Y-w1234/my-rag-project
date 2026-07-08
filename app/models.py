"""
数据模型：UsageRecord（使用记录）+ ErrorLog（错误日志）
"""
import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class UsageRecord(Base):
    """用户问答使用记录"""
    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    sources = Column(Text, nullable=True)          # JSON 字符串：["doc1.pdf", "doc2.txt"]
    client_ip = Column(String(45), nullable=True)  # IPv6 最长 45 字符
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class ErrorLog(Base):
    """系统报错日志"""
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    error_message = Column(Text, nullable=False)
    traceback = Column(Text, nullable=True)         # 完整堆栈信息
    client_ip = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
