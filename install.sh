#!/bin/bash
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "错误: 请使用 sudo ./install.sh 运行安装器" >&2
    exit 1
fi

REPO_URL="https://raw.githubusercontent.com/daedlock/deepcool-lm/main"
TEMP_DIR=$(mktemp -d)
SOURCE_DIR="$TEMP_DIR/source"
FILES=(deepcool-lm deepcool_lm_display.py deepcool_lm_system.py deepcool-lm.service)
trap 'rm -rf "$TEMP_DIR"' EXIT
mkdir "$SOURCE_DIR"

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        cp "$file" "$SOURCE_DIR/$file"
    else
        echo "下载 $file..."
        curl -fsSL "$REPO_URL/$file" -o "$SOURCE_DIR/$file"
    fi
done

if ! python3 -c 'import psutil, usb; from PIL import Image' >/dev/null 2>&1; then
    echo "错误: 缺少 Python 运行依赖 PyUSB、psutil 或 Pillow。" >&2
    echo "请先按照 README.md 安装当前发行版对应的软件包。" >&2
    exit 1
fi

if ! command -v lsusb >/dev/null 2>&1; then
    echo "错误: 缺少 lsusb，请先安装 usbutils。" >&2
    exit 1
fi

if ! lsusb | grep -q "3633:0026"; then
    echo "警告: 未检测到 Deepcool LM 设备 (3633:0026)。"
    read -r -p "仍然继续安装？[y/N] " reply
    if [[ ! $reply =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

if systemctl is-active --quiet deepcool-lm.service 2>/dev/null; then
    systemctl stop deepcool-lm.service
fi

install -Dm755 "$SOURCE_DIR/deepcool-lm" /usr/local/bin/deepcool-lm
install -Dm644 "$SOURCE_DIR/deepcool_lm_display.py" /usr/local/lib/deepcool-lm/deepcool_lm_display.py
install -Dm644 "$SOURCE_DIR/deepcool_lm_system.py" /usr/local/lib/deepcool-lm/deepcool_lm_system.py
sed 's|ExecStart=/usr/bin/deepcool-lm|ExecStart=/usr/local/bin/deepcool-lm|' \
    "$SOURCE_DIR/deepcool-lm.service" > "$TEMP_DIR/deepcool-lm.service"
install -Dm644 "$TEMP_DIR/deepcool-lm.service" /etc/systemd/system/deepcool-lm.service
systemctl daemon-reload

read -r -p "启用开机启动？[Y/n] " reply
if [[ ! $reply =~ ^[Nn]$ ]]; then
    systemctl enable deepcool-lm.service
fi

read -r -p "现在启动服务？[Y/n] " reply
if [[ ! $reply =~ ^[Nn]$ ]]; then
    systemctl start deepcool-lm.service
fi

echo "安装完成。"
echo "监控: sudo deepcool-lm monitor"
echo "纯色: sudo deepcool-lm solid --color 255 0 0"
echo "亮度: sudo deepcool-lm brightness up"
