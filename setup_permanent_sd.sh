#!/bin/bash
# 文件名：setup_permanent_sd.sh
# 用途：设置SD卡作为永久存储（基础设置）

echo "=== SD卡永久存储基础设置 ==="
echo "注意：此脚本仅配置SD卡挂载和文件拷贝"
echo "Python环境配置请运行 setup_python_env.sh"
echo ""

# 获取脚本所在目录（U盘根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "U盘路径: $SCRIPT_DIR"
echo ""

# 显示U盘内容
echo "U盘内容:"
ls -lh "$SCRIPT_DIR"
echo ""

# 查找Anaconda安装包
echo "查找Anaconda安装包..."
ANACONDA_FILE=$(find "$SCRIPT_DIR" -maxdepth 1 -name "Anaconda*.sh" -o -name "anaconda*.sh" | head -1)
if [ -n "$ANACONDA_FILE" ]; then
    echo "找到: $(basename "$ANACONDA_FILE")"
else
    echo "未找到Anaconda安装包"
fi
echo ""

# 查找Python项目
echo "查找Python项目..."
PYTHON_PROJECTS=""
# 查找EIS_Online目录
if [ -d "$SCRIPT_DIR/EIS_Online" ]; then
    PYTHON_PROJECTS="$SCRIPT_DIR/EIS_Online"
    echo "找到Python项目目录: EIS_Online"
else
    echo "未找到EIS_Online目录"
fi
echo ""

# 检查SD卡并设置永久挂载
echo "=== SD卡配置 ==="

# 检查SD卡是否存在
if [ ! -b "/dev/mmcblk0p1" ]; then
    echo "错误: 未检测到SD卡 /dev/mmcblk0p1"
    echo "请插入SD卡后重试"
    exit 1
fi

echo "找到SD卡: /dev/mmcblk0p1"

# 创建永久挂载点
SD_MOUNT="/media/sd_storage"
echo "创建永久挂载点: $SD_MOUNT"
sudo mkdir -p "$SD_MOUNT"

# 检查是否已挂载
if mount | grep -q "/dev/mmcblk0p1"; then
    echo "SD卡已挂载在其他位置，尝试重新挂载..."
    CURRENT_MOUNT=$(mount | grep "/dev/mmcblk0p1" | awk '{print $3}')
    sudo umount "$CURRENT_MOUNT" 2>/dev/null
fi

# 挂载SD卡到永久位置
echo "挂载SD卡到 $SD_MOUNT ..."
sudo mount /dev/mmcblk0p1 "$SD_MOUNT"
if [ $? -ne 0 ]; then
    echo "错误: 无法挂载SD卡"
    exit 1
fi

echo "SD卡已成功挂载到: $SD_MOUNT"
echo ""

# 设置自动挂载（重启后仍然有效）
echo "配置自动挂载..."
# 获取SD卡的UUID
SD_UUID=$(sudo blkid -s UUID -o value /dev/mmcblk0p1)
if [ -n "$SD_UUID" ]; then
    echo "SD卡 UUID: $SD_UUID"
    
    # 添加到/etc/fstab
    FSTAB_ENTRY="UUID=$SD_UUID $SD_MOUNT auto defaults,nofail 0 2"
    if ! grep -q "$SD_MOUNT" /etc/fstab; then
        echo "添加自动挂载配置到 /etc/fstab"
        echo "$FSTAB_ENTRY" | sudo tee -a /etc/fstab
        echo "自动挂载配置完成，重启后SD卡会自动挂载到 $SD_MOUNT"
    else
        echo "SD卡已在 /etc/fstab 中配置了自动挂载"
    fi
else
    echo "警告: 无法获取SD卡UUID，将使用设备路径配置"
    FSTAB_ENTRY="/dev/mmcblk0p1 $SD_MOUNT auto defaults,nofail 0 2"
    if ! grep -q "$SD_MOUNT" /etc/fstab; then
        echo "$FSTAB_ENTRY" | sudo tee -a /etc/fstab
    fi
fi
echo ""

# 创建Python工作目录结构
echo "创建Python工作目录结构..."
PYTHON_WORKSPACE="$SD_MOUNT/python_workspace"
sudo mkdir -p "$PYTHON_WORKSPACE/projects"
sudo mkdir -p "$PYTHON_WORKSPACE/data"
sudo mkdir -p "$PYTHON_WORKSPACE/notebooks"
sudo mkdir -p "$PYTHON_WORKSPACE/venvs"
sudo mkdir -p "$PYTHON_WORKSPACE/scripts"

echo "Python工作空间创建在: $PYTHON_WORKSPACE"
echo ""

# 拷贝文件到SD卡
echo "=== 拷贝文件 ==="

# 1. 拷贝Anaconda安装包
if [ -n "$ANACONDA_FILE" ]; then
    echo "拷贝Anaconda安装包..."
    sudo cp "$ANACONDA_FILE" "$PYTHON_WORKSPACE/scripts/"
    echo "已拷贝: $(basename "$ANACONDA_FILE") 到 $PYTHON_WORKSPACE/scripts/"
fi

# 2. 拷贝Python项目（EIS_Online）
if [ -n "$PYTHON_PROJECTS" ] && [ -d "$PYTHON_PROJECTS" ]; then
    echo "拷贝Python项目 EIS_Online..."
    PROJECT_NAME=$(basename "$PYTHON_PROJECTS")
    sudo cp -r "$PYTHON_PROJECTS" "$PYTHON_WORKSPACE/projects/"
    echo "项目已拷贝到: $PYTHON_WORKSPACE/projects/$PROJECT_NAME"
    
    # 检查并拷贝项目依赖文件
    if [ -f "$PYTHON_PROJECTS/requirements.txt" ]; then
        echo "找到项目依赖文件 requirements.txt"
        sudo cp "$PYTHON_PROJECTS/requirements.txt" "$PYTHON_WORKSPACE/projects/$PROJECT_NAME/"
    fi
    
    # 检查并拷贝项目说明文件
    for readme in "README.md" "README.txt" "README"; do
        if [ -f "$PYTHON_PROJECTS/$readme" ]; then
            sudo cp "$PYTHON_PROJECTS/$readme" "$PYTHON_WORKSPACE/projects/$PROJECT_NAME/"
            echo "拷贝说明文件: $readme"
            break
        fi
    done
else
    echo "警告: 未找到EIS_Online项目目录"
fi

# 3. 拷贝setup_python_env.sh脚本（如果存在）
if [ -f "$SCRIPT_DIR/setup_python_env.sh" ]; then
    echo "拷贝Python环境配置脚本..."
    sudo cp "$SCRIPT_DIR/setup_python_env.sh" "$PYTHON_WORKSPACE/scripts/"
    sudo chmod +x "$PYTHON_WORKSPACE/scripts/setup_python_env.sh"
    echo "已拷贝: setup_python_env.sh"
fi

echo ""

# 安装Anaconda到SD卡（基础步骤）
if [ -n "$ANACONDA_FILE" ]; then
    ANACONDA_BASENAME=$(basename "$ANACONDA_FILE")
    ANACONDA_PATH="$PYTHON_WORKSPACE/scripts/$ANACONDA_BASENAME"
    
    echo "正在安装Anaconda到SD卡，请稍候..."
    echo "安装路径: $SD_MOUNT/anaconda3"
    
    # 检查安装包权限
    sudo chmod +x "$ANACONDA_PATH"
    
    # 安装Anaconda（静默模式）
    sudo bash "$ANACONDA_PATH" -b -p "$SD_MOUNT/anaconda3"
    
    if [ $? -eq 0 ]; then
        echo "Anaconda安装成功！"
        
        # 设置Anaconda目录权限
        echo "设置Anaconda目录权限..."
        sudo chown -R $USER:$USER "$SD_MOUNT/anaconda3"
    else
        echo "错误: Anaconda安装失败"
        exit 1
    fi
fi

echo ""

# 设置目录权限
echo "设置目录权限..."
sudo chown -R $USER:$USER "$PYTHON_WORKSPACE"
if [ -d "$SD_MOUNT/anaconda3" ]; then
    sudo chown -R $USER:$USER "$SD_MOUNT/anaconda3" 2>/dev/null
fi

echo ""

# 只设置最基础的bashrc配置（不设置快捷命令）
echo "配置基础环境变量..."
if [ -f ~/.bashrc ] && ! grep -q "SD_MOUNT" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# SD卡存储配置（由setup_permanent_sd.sh添加）" >> ~/.bashrc
    echo "export SD_MOUNT=\"/media/sd_storage\"" >> ~/.bashrc
    echo "export PYTHON_WORKSPACE=\"\$SD_MOUNT/python_workspace\"" >> ~/.bashrc
    echo "注意: Python环境快捷命令将由 setup_python_env.sh 配置" >> ~/.bashrc
fi

# 显示配置总结
echo "=== 基础配置完成 ==="
echo ""
echo "SD卡已配置为永久存储设备:"
echo "1. 挂载点: $SD_MOUNT (自动挂载已配置)"
echo "2. Python工作空间: $PYTHON_WORKSPACE"
echo "3. 目录结构:"
echo "   - projects/    # Python项目 (包含EIS_Online)"
echo "   - data/        # 数据文件"
echo "   - notebooks/   # Jupyter笔记本"
echo "   - venvs/       # 虚拟环境"
echo "   - scripts/     # 配置脚本"
echo ""

if [ -d "$SD_MOUNT/anaconda3" ]; then
    echo "Anaconda已安装: $SD_MOUNT/anaconda3"
    echo ""
    echo "下一步:"
    echo "1. 运行Python环境配置:"
    echo "   bash $PYTHON_WORKSPACE/scripts/setup_python_env.sh"
    echo ""
    echo "2. 或者手动激活基础环境:"
    echo "   source $SD_MOUNT/anaconda3/etc/profile.d/conda.sh"
    echo "   conda activate base"
else
    echo "Anaconda安装失败，请检查安装包和权限"
fi

echo ""
echo "=== 文件位置说明 ==="
echo "1. Anaconda安装包: $PYTHON_WORKSPACE/scripts/$(basename "$ANACONDA_FILE")"
echo "2. Python项目: $PYTHON_WORKSPACE/projects/EIS_Online"
echo "3. 环境配置脚本: $PYTHON_WORKSPACE/scripts/setup_python_env.sh"
echo ""
echo "注意: 请运行 'source ~/.bashrc' 或重新打开终端以使环境变量生效"
echo ""
