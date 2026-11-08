#!/usr/bin/env bash
set -euo pipefail

# CPU 检测、版本选择、软件包配对及安装确认统一由 kernel-build 维护。
INSTALLER_URL="https://raw.githubusercontent.com/avsba001/kernel-build/main/install.sh"

main() {
  local tmpdir status

  command -v curl >/dev/null 2>&1 || {
    echo "缺少依赖：curl" >&2
    return 1
  }
  tmpdir="$(mktemp -d)" || return 1
  trap "rm -rf -- $(printf '%q' "$tmpdir")" EXIT

  echo "正在获取 ${INSTALLER_URL}…"
  if ! curl -fL --retry 5 --retry-delay 2 --retry-all-errors \
    --connect-timeout 15 --max-time 120 \
    -o "$tmpdir/install.sh" "$INSTALLER_URL"; then
    echo "下载 XanMod 安装器失败，已停止；未安装任何内核。" >&2
    return 1
  fi
  if [[ ! -s "$tmpdir/install.sh" ]] || ! bash -n "$tmpdir/install.sh"; then
    echo "XanMod 安装器为空或 Bash 语法检查失败，已停止。" >&2
    return 1
  fi

  # 使用独立 Bash，保留终端标准输入和上游的安装前人工确认。
  # 不使用 exec：子进程结束后仍需清理临时目录，并返回原始退出码。
  status=0
  bash "$tmpdir/install.sh" "$@" || status=$?
  return "$status"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
