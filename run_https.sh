#!/bin/bash
# ============================================================
#  HTTPS 模式启动脚本 (Git Bash / Linux / macOS)
#  使用自签名证书，适用于开发环境 / 内网部署
#
#  首次使用前请先生成证书:
#    openssl req -x509 -newkey rsa:4096 \
#      -keyout certs/key.pem -out certs/cert.pem \
#      -days 365 -nodes -config certs/openssl.cnf
#
#  浏览器访问 https://localhost:8888 时会提示不安全，
#  点击"高级" → "继续访问" 即可。
# ============================================================

echo "========================================"
echo "  启动 HTTPS 模式 (开发/内网)"
echo "  地址: https://localhost:8888"
echo "  文档: https://localhost:8888/docs"
echo "========================================"
echo ""

python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8888 \
    --ssl-keyfile=certs/key.pem \
    --ssl-certfile=certs/cert.pem
