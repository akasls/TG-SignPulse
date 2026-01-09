#!/bin/bash

# tg-signer 本地测试脚本
# 用于快速构建和运行 Docker 容器进行本地测试

set -e

echo "========================================="
echo "tg-signer 本地测试脚本"
echo "========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 配置
IMAGE_NAME="tg-signer-test"
CONTAINER_NAME="tg-signer-test-container"
PORT=8080
DATA_DIR="./data"

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker 未安装${NC}"
    exit 1
fi

# 清理旧容器
echo -e "${YELLOW}1. 清理旧容器...${NC}"
docker stop $CONTAINER_NAME 2>/dev/null || true
docker rm $CONTAINER_NAME 2>/dev/null || true
echo -e "${GREEN}✓ 清理完成${NC}"
echo ""

# 构建镜像
echo -e "${YELLOW}2. 构建 Docker 镜像...${NC}"
docker build -t $IMAGE_NAME .
echo -e "${GREEN}✓ 构建完成${NC}"
echo ""

# 创建数据目录
echo -e "${YELLOW}3. 创建数据目录...${NC}"
mkdir -p $DATA_DIR
echo -e "${GREEN}✓ 数据目录已创建: $DATA_DIR${NC}"
echo ""

# 运行容器
echo -e "${YELLOW}4. 启动容器...${NC}"
docker run -d \
  --name $CONTAINER_NAME \
  -p $PORT:8080 \
  -e APP_SECRET_KEY=test-secret-key-for-local-development \
  -v "$(pwd)/$DATA_DIR:/data" \
  $IMAGE_NAME

echo -e "${GREEN}✓ 容器已启动${NC}"
echo ""

# 等待容器启动
echo -e "${YELLOW}5. 等待应用启动...${NC}"
sleep 5

# 检查容器状态
if docker ps | grep -q $CONTAINER_NAME; then
    echo -e "${GREEN}✓ 容器运行正常${NC}"
else
    echo -e "${RED}✗ 容器启动失败${NC}"
    echo ""
    echo "查看日志:"
    docker logs $CONTAINER_NAME
    exit 1
fi
echo ""

# 显示日志
echo -e "${YELLOW}6. 容器日志 (最近 20 行):${NC}"
docker logs --tail 20 $CONTAINER_NAME
echo ""

# 测试健康检查
echo -e "${YELLOW}7. 测试健康检查...${NC}"
sleep 3
if curl -s http://localhost:$PORT/health | grep -q "ok"; then
    echo -e "${GREEN}✓ 健康检查通过${NC}"
else
    echo -e "${RED}✗ 健康检查失败${NC}"
fi
echo ""

# 显示访问信息
echo "========================================="
echo -e "${GREEN}应用已成功启动！${NC}"
echo "========================================="
echo ""
echo "访问信息:"
echo "  - 前端: http://localhost:$PORT"
echo "  - API:  http://localhost:$PORT/api"
echo "  - 健康检查: http://localhost:$PORT/health"
echo ""
echo "默认登录信息:"
echo "  - 用户名: admin"
echo "  - 密码: admin123"
echo ""
echo "有用的命令:"
echo "  - 查看日志: docker logs -f $CONTAINER_NAME"
echo "  - 停止容器: docker stop $CONTAINER_NAME"
echo "  - 删除容器: docker rm $CONTAINER_NAME"
echo "  - 进入容器: docker exec -it $CONTAINER_NAME /bin/bash"
echo "  - 运行测试: python test_api.py"
echo ""
echo "数据目录: $DATA_DIR"
echo ""

# 询问是否运行测试
read -p "是否运行 API 测试? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo -e "${YELLOW}运行 API 测试...${NC}"
    python test_api.py
fi

echo ""
echo -e "${GREEN}完成！${NC}"
