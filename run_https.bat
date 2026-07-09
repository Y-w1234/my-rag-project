@echo off
REM ============================================================
REM  HTTPS 模式启动脚本 (Windows)
REM  使用自签名证书，适用于开发环境 / 内网部署
REM
REM  首次使用前请先生成证书:
REM    openssl req -x509 -newkey rsa:4096 ^
REM      -keyout certs/key.pem -out certs/cert.pem ^
REM      -days 365 -nodes -config certs/openssl.cnf
REM
REM  浏览器访问 https://localhost:8888 时会提示不安全，
REM  点击"高级" → "继续访问" 即可。
REM ============================================================

echo ========================================
echo   启动 HTTPS 模式 (开发/内网)
echo   地址: https://localhost:8888
echo   文档: https://localhost:8888/docs
echo ========================================
echo.

python -m uvicorn app.main:app ^
    --host 0.0.0.0 ^
    --port 8888 ^
    --ssl-keyfile=certs/key.pem ^
    --ssl-certfile=certs/cert.pem

pause
