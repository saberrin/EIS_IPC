#!/bin/bash
# 文件名：install_eis_complete.sh
# 用途：完整的EIS Online安装脚本

echo "==============================================="
echo "      EIS Online 完整安装脚本"
echo "==============================================="
echo "注意：此脚本将完成所有安装步骤"
echo "包括：SSD挂载、环境配置、项目部署"
echo "==============================================="
echo ""

# 检查是否以root权限运行
if [ "$EUID" -ne 0 ]; then 
    echo "警告: 建议使用sudo运行此脚本"
    echo "请使用: sudo ./install_eis_complete.sh"
    read -p "是否继续? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# ================================================
# 第一部分：获取U盘路径和检查文件
# ================================================

echo "=== 第一步：检查U盘文件 ==="
echo ""

# 获取脚本所在目录（U盘根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "U盘路径: $SCRIPT_DIR"
echo ""

# 配置下位机与EIS服务器通信使用的永久静态网络地址。
# 可通过环境变量覆盖默认值：
# EIS_NETWORK_INTERFACE=eth1 EIS_STATIC_CIDR=192.168.98.3/24 EIS_SERVER_IP=192.168.98.2
NETWORK_SETUP_SCRIPT="$SCRIPT_DIR/setup_static_network.sh"
NETWORK_CONFIGURED=false
if [ "${EIS_SKIP_NETWORK_SETUP:-0}" = "1" ]; then
    echo "已通过 EIS_SKIP_NETWORK_SETUP=1 跳过网络配置"
elif [ -f "$NETWORK_SETUP_SCRIPT" ]; then
    echo "=== 配置EIS通信网卡 ==="
    chmod +x "$NETWORK_SETUP_SCRIPT"
    if bash "$NETWORK_SETUP_SCRIPT"; then
        NETWORK_CONFIGURED=true
        echo "EIS通信网卡配置完成"
    else
        echo "错误: EIS通信网卡配置失败"
        exit 1
    fi
    echo ""
else
    echo "错误: 未找到网络配置脚本 $NETWORK_SETUP_SCRIPT"
    exit 1
fi

# 显示U盘内容
echo "U盘内容:"
ls -lh "$SCRIPT_DIR"
echo ""

# 查找Anaconda安装包
echo "查找Anaconda安装包..."
ANACONDA_FILE=$(find "$SCRIPT_DIR" -maxdepth 1 -name "Anaconda*.sh" -o -name "anaconda*.sh" | head -1)
if [ -n "$ANACONDA_FILE" ]; then
    echo "找到: $(basename "$ANACONDA_FILE")"
    ANACONDA_FOUND=true
else
    echo "警告: 未找到Anaconda安装包"
    echo "如果Anaconda已安装，脚本将跳过安装步骤"
    ANACONDA_FOUND=false
fi
echo ""

# 查找Python项目
echo "查找Python项目..."
if [ -d "$SCRIPT_DIR/EIS_Online" ]; then
    echo "找到Python项目目录: EIS_Online"
    PYTHON_PROJECTS="$SCRIPT_DIR/EIS_Online"
else
    echo "错误: 未找到EIS_Online目录"
    echo "请将EIS_Online项目目录放在U盘根目录"
    exit 1
fi
echo ""

# ================================================
# 第二部分：SSD设置
# ================================================

echo "=== 第二步：SSD存储设备设置 ==="
echo ""

# 检测存储设备
echo "检测存储设备..."
lsblk
echo ""

# 让用户选择SSD设备
echo "请根据上面的设备列表选择SSD设备:"
echo "注意: 请选择分区（如 /dev/sda1），而不是整个磁盘（如 /dev/sda）"
echo ""
read -p "请输入SSD设备路径 (例如: /dev/sda1): " SSD_DEVICE

if [ ! -b "$SSD_DEVICE" ]; then
    echo "错误: 设备 $SSD_DEVICE 不存在"
    echo "可用的设备列表:"
    lsblk
    exit 1
fi

echo "使用SSD设备: $SSD_DEVICE"

# 创建永久挂载点
SSD_MOUNT="/media/ssd_storage"
echo "创建永久挂载点: $SSD_MOUNT"
mkdir -p "$SSD_MOUNT"

# 检查是否已挂载
if mount | grep -q "$SSD_DEVICE"; then
    echo "SSD已挂载在其他位置，尝试重新挂载..."
    CURRENT_MOUNT=$(mount | grep "$SSD_DEVICE" | awk '{print $3}')
    umount "$CURRENT_MOUNT" 2>/dev/null
fi

# 挂载SSD到永久位置
echo "挂载SSD到 $SSD_MOUNT ..."
mount "$SSD_DEVICE" "$SSD_MOUNT"
if [ $? -ne 0 ]; then
    echo "错误: 无法挂载SSD"
    echo "SSD可能需要格式化"
    exit 1
fi

echo "SSD已成功挂载到: $SSD_MOUNT"
echo ""

# 设置自动挂载
echo "配置自动挂载..."
SSD_UUID=$(blkid -s UUID -o value "$SSD_DEVICE")
if [ -n "$SSD_UUID" ]; then
    echo "SSD UUID: $SSD_UUID"
    
    # 添加到/etc/fstab
    FSTAB_ENTRY="UUID=$SSD_UUID $SSD_MOUNT auto defaults,nofail 0 2"
    if ! grep -q "$SSD_MOUNT" /etc/fstab; then
        echo "添加自动挂载配置到 /etc/fstab"
        echo "$FSTAB_ENTRY" >> /etc/fstab
        echo "自动挂载配置完成"
    else
        echo "SSD已在 /etc/fstab 中配置了自动挂载"
    fi
else
    echo "警告: 无法获取SSD UUID，将使用设备路径配置"
    FSTAB_ENTRY="$SSD_DEVICE $SSD_MOUNT auto defaults,nofail 0 2"
    if ! grep -q "$SSD_MOUNT" /etc/fstab; then
        echo "$FSTAB_ENTRY" >> /etc/fstab
    fi
fi
echo ""

# ================================================
# 第三部分：创建目录结构和拷贝文件
# ================================================

echo "=== 第三步：创建Python工作环境 ==="
echo ""

# 创建Python工作目录结构
echo "创建Python工作目录结构..."
PYTHON_WORKSPACE="$SSD_MOUNT/python_workspace"
mkdir -p "$PYTHON_WORKSPACE/projects"
mkdir -p "$PYTHON_WORKSPACE/data"
mkdir -p "$PYTHON_WORKSPACE/notebooks"
mkdir -p "$PYTHON_WORKSPACE/venvs"
mkdir -p "$PYTHON_WORKSPACE/scripts"

echo "Python工作空间创建在: $PYTHON_WORKSPACE"
echo ""

# 拷贝文件到SSD
echo "拷贝文件到SSD..."

# 1. 拷贝Anaconda安装包（如果存在）
if [ "$ANACONDA_FOUND" = true ]; then
    echo "拷贝Anaconda安装包..."
    cp "$ANACONDA_FILE" "$PYTHON_WORKSPACE/scripts/"
    echo "已拷贝: $(basename "$ANACONDA_FILE")"
fi

# 2. 拷贝Python项目
echo "拷贝Python项目 EIS_Online..."
PROJECT_NAME=$(basename "$PYTHON_PROJECTS")
cp -r "$PYTHON_PROJECTS" "$PYTHON_WORKSPACE/projects/"
echo "项目已拷贝到: $PYTHON_WORKSPACE/projects/$PROJECT_NAME"

# 检查并拷贝项目依赖文件
if [ -f "$PYTHON_PROJECTS/requirements.txt" ]; then
    echo "找到项目依赖文件 requirements.txt"
    cp "$PYTHON_PROJECTS/requirements.txt" "$PYTHON_WORKSPACE/projects/$PROJECT_NAME/"
fi

echo "文件拷贝完成"
echo ""

# ================================================
# 第四部分：安装Anaconda（如果未安装）
# ================================================

echo "=== 第四步：检查并安装Anaconda ==="
echo ""

ANACONDA_PATH="$SSD_MOUNT/anaconda3"

# 检查Anaconda是否已安装
if [ -d "$ANACONDA_PATH" ]; then
    echo "✓ Anaconda已安装在: $ANACONDA_PATH"
    echo "跳过Anaconda安装步骤"
    ANACONDA_INSTALLED=true
else
    echo "Anaconda未安装，开始安装..."
    ANACONDA_INSTALLED=false
    
    if [ "$ANACONDA_FOUND" = true ]; then
        ANACONDA_BASENAME=$(basename "$ANACONDA_FILE")
        ANACONDA_INSTALLER="$PYTHON_WORKSPACE/scripts/$ANACONDA_BASENAME"
        
        echo "正在安装Anaconda到SSD，请稍候..."
        echo "安装路径: $ANACONDA_PATH"
        
        # 检查安装包权限
        chmod +x "$ANACONDA_INSTALLER"
        
        # 安装Anaconda（静默模式）
        bash "$ANACONDA_INSTALLER" -b -p "$ANACONDA_PATH"
        
        if [ $? -eq 0 ]; then
            echo "✓ Anaconda安装成功！"
            ANACONDA_INSTALLED=true
        else
            echo "错误: Anaconda安装失败"
            echo "请手动安装Anaconda或使用已存在的安装"
            ANACONDA_INSTALLED=false
        fi
    else
        echo "错误: 未找到Anaconda安装包且Anaconda未安装"
        echo "请将Anaconda安装包放在U盘根目录"
        exit 1
    fi
fi

echo ""

# ================================================
# 第五部分：设置权限
# ================================================

echo "=== 第五步：设置文件权限 ==="
echo ""

# 设置所有权
echo "设置文件所有权..."
USERNAME=$(logname 2>/dev/null || echo $SUDO_USER)
if [ -z "$USERNAME" ]; then
    USERNAME=$USER
fi

chown -R "$USERNAME:$USERNAME" "$SSD_MOUNT"

# 设置目录权限
echo "设置目录权限..."
chmod 755 "$SSD_MOUNT"
chmod -R 755 "$PYTHON_WORKSPACE"

# 设置Python文件权限
if [ -d "$PYTHON_WORKSPACE/projects/EIS_Online" ]; then
    echo "设置EIS_Online项目文件权限..."
    
    # Python文件设置为可执行
    find "$PYTHON_WORKSPACE/projects/EIS_Online" -name "*.py" -type f -exec chmod 755 {} \;
    
    # 文本文件设置为可读可写
    find "$PYTHON_WORKSPACE/projects/EIS_Online" -name "*.txt" -o -name "*.md" -type f -exec chmod 644 {} \;
    
    echo "✓ 项目文件权限设置完成"
fi

echo "权限设置完成"
echo ""

# ================================================
# 第六部分：配置Python环境
# ================================================

echo "=== 第六步：配置Python环境 ==="
echo ""

# 检查Anaconda是否可用
if [ "$ANACONDA_INSTALLED" = false ]; then
    echo "错误: Anaconda未安装，无法配置Python环境"
    echo "请先安装Anaconda"
    exit 1
fi

# 设置默认值
PYTHON_VERSION="3.9"
CONDA_ENV_NAME="eis_env"
DEFAULT_ENTRY_FILE="can_tester.py"

STORAGE_MOUNT="$SSD_MOUNT"
ANACONDA_PATH="$STORAGE_MOUNT/anaconda3"
PROJECT_DIR="$STORAGE_MOUNT/python_workspace/projects/EIS_Online"

echo "存储设备挂载点: $STORAGE_MOUNT"
echo "Anaconda路径: $ANACONDA_PATH"
echo "项目目录: $PROJECT_DIR"
echo ""

# 初始化conda
echo "初始化conda环境..."
export PATH="$ANACONDA_PATH/bin:$PATH"

# 检查conda是否可用
if ! command -v conda &> /dev/null; then
    echo "conda命令不可用，尝试初始化..."
    eval "$($ANACONDA_PATH/bin/conda shell.bash hook)"
fi

if ! command -v conda &> /dev/null; then
    echo "错误: conda命令不可用"
    exit 1
fi

echo "✓ conda版本: $(conda --version)"

# 接受Conda许可条款
echo "接受Conda许可条款..."
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main 2>/dev/null || true
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r 2>/dev/null || true

# 激活base环境
echo "激活base环境..."
conda activate base
if [ $? -ne 0 ]; then
    echo "初始化conda..."
    conda init bash
    source ~/.bashrc
    conda activate base
fi

echo "✓ 当前Python版本: $(python --version)"
echo ""

# ============================================
# 检查并创建虚拟环境
# ============================================

echo "检查虚拟环境 '$CONDA_ENV_NAME'..."
existing_envs=$(conda env list | awk '{print $1}' | grep "^$CONDA_ENV_NAME$")

if [ -n "$existing_envs" ]; then
    echo "✓ 虚拟环境 '$CONDA_ENV_NAME' 已存在"
    echo "使用现有环境"
    ENV_EXISTS=true
else
    echo "虚拟环境 '$CONDA_ENV_NAME' 不存在，开始创建..."
    ENV_EXISTS=false
    
    echo "创建虚拟环境..."
    echo "Python版本: $PYTHON_VERSION"
    
    # 创建环境
    echo "使用清华镜像源创建环境..."
    conda create -n "$CONDA_ENV_NAME" python="$PYTHON_VERSION" -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main -y
    
    if [ $? -eq 0 ]; then
        echo "✓ 虚拟环境创建成功！"
        ENV_EXISTS=true
    else
        echo "尝试使用默认源创建环境..."
        conda create -n "$CONDA_ENV_NAME" python="$PYTHON_VERSION" -y
        
        if [ $? -eq 0 ]; then
            echo "✓ 虚拟环境创建成功！"
            ENV_EXISTS=true
        else
            echo "错误: 虚拟环境创建失败"
            ENV_EXISTS=false
        fi
    fi
fi

# ============================================
# 激活环境并安装包
# ============================================

if [ "$ENV_EXISTS" = true ]; then
    echo ""
    echo "激活虚拟环境..."
    source "$ANACONDA_PATH/etc/profile.d/conda.sh"
    conda activate "$CONDA_ENV_NAME"
    
    if [ $? -eq 0 ]; then
        echo "✓ 环境激活成功！"
        echo "✓ 当前Python版本: $(python --version)"
    else
        echo "错误: 环境激活失败"
        exit 1
    fi
    
    echo ""
    
else
    echo "错误: 虚拟环境不可用，跳过包安装"
fi

# ============================================
# 安装项目依赖
# ============================================

if [ "$ENV_EXISTS" = true ]; then
    echo "检查EIS_Online项目依赖..."
    
    # 检查requirements.txt
    if [ -f "$PROJECT_DIR/requirements.txt" ]; then
        echo "安装或更新项目依赖文件 requirements.txt..."
        pip install -r "$PROJECT_DIR/requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null || \
        pip install -r "$PROJECT_DIR/requirements.txt"

        if [ $? -eq 0 ] && python -c "import can, requests" &>/dev/null; then
            echo "✓ 项目依赖安装成功（python-can、requests）"
        else
            echo "⚠ 项目依赖安装或导入检查失败"
        fi
    else
        echo "未找到requirements.txt文件"
        echo "创建默认requirements.txt并安装python-can、requests..."

        cat > "$PROJECT_DIR/requirements.txt" << 'EOF'
# EIS Online 项目依赖
python-can>=4.3.0
requests>=2.31.0
EOF
        pip install -r "$PROJECT_DIR/requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null || \
        pip install -r "$PROJECT_DIR/requirements.txt"

        if [ $? -eq 0 ] && python -c "import can, requests" &>/dev/null; then
            echo "✓ python-can、requests安装成功"
        else
            echo "⚠ python-can或requests安装失败"
        fi
    fi
    
    echo ""
else
    echo "跳过项目依赖安装（环境不可用）"
    echo ""
fi

# ============================================
# 第七部分：创建运行脚本和快捷命令
# ============================================

echo "=== 第七步：创建运行脚本和快捷命令 ==="
echo ""

# 创建运行脚本
RUN_SCRIPT="$PROJECT_DIR/run_eis.sh"
echo "检查运行脚本..."

if [ -f "$RUN_SCRIPT" ]; then
    echo "✓ 运行脚本已存在: $RUN_SCRIPT"
else
    echo "创建运行脚本: $RUN_SCRIPT"
    
    cat > "$RUN_SCRIPT" << 'EOF'
#!/bin/bash
# EIS项目运行脚本

echo "========================================"
echo "启动 EIS Online 项目"
echo "========================================"
echo ""

STORAGE_MOUNT="/media/ssd_storage"
ANACONDA_PATH="$STORAGE_MOUNT/anaconda3"
PROJECT_DIR="$STORAGE_MOUNT/python_workspace/projects/EIS_Online"
ENTRY_FILE="can_tester.py"

echo "存储路径: $STORAGE_MOUNT"
echo "项目目录: $PROJECT_DIR"
echo "入口文件: $ENTRY_FILE"
echo ""

# 检查Anaconda是否安装
if [ ! -d "$ANACONDA_PATH" ]; then
    echo "错误: Anaconda未安装"
    exit 1
fi

# 初始化conda
if [ -f "$ANACONDA_PATH/etc/profile.d/conda.sh" ]; then
    source "$ANACONDA_PATH/etc/profile.d/conda.sh"
else
    echo "错误: 无法初始化conda"
    exit 1
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
fi

exit $RUN_STATUS
EOF
    
    chmod +x "$RUN_SCRIPT"
    echo "✓ 运行脚本创建完成"
fi
echo ""

# 创建环境激活脚本
ACTIVATE_SCRIPT="$STORAGE_MOUNT/python_workspace/scripts/activate_eis_env.sh"
echo "检查环境激活脚本..."

if [ -f "$ACTIVATE_SCRIPT" ]; then
    echo "✓ 环境激活脚本已存在: $ACTIVATE_SCRIPT"
else
    echo "创建环境激活脚本: $ACTIVATE_SCRIPT"
    
    cat > "$ACTIVATE_SCRIPT" << EOF
#!/bin/bash
# EIS项目环境激活脚本

echo "=== 激活 eis_env 环境 ==="

STORAGE_MOUNT="/media/ssd_storage"
ANACONDA_PATH="\$STORAGE_MOUNT/anaconda3"

# 检查Anaconda是否安装
if [ ! -d "\$ANACONDA_PATH" ]; then
    echo "错误: Anaconda未安装"
    exit 1
fi

# 初始化conda
if [ -f "\$ANACONDA_PATH/etc/profile.d/conda.sh" ]; then
    source "\$ANACONDA_PATH/etc/profile.d/conda.sh"
else
    echo "错误: 无法初始化conda"
    exit 1
fi

# 激活环境
conda activate eis_env

if [ \$? -eq 0 ]; then
    echo "环境激活成功！"
    echo "Python版本: \$(python --version)"
    echo ""
    echo "项目目录: \$STORAGE_MOUNT/python_workspace/projects/EIS_Online"
    echo "运行项目: bash \$STORAGE_MOUNT/python_workspace/projects/EIS_Online/run_eis.sh"
else
    echo "环境激活失败"
    exit 1
fi
EOF
    
    chmod +x "$ACTIVATE_SCRIPT"
    echo "✓ 激活脚本创建完成"
fi
echo ""

# 创建快捷命令
echo "配置快捷命令..."
ALIAS_FILE=".bash_aliases_eis"

if [ -f "/home/$USERNAME/$ALIAS_FILE" ] && grep -q "eis-run" "/home/$USERNAME/$ALIAS_FILE"; then
    echo "✓ 快捷命令已配置"
else
    echo "创建快捷命令文件..."
    
    cat > "/home/$USERNAME/$ALIAS_FILE" << EOF
# EIS项目快捷命令
alias eis-env='source "$ACTIVATE_SCRIPT"'
alias eis-run='bash "$RUN_SCRIPT"'
alias eis-projects='cd "$PROJECT_DIR"'
alias eis-notebook='jupyter notebook --notebook-dir="$STORAGE_MOUNT/python_workspace/notebooks"'
alias eis-activate='source "$ANACONDA_PATH/etc/profile.d/conda.sh"'
EOF
    
    # 添加到bashrc
    if [ -f "/home/$USERNAME/.bashrc" ]; then
        echo "" >> "/home/$USERNAME/.bashrc"
        echo "# EIS项目快捷命令" >> "/home/$USERNAME/.bashrc"
        echo "if [ -f ~/$ALIAS_FILE ]; then" >> "/home/$USERNAME/.bashrc"
        echo "    . ~/$ALIAS_FILE" >> "/home/$USERNAME/.bashrc"
        echo "fi" >> "/home/$USERNAME/.bashrc"
        echo "✓ 快捷命令已添加到 ~/.bashrc"
    fi
fi

echo ""

# ============================================
# 第八部分：测试运行
# ============================================

echo "=== 第八步：测试运行 ==="
echo ""

if [ "$ENV_EXISTS" = true ] && [ -f "$RUN_SCRIPT" ]; then
    echo "正在测试运行 EIS Online 项目..."
    echo ""
    
    # 询问用户是否要测试运行
    read -p "是否要测试运行项目? (Y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        echo "跳过测试运行"
        RUN_STATUS=-1
    else
        bash "$RUN_SCRIPT"
        RUN_STATUS=$?
    fi
else
    echo "跳过测试运行（环境或脚本不可用）"
    RUN_STATUS=-1
fi

echo ""

# ============================================
# 第九部分：完成总结
# ============================================

echo "==============================================="
echo "         安装完成总结"
echo "==============================================="
echo ""

echo "安装状态:"
echo "✓ SSD存储: $SSD_MOUNT"
echo "✓ 自动挂载: 已配置"
if [ "$NETWORK_CONFIGURED" = true ]; then
    echo "✓ EIS通信网络: ${EIS_STATIC_CIDR:-192.168.98.3/24}"
else
    echo "○ EIS通信网络: 已跳过"
fi

if [ "$ANACONDA_INSTALLED" = true ]; then
    echo "✓ Anaconda: $ANACONDA_PATH"
else
    echo "✗ Anaconda: 未安装"
fi

if [ "$ENV_EXISTS" = true ]; then
    echo "✓ 虚拟环境: $CONDA_ENV_NAME"
    echo "✓ Python包: 已安装"
else
    echo "✗ 虚拟环境: 不可用"
fi

echo "✓ 项目文件: $PROJECT_DIR"
echo "✓ 运行脚本: $RUN_SCRIPT"
echo "✓ 快捷命令: 已配置"

if [ $RUN_STATUS -eq 0 ]; then
    echo "✓ 测试运行: 成功"
elif [ $RUN_STATUS -eq -1 ]; then
    echo "○ 测试运行: 跳过"
else
    echo "⚠ 测试运行: 失败 (代码: $RUN_STATUS)"
fi

echo ""
echo "重要路径:"
echo "- 项目目录: $PROJECT_DIR"
echo "- 运行脚本: $RUN_SCRIPT"
echo "- 激活脚本: $ACTIVATE_SCRIPT"
echo "- Anaconda路径: $ANACONDA_PATH"
echo ""
echo "使用方法:"
echo "1. 重新加载bash配置:"
echo "   source ~/.bashrc"
echo ""
echo "2. 日常使用快捷命令:"
echo "   eis-run          # 运行项目"
echo "   eis-env          # 激活环境"
echo "   eis-projects     # 进入项目目录"
echo ""
echo "3. 或者直接运行:"
echo "   bash $RUN_SCRIPT"
echo ""
echo "4. 手动运行:"
echo "   cd $PROJECT_DIR"
echo "   python can_tester.py"
echo ""
echo "注意:"
echo "- 重启后SSD会自动挂载"
echo "- EIS通信网卡会在重启后自动配置为 ${EIS_STATIC_CIDR:-192.168.98.3/24}"
echo "- EIS服务器地址默认为 ${EIS_SERVER_IP:-192.168.98.2}"
echo "- 如果CAN设备未连接，项目可能无法正常运行"
echo "- 重新运行此脚本会跳过已完成的步骤"
echo ""
echo "==============================================="
echo "安装完成！感谢使用EIS Online安装脚本"
echo "==============================================="
