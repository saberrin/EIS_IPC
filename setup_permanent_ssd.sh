#!/bin/bash
# 文件名：setup_permanent_ssd.sh
# 用途：设置SSD作为永久存储（基础设置）

echo "=== SSD永久存储基础设置 ==="
echo "注意：此脚本仅配置SSD挂载和文件拷贝"
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

# 检查SSD并设置永久挂载
echo "=== SSD配置 ==="

# 检测SSD设备
echo "检测存储设备..."
lsblk

# 让用户选择SSD设备，自动添加分区号
echo ""
echo "请根据上面的设备列表选择SSD设备:"
echo "注意: 请选择分区（如 /dev/sda1），而不是整个磁盘（如 /dev/sda）"
echo "如果SSD没有分区，脚本将帮您创建分区"

read -p "请输入SSD设备路径: " USER_DEVICE

# 规范化设备路径
if [[ "$USER_DEVICE" =~ ^/dev/sd[a-z]$ ]] || [[ "$USER_DEVICE" =~ ^/dev/nvme[0-9]+n[0-9]+$ ]]; then
    # 用户输入了整个磁盘，而不是分区
    echo "检测到您输入了整个磁盘: $USER_DEVICE"
    echo "正在查找分区..."
    
    # 查找该磁盘的第一个分区
    PARTITION=$(lsblk -ln -o NAME "$USER_DEVICE" | grep -E "${USER_DEVICE#/dev/}[0-9]+" | head -1)
    
    if [ -n "$PARTITION" ]; then
        SSD_DEVICE="/dev/$PARTITION"
        echo "找到分区: $SSD_DEVICE"
    else
        echo "未找到分区，SSD可能需要创建分区"
        echo "正在创建分区..."
        
        # 创建GPT分区表和单个分区
        echo "为 $USER_DEVICE 创建GPT分区表和单个分区..."
        
        read -p "这将擦除 $USER_DEVICE 上的所有数据！是否继续? (输入YES确认): " CONFIRM
        if [ "$CONFIRM" != "YES" ]; then
            echo "操作取消"
            exit 1
        fi
        
        # 创建GPT分区表
        echo "创建GPT分区表..."
        sudo parted "$USER_DEVICE" mklabel gpt
        
        # 创建单个分区占用全部空间
        echo "创建分区..."
        sudo parted "$USER_DEVICE" mkpart primary ext4 0% 100%
        
        # 等待内核识别新分区
        sleep 2
        
        # 查找新创建的分区
        PARTITION=$(lsblk -ln -o NAME "$USER_DEVICE" | grep -E "${USER_DEVICE#/dev/}[0-9]+" | head -1)
        
        if [ -n "$PARTITION" ]; then
            SSD_DEVICE="/dev/$PARTITION"
            echo "已创建分区: $SSD_DEVICE"
            
            # 格式化分区为ext4
            echo "格式化分区为ext4..."
            sudo mkfs.ext4 -F "$SSD_DEVICE"
        else
            echo "错误: 无法创建分区"
            exit 1
        fi
    fi
elif [[ "$USER_DEVICE" =~ ^/dev/sd[a-z][0-9]+$ ]] || [[ "$USER_DEVICE" =~ ^/dev/nvme[0-9]+n[0-9]+p[0-9]+$ ]]; then
    # 用户输入了分区
    SSD_DEVICE="$USER_DEVICE"
    echo "使用分区: $SSD_DEVICE"
else
    echo "错误: 无效的设备路径: $USER_DEVICE"
    echo "正确的格式: /dev/sda1, /dev/sdb1, /dev/nvme0n1p1"
    exit 1
fi

# 验证设备存在
if [ ! -b "$SSD_DEVICE" ]; then
    echo "错误: 设备 $SSD_DEVICE 不存在"
    exit 1
fi

echo "最终使用SSD设备: $SSD_DEVICE"

# 创建永久挂载点
SSD_MOUNT="/media/ssd_storage"
echo "创建永久挂载点: $SSD_MOUNT"
sudo mkdir -p "$SSD_MOUNT"

# 检查是否已挂载
if mount | grep -q "$SSD_DEVICE"; then
    echo "SSD已挂载在其他位置，尝试重新挂载..."
    CURRENT_MOUNT=$(mount | grep "$SSD_DEVICE" | awk '{print $3}')
    sudo umount "$CURRENT_MOUNT" 2>/dev/null
fi

# 挂载SSD到永久位置
echo "挂载SSD到 $SSD_MOUNT ..."
sudo mount "$SSD_DEVICE" "$SSD_MOUNT"
if [ $? -ne 0 ]; then
    echo "挂载失败，检查文件系统..."
    
    # 检查文件系统类型
    FS_TYPE=$(sudo blkid -s TYPE -o value "$SSD_DEVICE" 2>/dev/null)
    
    if [ -z "$FS_TYPE" ]; then
        echo "设备没有有效的文件系统"
        read -p "是否格式化为ext4文件系统? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "警告: 这将擦除 $SSD_DEVICE 上的所有数据!"
            read -p "确认格式化 $SSD_DEVICE? (输入YES确认): " CONFIRM
            if [ "$CONFIRM" = "YES" ]; then
                echo "正在格式化 $SSD_DEVICE 为ext4..."
                sudo mkfs.ext4 -F "$SSD_DEVICE"
                echo "格式化完成，重新挂载..."
                sudo mount "$SSD_DEVICE" "$SSD_MOUNT"
                if [ $? -ne 0 ]; then
                    echo "错误: 挂载仍然失败"
                    exit 1
                fi
            else
                echo "取消格式化，退出脚本"
                exit 1
            fi
        else
            echo "请手动格式化SSD后重试"
            exit 1
        fi
    else
        echo "设备有 $FS_TYPE 文件系统，但无法挂载"
        echo "可能需要修复文件系统"
        read -p "是否尝试修复文件系统? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            case "$FS_TYPE" in
                "ext4"|"ext3"|"ext2")
                    echo "修复ext文件系统..."
                    sudo fsck -y "$SSD_DEVICE"
                    ;;
                "ntfs")
                    echo "修复NTFS文件系统..."
                    sudo ntfsfix "$SSD_DEVICE"
                    ;;
                "vfat"|"fat32")
                    echo "修复FAT文件系统..."
                    sudo fsck.vfat -y "$SSD_DEVICE"
                    ;;
                *)
                    echo "不支持的文件系统: $FS_TYPE"
                    exit 1
                    ;;
            esac
            
            echo "重新尝试挂载..."
            sudo mount "$SSD_DEVICE" "$SSD_MOUNT"
            if [ $? -ne 0 ]; then
                echo "错误: 挂载仍然失败"
                exit 1
            fi
        else
            echo "请手动修复文件系统后重试"
            exit 1
        fi
    fi
fi

echo "SSD已成功挂载到: $SSD_MOUNT"
echo ""

# 检查文件系统信息
echo "文件系统信息:"
df -h "$SSD_MOUNT"
echo ""

# 设置自动挂载（重启后仍然有效）
echo "配置自动挂载..."
# 获取SSD的UUID
SSD_UUID=$(sudo blkid -s UUID -o value "$SSD_DEVICE")
if [ -n "$SSD_UUID" ]; then
    echo "SSD UUID: $SSD_UUID"
    
    # 获取文件系统类型
    FS_TYPE=$(sudo blkid -s TYPE -o value "$SSD_DEVICE")
    FS_TYPE=${FS_TYPE:-auto}
    
    # 添加到/etc/fstab
    FSTAB_ENTRY="UUID=$SSD_UUID $SSD_MOUNT $FS_TYPE defaults,nofail 0 2"
    if ! grep -q "$SSD_MOUNT" /etc/fstab; then
        echo "添加自动挂载配置到 /etc/fstab"
        echo "$FSTAB_ENTRY" | sudo tee -a /etc/fstab
        echo "自动挂载配置完成，重启后SSD会自动挂载到 $SSD_MOUNT"
    else
        echo "SSD已在 /etc/fstab 中配置了自动挂载"
    fi
else
    echo "警告: 无法获取SSD UUID，将使用设备路径配置"
    
    # 获取文件系统类型
    FS_TYPE=$(sudo blkid -s TYPE -o value "$SSD_DEVICE")
    FS_TYPE=${FS_TYPE:-auto}
    
    FSTAB_ENTRY="$SSD_DEVICE $SSD_MOUNT $FS_TYPE defaults,nofail 0 2"
    if ! grep -q "$SSD_MOUNT" /etc/fstab; then
        echo "$FSTAB_ENTRY" | sudo tee -a /etc/fstab
    fi
fi
echo ""

# 创建Python工作目录结构
echo "创建Python工作目录结构..."
PYTHON_WORKSPACE="$SSD_MOUNT/python_workspace"
sudo mkdir -p "$PYTHON_WORKSPACE/projects"
sudo mkdir -p "$PYTHON_WORKSPACE/data"
sudo mkdir -p "$PYTHON_WORKSPACE/notebooks"
sudo mkdir -p "$PYTHON_WORKSPACE/venvs"
sudo mkdir -p "$PYTHON_WORKSPACE/scripts"

echo "Python工作空间创建在: $PYTHON_WORKSPACE"
echo ""

# 拷贝文件到SSD
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

# ============================================
# 设置文件权限 - 关键部分
# ============================================

echo "=== 设置文件权限 ==="

# 设置SSD根目录权限
echo "设置SSD根目录权限..."
sudo chmod 755 "$SSD_MOUNT"

# 设置Python工作空间权限
echo "设置Python工作空间权限..."
sudo chmod -R 755 "$PYTHON_WORKSPACE"

# 设置脚本文件可执行权限
echo "设置脚本文件可执行权限..."
if [ -f "$PYTHON_WORKSPACE/scripts/setup_python_env.sh" ]; then
    sudo chmod +x "$PYTHON_WORKSPACE/scripts/setup_python_env.sh"
fi

# 设置Python项目文件权限
if [ -d "$PYTHON_WORKSPACE/projects/EIS_Online" ]; then
    echo "设置EIS_Online项目文件权限..."
    
    # Python文件设置为可读可写可执行（对所有者）
    find "$PYTHON_WORKSPACE/projects/EIS_Online" -name "*.py" -type f -exec sudo chmod 755 {} \;
    
    # 其他文本文件设置为可读可写
    find "$PYTHON_WORKSPACE/projects/EIS_Online" -name "*.txt" -o -name "*.md" -o -name "*.cfg" -o -name "*.ini" -type f -exec sudo chmod 644 {} \;
    
    # 如果有shell脚本，设置为可执行
    find "$PYTHON_WORKSPACE/projects/EIS_Online" -name "*.sh" -type f -exec sudo chmod +x {} \;
    
    # 数据库文件设置为可读可写
    find "$PYTHON_WORKSPACE/projects/EIS_Online" -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" -type f -exec sudo chmod 666 {} \;
    
    # 日志文件设置为可读可写
    find "$PYTHON_WORKSPACE/projects/EIS_Online" -name "*.log" -type f -exec sudo chmod 666 {} \;
    
    echo "项目文件权限设置完成"
fi

echo ""

# 设置所有权（让当前用户可以读写所有文件）
echo "设置文件所有权..."
sudo chown -R $USER:$USER "$SSD_MOUNT"

echo "所有权和权限设置完成"
echo ""

# 验证权限设置
echo "=== 验证权限设置 ==="
echo "SSD挂载点权限:"
ls -ld "$SSD_MOUNT"
echo ""
echo "Python工作空间权限:"
ls -ld "$PYTHON_WORKSPACE"
echo ""
echo "EIS_Online项目权限示例:"
if [ -d "$PYTHON_WORKSPACE/projects/EIS_Online" ]; then
    find "$PYTHON_WORKSPACE/projects/EIS_Online" -maxdepth 1 -type f | head -5 | xargs ls -l 2>/dev/null || true
fi

echo ""

# 安装Anaconda到SSD（基础步骤）
if [ -n "$ANACONDA_FILE" ]; then
    ANACONDA_BASENAME=$(basename "$ANACONDA_FILE")
    ANACONDA_PATH="$PYTHON_WORKSPACE/scripts/$ANACONDA_BASENAME"
    
    echo "正在安装Anaconda到SSD，请稍候..."
    echo "安装路径: $SSD_MOUNT/anaconda3"
    
    # 检查安装包权限
    sudo chmod +x "$ANACONDA_PATH"
    
    # 安装Anaconda（静默模式）
    sudo bash "$ANACONDA_PATH" -b -p "$SSD_MOUNT/anaconda3"
    
    if [ $? -eq 0 ]; then
        echo "Anaconda安装成功！"
        
        # 设置Anaconda目录权限
        echo "设置Anaconda目录权限..."
        sudo chown -R $USER:$USER "$SSD_MOUNT/anaconda3"
    else
        echo "错误: Anaconda安装失败"
        exit 1
    fi
fi

echo ""

# 设置目录权限
echo "设置目录权限..."
sudo chown -R $USER:$USER "$PYTHON_WORKSPACE"
if [ -d "$SSD_MOUNT/anaconda3" ]; then
    sudo chown -R $USER:$USER "$SSD_MOUNT/anaconda3" 2>/dev/null
fi

echo ""

# 只设置最基础的bashrc配置（不设置快捷命令）
echo "配置基础环境变量..."
if [ -f ~/.bashrc ] && ! grep -q "SSD_MOUNT" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# SSD存储配置（由setup_permanent_ssd.sh添加）" >> ~/.bashrc
    echo "export SSD_MOUNT=\"$SSD_MOUNT\"" >> ~/.bashrc
    echo "export PYTHON_WORKSPACE=\"\$SSD_MOUNT/python_workspace\"" >> ~/.bashrc
    echo "注意: Python环境快捷命令将由 setup_python_env.sh 配置" >> ~/.bashrc
fi

# 显示配置总结
echo "=== 基础配置完成 ==="
echo ""
echo "SSD已配置为永久存储设备:"
echo "1. 挂载点: $SSD_MOUNT (自动挂载已配置)"
echo "2. Python工作空间: $PYTHON_WORKSPACE"
echo "3. 目录结构:"
echo "   - projects/    # Python项目 (包含EIS_Online)"
echo "   - data/        # 数据文件"
echo "   - notebooks/   # Jupyter笔记本"
echo "   - venvs/       # 虚拟环境"
echo "   - scripts/     # 配置脚本"
echo ""

if [ -d "$SSD_MOUNT/anaconda3" ]; then
    echo "Anaconda已安装: $SSD_MOUNT/anaconda3"
    echo ""
    echo "下一步:"
    echo "1. 运行Python环境配置:"
    echo "   bash $PYTHON_WORKSPACE/scripts/setup_python_env.sh"
    echo ""
    echo "2. 或者手动激活基础环境:"
    echo "   source $SSD_MOUNT/anaconda3/etc/profile.d/conda.sh"
    echo "   conda activate base"
else
    echo "Anaconda安装失败，请检查安装包和权限"
fi

echo ""
echo "=== 文件位置说明 ==="
if [ -n "$ANACONDA_FILE" ]; then
    echo "1. Anaconda安装包: $PYTHON_WORKSPACE/scripts/$(basename "$ANACONDA_FILE")"
fi
echo "2. Python项目: $PYTHON_WORKSPACE/projects/EIS_Online"
echo "3. 环境配置脚本: $PYTHON_WORKSPACE/scripts/setup_python_env.sh"
echo ""
echo "注意: 请运行 'source ~/.bashrc' 或重新打开终端以使环境变量生效"
echo ""
