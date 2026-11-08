# vps-secure

VPS 安全与网络优化一键工具。`vps-secure.sh` 是主入口脚本，提供交互式菜单，并按需下载和执行各功能脚本。

## 功能菜单

| 选项 | 调用脚本 | 作用 |
| --- | --- | --- |
| 1 | `sshd-secure-setup.sh` | 交互式加固 SSHD，配置端口、root 登录策略、密码登录、转发、加密算法和 KeepAlive。 |
| 2 | `cake.sh` | 配置 CAKE 队列管理，并创建 systemd 服务实现开机自动应用。 |
| 3 | `fail2ban.sh` | 安装并配置 Fail2Ban 与 ipset，对 SSH 爆破进行更强拦截和持久化封禁；可选择启用 Cloudflare ASN ipset 白名单保护，避免误封 Cloudflare IP。 |
| 4 | `xanmod.sh` | 复用 `avsba001/kernel-build` 的统一安装器，按 CPU 配置选择并安装 XanMod Cloud 精简内核。 |
| 6 | `cloudflare-ssh.sh` | Unified Cloudflare SSH firewall, China ICMP filtering, and IPv4/IPv6 MSS management with shared MTU detection, persistence, and rollback. |
| 7 | Merged into step 6 | `pmtu-mss.sh` remains as a compatibility wrapper to the unified firewall script. |
| 8 | `ssh-whitelist-check.sh` | 检查当前生效的 SSH 白名单链和 ipset 集合，显示 Cloudflare ASN、中国全量或中国省份等 IP 段归属；发现 nft 后端时可选择切换到 iptables-legacy。 |
| 9 | 全部配置脚本 | 按顺序执行配置类功能。 |
| 10 | 主脚本内置 | 从最近备份撤销已支持的修改。 |
| 11 | 主脚本内置 | 卸载本项目创建的配置、服务、辅助脚本和防火墙规则，但保留已安装依赖软件包。 |

## 一键运行

```bash
bash <(curl -sL https://raw.githubusercontent.com/avsba001/vps-secure/refs/heads/main/vps-secure.sh)
```

国内加速：

```bash
bash <(curl -sL https://gh-proxy.com/https://raw.githubusercontent.com/avsba001/vps-secure/refs/heads/main/vps-secure.sh)
```

## 使用说明

- 请使用 `root` 用户运行。
- 主脚本会先检查远程 `VERSION`，发现新版本时自动更新后再继续执行。
- 大部分修改会在 `/var/backups/vps-secure` 下保存最近备份，可通过菜单中的“撤销修改”恢复。
- “卸载脚本配置”用于删除本项目创建的配置和规则，不删除 `fail2ban`、`ufw`、`ipset`、`iptables-persistent` 等依赖软件包。
- `xanmod.sh` 保留菜单 4 和“全部执行”的调用方式，下载并运行 [`kernel-build/main/install.sh`](https://github.com/avsba001/kernel-build/blob/main/install.sh)，不在本仓库重复维护内核选择逻辑。入口需要 `curl`，统一安装器还需要 `python3`、`dpkg`、`uname`，仅支持 x86-64 Debian/Ubuntu（amd64）。
- 统一安装器检测所有 CPU 核心共有的指令集及 Intel/AMD 厂商，匹配 `v2-intel`、`v3-intel`、`v2-amd` 或 `v3-amd`；低于 v2、未知/混合厂商或 CPU 信息不完整时停止。
- 内核系列可选 `latest`（默认）或 `6.12`、`6.18`、`7.3` 等上游支持的 6.x/7.x 系列；按内核版本号选择对应 CPU 配置的最新完整正式发布，仅下载同一 Release 内文件版本完全配对的 image 和 headers，跳过草稿、预发布及不完整发布（可能选择较旧的完整版本）。
- 下载内核包和安装前会展示匹配版本及软件包列表，只有人工确认后才继续。入口下载失败、空文件或 Bash 语法检查失败时直接停止，不回退到旧脚本；临时安装器会在退出时清理。安装内核后需要手动重启系统才能加载新内核，脚本不会自动重启，主脚本不提供自动回滚。

- `cloudflare-ssh.sh` 自带回滚保护。应用后请按脚本提示确认 SSH 和网络正常，再执行确认命令保留规则。
- The unified script applies and persists Cloudflare firewall and MSS rules together. If MTU is omitted, it probes IPv4 and IPv6 China-route targets separately; `PMTU_MTU`, `PMTU_IPV4_MTU`, and `PMTU_IPV6_MTU` override detection. `PMTU_FALLBACK_MTU` defaults to 1480 and is reported when probing fails. A systemd repair timer reapplies the hooks about 75 seconds after boot and every minute, covering firewall reloads by 1Panel.
- 中国 IP ICMP 屏蔽已合并到 `cloudflare-ssh.sh`，不再提供独立 `cn-ipset.sh`。
- 部分辅助脚本会检查当前 `iptables` 后端；`cloudflare-ssh.sh` 已恢复为最早版本的 iptables 规则流程，并在此基础上提供可选中国/省份 SSH 白名单。
- 如果 SSH 白名单看起来未生效，可运行菜单 8 检查端口、链挂接、同端口提前放行规则和 ipset 归属；当前已建立的 SSH 连接会被已建立连接规则继续放行，请用新连接验证。


### XanMod 隔离回归测试

在具备 Bash 和 Python 3 的环境中运行（不会安装内核或重启）：

```bash
python3 tests/test_xanmod.py --installer ../kernel-build/install.sh
```

测试使用指定的统一安装器源码、合成 CPU 信息和模拟 Releases API；入口下载、内核下载、`dpkg`、`sudo`、`uname` 及重启命令均由桩替代。需先将 `avsba001/kernel-build` 检出到相邻目录，或通过 `--installer` 指定其 `install.sh`。测试不访问真实 Releases API，不运行系统包管理器。
