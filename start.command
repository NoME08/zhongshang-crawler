#!/bin/bash
cd "$(dirname "$0")"

echo "========================================"
echo "  淑琪同学 · 中商情报网爬虫"
echo "========================================"
echo ""

# ── 💌 今日份甜度 ──
QUOTES=(
  "一起去散步呗。"
  "今晚月色真美。"
  "世间所有的相遇，都是久别重逢。"
  "山有木兮木有枝，心悦君兮君不知。"
  "所爱隔山海，山海皆可平。"
  "我见众生皆草木，唯有见你是青山。"
  "晓看天色暮看云，行也思君，坐也思君。"
  "既见君子，云胡不喜。"
  "愿我如星君如月，夜夜流光相皎洁。"
  "幸得识卿桃花面，从此阡陌多暖春。"
  "有人问粥可温，有人与立黄昏。"
  "白茶清欢无别事，我在等风也等你。"
  "玲珑骰子安红豆，入骨相思知不知。"
  "沅有芷兮澧有兰，思君子兮未敢言。"
  "我的勇气和你的勇气加起来，对付这个世界总够了吧。"
  "平安喜乐"
)
RANDOM_INDEX=$((RANDOM % ${#QUOTES[@]}))
echo "💌 今日份甜度："
echo "   \"${QUOTES[$RANDOM_INDEX]}\""
echo ""

# ── ① 检查 Python3 ──
echo "🔍 检查 Python3..."
if ! command -v python3 &>/dev/null; then
    echo "❌ 未找到 python3，请先安装 Python："
    echo "   https://www.python.org/downloads/"
    echo ""
    echo "   安装完成后重新双击 start.command 即可。"
    read -p "按回车退出..."
    exit 1
fi
echo "   ✅ Python3: $(python3 --version)"

# ── ② 检查 pip ──
echo "🔍 检查 pip..."
if ! python3 -m pip --version &>/dev/null; then
    echo "   ⚠️  pip 不可用，尝试自动安装..."
    python3 -m ensurepip --upgrade 2>/dev/null
    if ! python3 -m pip --version &>/dev/null; then
        echo "   ❌ pip 安装失败，请手动安装后重试。"
        read -p "按回车退出..."
        exit 1
    fi
fi
echo "   ✅ pip 就绪"

# ── ③ 安装 Python 依赖 ──
echo "📦 安装 Python 依赖..."
python3 -m pip install -r requirements.txt --quiet
if [ $? -ne 0 ]; then
    echo "   ⚠️  依赖安装可能不完整，尝试继续..."
else
    echo "   ✅ 依赖安装完成"
fi

# ── ④ 检查 Homebrew ──
HAVE_BREW=false
if command -v brew &>/dev/null; then
    HAVE_BREW=true
    echo "🍺 Homebrew 就绪"
else
    echo "⚠️  未安装 Homebrew（自动安装 LibreOffice 需要）"
    echo "   如需 PDF 功能，请在终端执行以下命令安装 Homebrew："
    echo ""
    echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    echo ""
    echo "   安装完成后重新双击 start.command 即可。"
    echo "   暂时跳过 LibreOffice，可正常使用 Word 文档功能。"
    echo ""
fi

# ── ⑤ 检查 / 安装 LibreOffice ──
LO_PATH="/Applications/LibreOffice.app/Contents/MacOS/soffice"

if [ -f "$LO_PATH" ]; then
    # 已经装过：只做功能验证（实际运行 --version）
    echo "🔍 验证 LibreOffice 是否可用..."
    LO_CHECK=$("$LO_PATH" --headless --version 2>/dev/null)
    if [ $? -eq 0 ] && echo "$LO_CHECK" | grep -q "LibreOffice"; then
        echo "   ✅ LibreOffice 就绪 ($LO_CHECK)"
    else
        echo "   ⚠️  LibreOffice 文件存在但不能正常执行（可能被 macOS 隔离）"
        echo "   尝试修复..."
        xattr -d com.apple.quarantine /Applications/LibreOffice.app 2>/dev/null
        LO_CHECK2=$("$LO_PATH" --headless --version 2>/dev/null)
        if [ $? -eq 0 ] && echo "$LO_CHECK2" | grep -q "LibreOffice"; then
            echo "   ✅ 修复成功，LibreOffice 就绪"
        else
            echo "   ⚠️  仍不可用，PDF 功能将跳过"
            echo "   请手动打开一次 LibreOffice.app 再重试。"
        fi
    fi
elif $HAVE_BREW; then
    echo "📦 安装 LibreOffice（约 3 分钟，仅首次）..."
    brew install --cask libreoffice
    if [ -f "$LO_PATH" ]; then
        echo "   ✅ 安装完成"
        # 移除 macOS 隔离标记，否则 headless 模式会被拦截
        echo "   🔧 解除 macOS 隔离限制..."
        xattr -d com.apple.quarantine /Applications/LibreOffice.app 2>/dev/null
        # 预热启动：让 LibreOffice 创建好用户配置目录
        # 首次 headless 运行需要初始化 ~/.config/libreoffice，不预热会超时
        echo "   🔧 预热 LibreOffice（首次运行初始化）..."
        "$LO_PATH" --headless --terminate_after_init &
        LO_PID=$!
        # 等待最多 20 秒
        for i in $(seq 1 20); do
            sleep 1
            if ! kill -0 "$LO_PID" 2>/dev/null; then
                break
            fi
            if [ $i -eq 20 ]; then
                kill "$LO_PID" 2>/dev/null
            fi
        done
        wait "$LO_PID" 2>/dev/null
        echo "   ✅ LibreOffice 准备就绪"
    else
        echo "   ⚠️  安装可能失败，PDF 功能不可用"
        echo "   可手动安装：https://www.libreoffice.org/download/"
    fi
else
    echo "📦 未检测到 LibreOffice，且没有 Homebrew，跳过安装。"
    echo "   PDF 功能不可用，但 Word 文档正常生成。"
    echo "   如需 PDF：先安装 Homebrew，再重新运行本脚本即可。"
fi

echo ""
echo "🌸 启动中..."
echo "   浏览器将自动打开 http://localhost:1108"
echo "   关闭本窗口即可停止服务"
echo ""

# 杀掉之前可能残留的进程（关闭窗口后孤儿进程仍占端口）
OLD_PID=$(lsof -ti:1108 2>/dev/null)
if [ -n "$OLD_PID" ]; then
    echo "🔧 清理上次残留的进程 (PID: $OLD_PID)..."
    kill "$OLD_PID" 2>/dev/null
    sleep 0.5
    # 如果还没死，强杀
    kill -9 "$OLD_PID" 2>/dev/null
fi

# 启动 Flask，记录 PID，退出时自动清理
python3 app.py &
PY_PID=$!

# 窗口关闭 / Ctrl+C / 脚本退出时，自动杀掉 Flask 进程
cleanup() {
    kill "$PY_PID" 2>/dev/null
    wait "$PY_PID" 2>/dev/null
    echo "👋 服务已停止"
}
trap cleanup EXIT INT TERM

sleep 1.5
open http://localhost:1108
wait "$PY_PID"
