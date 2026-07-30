#!/bin/bash
# WLB大作战 - 一键部署脚本
# 用法: 在服务器上执行 bash deploy.sh
set -e

echo "=== WLB大作战 部署脚本 ==="

# 1. Check Docker
if ! command -v docker &> /dev/null; then
    echo ">> 安装 Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo systemctl enable docker
    sudo systemctl start docker
    echo ">> Docker 安装完成"
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo ">> 安装 docker-compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# 2. Create data dirs
mkdir -p backend/data/resumes backend/logs

# 3. Check config
if [ ! -f backend/config.yaml ]; then
    echo ""
    echo "!! 缺少 backend/config.yaml 配置文件"
    echo "!! 请复制 config.yaml.example 并填入你的 API Key"
    echo ""
    exit 1
fi

# 4. Build and start
echo ">> 构建镜像..."
docker compose build

echo ">> 启动服务..."
docker compose up -d

# 5. Wait and check
sleep 3
if curl -s http://localhost:8000 > /dev/null 2>&1; then
    echo ""
    echo "=== 部署成功! ==="
    IP=$(curl -s ifconfig.me 2>/dev/null || echo "YOUR_IP")
    echo "  访问地址: http://$IP:8000"
    echo ""
    echo "  常用命令:"
    echo "    查看日志:   docker compose logs -f"
    echo "    停止服务:   docker compose down"
    echo "    重启服务:   docker compose restart"
    echo "    更新部署:   git pull && docker compose up -d --build"
    echo ""
else
    echo "!! 服务启动失败，请检查日志: docker compose logs"
fi
