#!/usr/bin/env bash
set -euo pipefail

script="cloudflare-ssh.sh"
grep -F 'CHAIN_CN_TCP_V4="CN_TCP_DROP"' "$script" >/dev/null
grep -F 'CHAIN_CN_TCP_V6="CN_TCP_DROP_V6"' "$script" >/dev/null
grep -F 'run iptables -A "$CHAIN_CN_TCP_V4" -p tcp --dport "$SSH_PORT" -j "$CHAIN_V4"' "$script" >/dev/null
grep -F 'run iptables -A "$CHAIN_CN_TCP_V4" -p tcp --dport 443 -j RETURN' "$script" >/dev/null
grep -F 'run iptables -A "$CHAIN_CN_TCP_V4" -m set --match-set "$IPSET_CN4" src -j DROP' "$script" >/dev/null
grep -F 'run ip6tables -A "$CHAIN_CN_TCP_V6" -p tcp --dport "$SSH_PORT" -j "$CHAIN_V6"' "$script" >/dev/null
grep -F 'run ip6tables -A "$CHAIN_CN_TCP_V6" -p tcp --dport 443 -j RETURN' "$script" >/dev/null
grep -F 'run ip6tables -A "$CHAIN_CN_TCP_V6" -m set --match-set "$IPSET_CN6" src -j DROP' "$script" >/dev/null
grep -F 'ensure_jump iptables "$CHAIN_CN_TCP_V4" tcp 3' "$script" >/dev/null
grep -F 'ensure_jump ip6tables "$CHAIN_CN_TCP_V6" tcp 3' "$script" >/dev/null
grep -F 'remove_input_jumps_to_chain iptables "$CHAIN_CN_TCP_V4"' "$script" >/dev/null
grep -F 'remove_input_jumps_to_chain ip6tables "$CHAIN_CN_TCP_V6"' "$script" >/dev/null
printf 'China TCP guard contract: verified\n'
