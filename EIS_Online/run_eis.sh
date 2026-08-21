#!/bin/bash
# EIS项目运行脚本

echo "========================================"
echo "启动 EIS Online 项目"
echo "========================================"
echo ""

# 自动检测存储设备
if [ -d "/media/ssd_storage/anaconda3" ]; then
    STORAGE_MOUNT="/media/ssd_storage"
    echo "使用SSD存储"
elif [ -d "/media/sd_storage/anaconda3" ]; then
    STORAGE_MOUNT="/media/sd_storage"
    echo "使用SD卡存储"
else
    echo "错误: 未找到存储设备"
    exit 1
fi

ANACONDA_PATH="$STORAGE_MOUNT/anaconda3"
PROJECT_DIR="$STORAGE_MOUNT/python_workspace/projects/EIS_Online"
ENTRY_FILE="can_tester.py"

echo "存储路径: $STORAGE_MOUNT"
echo "项目目录: $PROJECT_DIR"
echo "入口文件: $ENTRY_FILE"
echo ""

# 检查环境
if [ ! -d "$ANACONDA_PATH/envs/eis_env" ]; then
    echo "错误: 虚拟环境 eis_env 不存在"
    echo "请先运行: bash $STORAGE_MOUNT/python_workspace/scripts/setup_python_env.sh"
    exit 1
fi

# 初始化conda
if [ -f "$ANACONDA_PATH/etc/profile.d/conda.sh" ]; then
    source "$ANACONDA_PATH/etc/profile.d/conda.sh"
else
    eval "$($ANACONDA_PATH/bin/conda shell.bash hook)"
fi

# 激活环境
conda activate eis_env

if [ $? -ne 0 ]; then
    echo "错误: 无法激活 eis_env 环境"
    exit 1
fi

echo "✓ 环境激活成功"
echo "Python版本: $(python --version)"
echo ""

# 进入项目目录
cd "$PROJECT_DIR"
echo "当前目录: $(pwd)"

# 检查入口文件
if [ ! -f "$ENTRY_FILE" ]; then
    echo "错误: 未找到入口文件 $ENTRY_FILE"
    echo "目录内容:"
    ls -la
    exit 1
fi

echo "✓ 找到入口文件: $ENTRY_FILE"
echo ""

# 运行项目
echo "========================================"
echo "开始运行 EIS Online 项目"
echo "========================================"
echo ""

python "$ENTRY_FILE"

RUN_STATUS=$?

echo ""
echo "========================================"
echo "运行完成"
echo "========================================"
echo ""

if [ $RUN_STATUS -eq 0 ]; then
    echo "✓ 项目正常退出 (退出代码: 0)"
else
    echo "⚠ 项目异常退出 (退出代码: $RUN_STATUS)"
    echo ""
    echo "可能的原因:"
    echo "  1. CAN设备未连接或未正确配置"
    echo "  2. 缺少必要的硬件或驱动"
    echo "  3. 程序遇到错误"
    echo ""
    echo "建议:"
    echo "  1. 检查CAN设备连接"
    echo "  2. 检查系统CAN驱动"
    echo "  3. 查看程序日志获取详细信息"
fi

exit $RUN_STATUS
