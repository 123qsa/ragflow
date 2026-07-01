#!/bin/bash
set -e
cd "$(dirname "$0")"

# 检查 .api_key 文件
if [ ! -f .api_key ]; then
    echo "❌ 缺少 .api_key 文件，请在 RAGFlow 后台「API Keys」生成后填入"
    exit 1
fi

API_KEY=$(cat .api_key)
if [ -z "$API_KEY" ]; then
    echo "❌ .api_key 文件为空"
    exit 1
fi

# 检查 RAGFlow 是否可达
if ! curl -s -o /dev/null -w "%{http_code}" http://localhost:9380 | grep -q 200; then
    echo "⚠️  RAGFlow 后端 (localhost:9380) 不可达，请先启动 Docker"
fi

export RAGFLOW_API_KEY=$API_KEY
export RAGFLOW_BASE_URL=http://localhost:9380
export PYTHONUNBUFFERED=1

pkill -f "api_server.py" 2>/dev/null && echo "已终止旧进程"
sleep 1
nohup .venv/bin/python api_server.py > api_server.log 2>&1 &
sleep 2

# 验证启动是否成功
if curl -s http://localhost:9500/api/health | grep -q ok; then
    echo "✅ API server started (PID $!), listening on :9500"
else
    echo "❌ 启动失败，查看 api_server.log"
    exit 1
fi
