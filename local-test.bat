@echo off
REM tg-signer 本地测试脚本 (Windows 版本)
REM 用于快速构建和运行 Docker 容器进行本地测试

setlocal enabledelayedexpansion

echo =========================================
echo tg-signer 本地测试脚本 (Windows)
echo =========================================
echo.

REM 配置
set IMAGE_NAME=tg-signer-test
set CONTAINER_NAME=tg-signer-test-container
set PORT=8080
set DATA_DIR=.\data

REM 检查 Docker 是否安装
docker --version >nul 2>&1
if errorlevel 1 (
    echo 错误: Docker 未安装
    exit /b 1
)

REM 清理旧容器
echo 1. 清理旧容器...
docker stop %CONTAINER_NAME% >nul 2>&1
docker rm %CONTAINER_NAME% >nul 2>&1
echo [OK] 清理完成
echo.

REM 构建镜像
echo 2. 构建 Docker 镜像...
docker build -t %IMAGE_NAME% .
if errorlevel 1 (
    echo [ERROR] 构建失败
    exit /b 1
)
echo [OK] 构建完成
echo.

REM 创建数据目录
echo 3. 创建数据目录...
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
echo [OK] 数据目录已创建: %DATA_DIR%
echo.

REM 运行容器
echo 4. 启动容器...
docker run -d ^
  --name %CONTAINER_NAME% ^
  -p %PORT%:8080 ^
  -e APP_SECRET_KEY=test-secret-key-for-local-development ^
  -v "%cd%\%DATA_DIR%:/data" ^
  %IMAGE_NAME%

if errorlevel 1 (
    echo [ERROR] 容器启动失败
    exit /b 1
)
echo [OK] 容器已启动
echo.

REM 等待容器启动
echo 5. 等待应用启动...
timeout /t 5 /nobreak >nul

REM 检查容器状态
docker ps | findstr %CONTAINER_NAME% >nul
if errorlevel 1 (
    echo [ERROR] 容器启动失败
    echo.
    echo 查看日志:
    docker logs %CONTAINER_NAME%
    exit /b 1
)
echo [OK] 容器运行正常
echo.

REM 显示日志
echo 6. 容器日志 (最近 20 行):
docker logs --tail 20 %CONTAINER_NAME%
echo.

REM 测试健康检查
echo 7. 测试健康检查...
timeout /t 3 /nobreak >nul
curl -s http://localhost:%PORT%/health | findstr "ok" >nul
if errorlevel 1 (
    echo [WARNING] 健康检查失败
) else (
    echo [OK] 健康检查通过
)
echo.

REM 显示访问信息
echo =========================================
echo 应用已成功启动！
echo =========================================
echo.
echo 访问信息:
echo   - 前端: http://localhost:%PORT%
echo   - API:  http://localhost:%PORT%/api
echo   - 健康检查: http://localhost:%PORT%/health
echo.
echo 默认登录信息:
echo   - 用户名: admin
echo   - 密码: admin123
echo.
echo 有用的命令:
echo   - 查看日志: docker logs -f %CONTAINER_NAME%
echo   - 停止容器: docker stop %CONTAINER_NAME%
echo   - 删除容器: docker rm %CONTAINER_NAME%
echo   - 进入容器: docker exec -it %CONTAINER_NAME% /bin/bash
echo   - 运行测试: python test_api.py
echo.
echo 数据目录: %DATA_DIR%
echo.

REM 询问是否运行测试
set /p RUN_TEST="是否运行 API 测试? (y/N): "
if /i "%RUN_TEST%"=="y" (
    echo.
    echo 运行 API 测试...
    python test_api.py
)

echo.
echo 完成！
pause
