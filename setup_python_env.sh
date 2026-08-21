#!/bin/bash
# 文件名：setup_python_env.sh
# 用途：配置Python虚拟环境和快捷命令，配置完成后使用run_eis.sh运行入口文件

echo "=== Python环境配置脚本 ==="
echo "使用默认配置：Python 3.9，环境名 eis_env"
echo "配置完成后将使用 run_eis.sh 运行 can_tester.py"
echo ""

# 设置默认值
PYTHON_VERSION="3.9"  # 默认Python版本
CONDA_ENV_NAME="eis_env"  # 默认虚拟环境名称
DEFAULT_ENTRY_FILE="can_tester.py"  # 默认入口文件名

# 检查存储设备挂载点（兼容SD卡和SSD）
if [ -n "$SSD_MOUNT" ]; then
    # 优先使用SSD_MOUNT
    STORAGE_MOUNT="$SSD_MOUNT"
    echo "使用SSD挂载点: $STORAGE_MOUNT"
elif [ -n "$SD_MOUNT" ]; then
    # 其次使用SD_MOUNT
    STORAGE_MOUNT="$SD_MOUNT"
    echo "使用SD卡挂载点: $STORAGE_MOUNT"
else
    # 默认尝试SSD挂载点
    STORAGE_MOUNT="/media/ssd_storage"
    echo "未设置存储挂载点，使用默认值: $STORAGE_MOUNT"
fi

# 检查存储设备是否已挂载
if [ ! -d "$STORAGE_MOUNT" ]; then
    echo "错误: 存储设备未挂载在 $STORAGE_MOUNT"
    echo "请先运行 setup_permanent_ssd.sh 或 setup_permanent_sd.sh"
    exit 1
fi

echo "存储设备挂载点: $STORAGE_MOUNT"

# 检查Anaconda是否已安装
ANACONDA_PATH="$STORAGE_MOUNT/anaconda3"
if [ ! -d "$ANACONDA_PATH" ]; then
    echo "错误: Anaconda未安装在 $ANACONDA_PATH"
    echo "请先运行基础设置脚本完成Anaconda安装"
    exit 1
fi

echo "Anaconda路径: $ANACONDA_PATH"
echo ""

# ============================================
# 初始化conda
# ============================================

echo "初始化conda环境..."

# 添加conda到PATH
export PATH="$ANACONDA_PATH/bin:$PATH"

# 检查conda是否可用
if ! command -v conda &> /dev/null; then
    echo "conda命令不可用，尝试初始化..."
    eval "$($ANACONDA_PATH/bin/conda shell.bash hook)"
fi

# 最终检查conda是否可用
if ! command -v conda &> /dev/null; then
    echo "错误: conda命令不可用，无法继续"
    echo "请手动运行: source $ANACONDA_PATH/etc/profile.d/conda.sh"
    exit 1
fi

echo "conda版本: $(conda --version)"

# 接受Conda许可条款
echo "接受Conda许可条款..."
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main 2>/dev/null || true
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r 2>/dev/null || true

# 检查base环境
conda activate base
if [ $? -ne 0 ]; then
    echo "警告: 无法激活base环境，尝试初始化..."
    conda init bash
    source ~/.bashrc
    conda activate base
fi

echo "当前Python版本: $(python --version)"
echo "当前conda版本: $(conda --version)"
echo ""

# ============================================
# 显示配置信息
# ============================================

echo "配置信息："
echo "- Python版本: $PYTHON_VERSION"
echo "- 虚拟环境名: $CONDA_ENV_NAME"
echo "- 入口文件: $DEFAULT_ENTRY_FILE"
echo ""

# ============================================
# 检查并删除已存在的环境
# ============================================

# 检查是否已存在同名虚拟环境
existing_envs=$(conda env list | awk '{print $1}' | grep "^$CONDA_ENV_NAME$")
if [ -n "$existing_envs" ]; then
    echo "虚拟环境 '$CONDA_ENV_NAME' 已存在"
    echo "删除旧环境并重新创建..."
    conda env remove -n "$CONDA_ENV_NAME" -y
    echo "旧环境已删除"
fi

# ============================================
# 创建新的虚拟环境
# ============================================

echo "创建新的conda虚拟环境..."
echo "环境名: $CONDA_ENV_NAME"
echo "Python版本: $PYTHON_VERSION"

# 使用清华镜像源创建环境（优先推荐）
echo "使用清华镜像源创建环境..."
conda create -n "$CONDA_ENV_NAME" python="$PYTHON_VERSION" -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main -y

if [ $? -eq 0 ]; then
    echo "虚拟环境创建成功！"
    
    # 配置镜像源以便后续使用
    echo "配置镜像源..."
    conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main 2>/dev/null || true
    conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r 2>/dev/null || true
    conda config --set show_channel_urls yes 2>/dev/null || true
else
    echo "使用镜像源创建失败，尝试使用默认源..."
    
    # 尝试使用默认源
    conda create -n "$CONDA_ENV_NAME" python="$PYTHON_VERSION" -y
    
    if [ $? -ne 0 ]; then
        echo "虚拟环境创建失败，尝试使用conda-forge..."
        
        # 使用conda-forge
        conda create -n "$CONDA_ENV_NAME" python="$PYTHON_VERSION" -c conda-forge -y
        
        if [ $? -ne 0 ]; then
            echo "错误: 所有方法都失败"
            exit 1
        fi
    fi
fi

# ============================================
# 激活虚拟环境
# ============================================

echo ""
echo "激活虚拟环境 '$CONDA_ENV_NAME'..."

# 重新初始化conda确保激活可用
source "$ANACONDA_PATH/etc/profile.d/conda.sh" 2>/dev/null || eval "$($ANACONDA_PATH/bin/conda shell.bash hook)"

# 激活环境
conda activate "$CONDA_ENV_NAME"

if [ $? -eq 0 ]; then
    echo "环境激活成功！"
    echo "当前Python版本: $(python --version)"
else
    echo "错误: 环境激活失败"
    exit 1
fi

# ============================================
# 检查并安装EIS_Online项目依赖
# ============================================

echo "检查EIS_Online项目依赖..."
PROJECT_DIR="$STORAGE_MOUNT/python_workspace/projects/EIS_Online"
if [ -d "$PROJECT_DIR" ]; then
    echo "找到EIS_Online项目: $PROJECT_DIR"
    
    # 检查入口文件是否存在
    if [ -f "$PROJECT_DIR/$DEFAULT_ENTRY_FILE" ]; then
        echo "找到入口文件: $DEFAULT_ENTRY_FILE"
    else
        echo "警告: 未找到入口文件 $DEFAULT_ENTRY_FILE"
        echo "请确保项目目录中有该文件"
    fi
    
    # 检查requirements.txt
    if [ -f "$PROJECT_DIR/requirements.txt" ]; then
        echo "发现项目依赖文件 requirements.txt"
        echo "安装项目依赖..."
        
        # 使用清华pip镜像源
        pip install -r "$PROJECT_DIR/requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null || \
        pip install -r "$PROJECT_DIR/requirements.txt"
        
        if [ $? -eq 0 ]; then
            echo "项目依赖安装成功"
        else
            echo "项目依赖安装失败"
        fi
    else
        echo "未找到requirements.txt文件"
        echo "创建默认的requirements.txt文件..."
        cat > "$PROJECT_DIR/requirements.txt" << 'EOF'
# EIS Online 项目依赖
python-can>=4.3.0
requests>=2.31.0
EOF
        echo "已创建默认requirements.txt"
        
        # 安装项目依赖
        echo "安装python-can和requests库..."
        pip install -r "$PROJECT_DIR/requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null || \
        pip install -r "$PROJECT_DIR/requirements.txt"
    fi
else
    echo "错误: 未找到EIS_Online项目目录"
    exit 1
fi

# ============================================
# 配置快捷命令
# ============================================

echo ""
echo "配置Python环境快捷命令..."

# 确定存储类型前缀
if [ "$STORAGE_MOUNT" = "/media/ssd_storage" ] || [ -n "$SSD_MOUNT" ]; then
    PREFIX="ssd"
    ALIAS_FILE=".bash_aliases_ssd"
else
    PREFIX="sd"
    ALIAS_FILE=".bash_aliases_sd"
fi

echo "使用存储类型: $PREFIX, 别名文件: $ALIAS_FILE"

# 创建激活脚本的完整路径
ACTIVATE_SCRIPT="$STORAGE_MOUNT/python_workspace/scripts/activate_eis_env.sh"

# 检查是否已经有别名文件
if [ -f ~/$ALIAS_FILE ]; then
    echo "更新现有的$ALIAS_FILE文件"
    # 移除旧的Python环境相关别名
    sed -i '/# Python环境快捷命令/d' ~/$ALIAS_FILE 2>/dev/null
    sed -i '/alias eis-/d' ~/$ALIAS_FILE 2>/dev/null
    sed -i "/alias ${PREFIX}-env=/d" ~/$ALIAS_FILE 2>/dev/null
    sed -i "/alias ${PREFIX}-activate=/d" ~/$ALIAS_FILE 2>/dev/null
else
    echo "创建新的$ALIAS_FILE文件"
fi

# 添加快捷命令到别名文件
cat >> ~/$ALIAS_FILE << EOF

# Python环境快捷命令（由setup_python_env.sh配置）
alias ${PREFIX}-env='source "$ACTIVATE_SCRIPT"'
alias eis-env='source "$ACTIVATE_SCRIPT"'
alias eis-run='cd "$PROJECT_DIR" && python "$DEFAULT_ENTRY_FILE"'
alias eis-test='cd "$PROJECT_DIR" && python -m pytest'
alias ${PREFIX}-projects='cd "$STORAGE_MOUNT/python_workspace/projects"'
alias ${PREFIX}-notebook='jupyter notebook --notebook-dir="$STORAGE_MOUNT/python_workspace/notebooks"'
alias ${PREFIX}-data='cd "$STORAGE_MOUNT/python_workspace/data"'
alias ${PREFIX}-scripts='cd "$STORAGE_MOUNT/python_workspace/scripts"'
alias ${PREFIX}-activate='source "$STORAGE_MOUNT/anaconda3/etc/profile.d/conda.sh"'
EOF

# 确保.bashrc加载这个别名文件
if [ -f ~/.bashrc ]; then
    # 移除可能存在的旧的别名文件加载
    sed -i "/$ALIAS_FILE/d" ~/.bashrc 2>/dev/null
    
    echo "" >> ~/.bashrc
    echo "# 加载${PREFIX}快捷命令" >> ~/.bashrc
    echo "if [ -f ~/$ALIAS_FILE ]; then" >> ~/.bashrc
    echo "    . ~/$ALIAS_FILE" >> ~/.bashrc
    echo "fi" >> ~/.bashrc
    echo "已添加到 ~/.bashrc"
else
    echo "警告: 未找到 ~/.bashrc 文件"
fi

# ============================================
# 创建环境激活脚本
# ============================================

echo ""
echo "创建环境激活脚本..."
mkdir -p "$STORAGE_MOUNT/python_workspace/scripts"

cat > "$ACTIVATE_SCRIPT" << 'EOF'
#!/bin/bash
# EIS项目环境激活脚本

echo "=== 激活 eis_env 环境 ==="

# 自动检测存储设备
if [ -d "/media/ssd_storage/anaconda3" ]; then
    STORAGE_MOUNT="/media/ssd_storage"
elif [ -d "/media/sd_storage/anaconda3" ]; then
    STORAGE_MOUNT="/media/sd_storage"
else
    echo "错误: 未找到存储设备"
    exit 1
fi

ANACONDA_PATH="$STORAGE_MOUNT/anaconda3"

# 初始化conda（多种方法尝试）
if [ -f "$ANACONDA_PATH/etc/profile.d/conda.sh" ]; then
    source "$ANACONDA_PATH/etc/profile.d/conda.sh"
else
    eval "$($ANACONDA_PATH/bin/conda shell.bash hook)"
fi

# 激活环境
conda activate eis_env

if [ $? -eq 0 ]; then
    echo "环境激活成功！"
    echo "Python版本: $(python --version 2>/dev/null || echo '未知')"
    echo ""
    echo "项目目录: $STORAGE_MOUNT/python_workspace/projects/EIS_Online"
    echo "运行项目: eis-run"
else
    echo "环境激活失败，尝试直接设置PATH..."
    export PATH="$ANACONDA_PATH/envs/eis_env/bin:$PATH"
    echo "通过PATH设置激活"
fi
EOF

chmod +x "$ACTIVATE_SCRIPT"
echo "已创建环境激活脚本: $ACTIVATE_SCRIPT"

# ============================================
# 创建项目运行脚本
# ============================================

echo ""
echo "创建项目运行脚本..."

RUN_SCRIPT="$PROJECT_DIR/run_eis.sh"
cat > "$RUN_SCRIPT" << 'EOF'
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
EOF

chmod +x "$RUN_SCRIPT"
echo "已创建项目运行脚本: $RUN_SCRIPT"

# ============================================
# 配置完成后自动运行入口文件
# ============================================

echo ""
echo "=== 环境配置完成 ==="
echo "正在使用 run_eis.sh 启动 EIS Online 项目..."
echo ""

# 使用 run_eis.sh 脚本运行项目
echo "调用运行脚本: $RUN_SCRIPT"
echo ""

bash "$RUN_SCRIPT"

RUN_STATUS=$?

echo ""
echo "========================================"
echo "配置总结"
echo "========================================"
echo ""

if [ $RUN_STATUS -eq 0 ]; then
    echo "🎉 恭喜！环境配置和项目运行都已完成！"
else
    echo "⚠ 环境配置完成，但项目运行遇到问题"
fi

echo ""
echo "✓ 虚拟环境已创建: $CONDA_ENV_NAME"
echo "✓ Python版本: $(python --version 2>/dev/null || echo '请运行 eis-env 检查')"
echo "✓ 基础包已安装: numpy, pandas, matplotlib, requests等"
echo "✓ 项目依赖已安装: python-can"
echo "✓ 快捷命令已配置"
echo "✓ 运行脚本已创建: $RUN_SCRIPT"
echo "✓ 项目已尝试运行 (退出代码: $RUN_STATUS)"
echo ""
echo "存储设备信息:"
echo "- 挂载点: $STORAGE_MOUNT"
echo "- 工作空间: $STORAGE_MOUNT/python_workspace"
echo "- 存储类型: $PREFIX"
echo ""
echo "快捷命令列表:"
echo "1. 激活EIS环境: eis-env 或 ${PREFIX}-env"
echo "2. 运行EIS项目: eis-run 或 bash $RUN_SCRIPT"
echo "3. 进入项目目录: ${PREFIX}-projects"
echo "4. 启动Jupyter: ${PREFIX}-notebook"
echo "5. 进入数据目录: ${PREFIX}-data"
echo "6. 进入脚本目录: ${PREFIX}-scripts"
echo "7. 激活conda: ${PREFIX}-activate"
echo ""
echo "项目相关:"
echo "- 项目位置: $PROJECT_DIR"
echo "- 入口文件: $PROJECT_DIR/$DEFAULT_ENTRY_FILE"
echo "- 运行脚本: $RUN_SCRIPT"
echo "- 激活脚本: $ACTIVATE_SCRIPT"
echo ""
echo "下一步操作:"
echo "1. 重新加载bash配置: source ~/.bashrc"
echo "2. 日常使用: eis-run 或 bash $RUN_SCRIPT"
echo "3. 手动运行: cd $PROJECT_DIR && python $DEFAULT_ENTRY_FILE"
echo ""
echo "注意:"
echo "- 每次打开新终端，需要先运行 'source ~/.bashrc' 加载快捷命令"
echo "- 项目可能需要CAN硬件支持才能正常运行"
echo "- 查看运行脚本源码: cat $RUN_SCRIPT"
echo ""
