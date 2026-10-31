#!/bin/bash
# 一键配置 CAKE 队列 + systemd 服务
# 完整模式：带宽限制、RTT、NAT、diffserv3 等
# 简洁模式：带宽限制、RTT、ethernet、besteffort

set -e

SERVICE_FILE="/etc/systemd/system/set-cake.service"
SCRIPT_FILE="/usr/local/bin/set-cake.sh"

# 检查 root 权限
if [[ "$EUID" -ne 0 ]]; then
    echo "请使用 root 权限运行此脚本。"
    exit 1
fi

# 检查必要命令
for CMD in tc ip systemctl; do
    if ! command -v "$CMD" >/dev/null 2>&1; then
        echo "缺少必要命令：$CMD，请先安装。"
        exit 1
    fi
done

echo "=== CAKE 队列一键配置脚本 ==="

# 交互选择配置模式
echo ""
echo "请选择配置模式："
echo "  1) 完整模式：带宽限制、RTT、NAT、diffserv3 等"
echo "  2) 简洁模式：带宽限制 + RTT + ethernet + besteffort"
read -rp "请输入选项 [默认: 1]: " MODE_INPUT

case "$MODE_INPUT" in
    1|"")
        MODE="full"
        ;;
    2)
        MODE="simple"
        ;;
    *)
        echo "输入无效，使用完整模式"
        MODE="full"
        ;;
esac

# 交互输入网卡接口
read -rp "请输入要配置的网卡接口 [默认: eth0]: " IFACE_INPUT
IFACE="${IFACE_INPUT:-eth0}"

if ! ip link show dev "$IFACE" >/dev/null 2>&1; then
    echo "网卡接口不存在：$IFACE"
    exit 1
fi

# 完整模式下输入 NAT 设置
NAT_MODE="nonat"

if [[ "$MODE" == "full" ]]; then
    read -rp "请确认是否为 NAT 机器？(y=是 / n=不是) [默认: n]: " NAT_CHOICE

    case "$NAT_CHOICE" in
        [Yy])
            NAT_MODE="nat"
            ;;
        [Nn]|"")
            NAT_MODE="nonat"
            ;;
        *)
            echo "输入无效，默认使用 nonat"
            NAT_MODE="nonat"
            ;;
    esac
fi

# 两种模式均交互输入 RTT
read -rp "请输入网络 RTT (仅输入正整数，单位 ms) [默认: 100]: " RTT_INPUT
RTT_INPUT="${RTT_INPUT:-100}"

if [[ "$RTT_INPUT" =~ ^[0-9]+$ && "$RTT_INPUT" =~ [1-9] ]]; then
    RTT="${RTT_INPUT}ms"
else
    echo "输入无效，使用默认 100ms"
    RTT="100ms"
fi

# 两种模式均交互输入带宽上限
echo ""
echo "带宽单位支持：mbit / gbit"
read -rp "请输入带宽数值 (仅输入正整数) [默认: 600]: " BW_INPUT
read -rp "请选择带宽单位 (m=mbit / g=gbit) [默认: m]: " BW_UNIT

BW_INPUT="${BW_INPUT:-600}"

if [[ ! "$BW_INPUT" =~ ^[0-9]+$ || ! "$BW_INPUT" =~ [1-9] ]]; then
    echo "输入无效，使用默认 600mbit"
    BW="600mbit"
else
    case "$BW_UNIT" in
        [Gg])
            BW="${BW_INPUT}gbit"
            ;;
        [Mm]|"")
            BW="${BW_INPUT}mbit"
            ;;
        *)
            echo "单位输入无效，使用默认 mbit"
            BW="${BW_INPUT}mbit"
            ;;
    esac
fi

# 构造 CAKE 命令，数组保证参数正确传递
# replace 可直接替换现有根队列，无需先删除
CAKE_CMD=(
    tc qdisc replace dev "$IFACE" root cake
    bandwidth "$BW"
    rtt "$RTT"
)

if [[ "$MODE" == "simple" ]]; then
    CAKE_CMD+=(
        ethernet
        besteffort
    )
else
    CAKE_CMD+=(
        diffserv3
        "$NAT_MODE"
        triple-isolate
        ack-filter
        split-gso
        ethernet
        overhead 0
        mpu 64
        wash
    )
fi

# 显示配置
echo ""
echo "====== 配置信息确认 ======"
if [[ "$MODE" == "simple" ]]; then
    echo "  配置模式 : 简洁模式"
else
    echo "  配置模式 : 完整模式"
    echo "  NAT 模式 : $NAT_MODE"
fi
echo "  网卡接口 : $IFACE"
echo "  带宽上限 : $BW"
echo "  RTT      : $RTT"
echo "  执行命令 :"
printf ' %q' "${CAKE_CMD[@]}"
printf '\n'
echo "=========================="
echo ""

# 最终确认
read -rp "是否确认应用该配置？(y=确认 / n=取消): " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "已取消配置，未做任何更改。"
    exit 1
fi

# 获取 tc 的绝对路径，供 systemd 启动脚本使用
TC_BIN="$(command -v tc)"
CAKE_CMD[0]="$TC_BIN"

# 生成 /usr/local/bin/set-cake.sh
# %q 对参数进行 Bash 转义
mkdir -p /usr/local/bin

{
    printf '#!/bin/bash\n'
    printf 'set -e\n\n'
    printf '%q ' "${CAKE_CMD[@]}"
    printf '\n'
} > "$SCRIPT_FILE"

chmod 0755 "$SCRIPT_FILE"

# 生成 systemd service 文件
cat > "$SERVICE_FILE" <<EOL
[Unit]
Description=Set CAKE Qdisc
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$SCRIPT_FILE
RemainAfterExit=true

[Install]
WantedBy=multi-user.target
EOL

chmod 0644 "$SERVICE_FILE"

# 应用 systemd
systemctl daemon-reload
systemctl enable set-cake.service

if ! systemctl restart set-cake.service; then
    echo ""
    echo "CAKE 配置失败，请查看日志："
    echo "  journalctl -u set-cake.service -n 50 --no-pager"
    exit 1
fi

echo ""
echo "✅ CAKE 已配置并开机自启"
echo "可用命令："
echo "  systemctl status set-cake.service  # 查看运行状态"
echo "  tc -s qdisc show dev \"$IFACE\"     # 查看 CAKE 队列统计"
echo "  journalctl -u set-cake.service -n 50 --no-pager  # 查看日志"
