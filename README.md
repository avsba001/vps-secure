# vps-secure

VPS 安全与网络优化一键工具。`vps-secure.sh` 是主入口脚本，提供交互式菜单，并按需下载和执行各功能脚本。

## 功能菜单

| 选项 | 调用脚本 | 作用 |
| --- | --- | --- |
| 1 | `sshd-secure-setup.sh` | 交互式加固 SSHD，配置端口、root 登录策略、密码登录、转发、加密算法和 KeepAlive。 |
| 2 | `cake.sh` | 配置 CAKE 队列管理，并创建 systemd 服务实现开机自动应用。 |
| 3 | `fail2ban.sh` | 安装并配置 Fail2Ban 与 ipset，对 SSH 爆破进行更强拦截和持久化封禁；可选择启用 Cloudflare ASN ipset 白名单保护，避免误封 Cloudflare IP。 |
| 4 | `xanmod.sh` | 从指定内核仓库选择并安装 XanMod Cloud 精简内核。 |
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
- `xanmod.sh` 安装内核后需要重启系统才能加载新内核，主脚本不提供自动回滚。
- `cloudflare-ssh.sh` 自带回滚保护。应用后请按脚本提示确认 SSH 和网络正常，再执行确认命令保留规则。
- The unified script applies and persists Cloudflare firewall and MSS rules together. If MTU is omitted, it probes IPv4 and IPv6 China-route targets separately; `PMTU_MTU`, `PMTU_IPV4_MTU`, and `PMTU_IPV6_MTU` override detection. `PMTU_FALLBACK_MTU` defaults to 1480 and is reported when probing fails. A systemd repair timer reapplies the hooks about 75 seconds after boot and every minute, covering firewall reloads by 1Panel.
- 中国 IP ICMP 屏蔽已合并到 `cloudflare-ssh.sh`，不再提供独立 `cn-ipset.sh`。
- 部分辅助脚本会检查当前 `iptables` 后端；`cloudflare-ssh.sh` 已恢复为最早版本的 iptables 规则流程，并在此基础上提供可选中国/省份 SSH 白名单。
- 如果 SSH 白名单看起来未生效，可运行菜单 8 检查端口、链挂接、同端口提前放行规则和 ipset 归属；当前已建立的 SSH 连接会被已建立连接规则继续放行，请用新连接验证。
