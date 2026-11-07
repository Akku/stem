#!/usr/bin/env bash
# Starts as root only to (a) fix volume ownership, (b) apply the --strict firewall,
# (c) configure git credentials from env (token is never written to the image),
# then drops ALL privileges and runs the command as user "stem".
set -eu
U=stem
mkdir -p /home/$U/work
chown $U:$U /home/$U /home/$U/work 2>/dev/null || true

if [ "${STEM_STRICT:-0}" = 1 ]; then
  ipset create stem_allow hash:net -exist
  ipset flush stem_allow
  add() { for ip in $(dig +short A "$1" | grep -E '^[0-9.]+$'); do ipset add stem_allow "$ip" -exist; done; }
  for d in api.anthropic.com console.anthropic.com claude.ai platform.claude.com statsig.anthropic.com \
           github.com api.github.com codeload.github.com objects.githubusercontent.com raw.githubusercontent.com \
           registry.npmjs.org pypi.org files.pythonhosted.org ${STEM_EXTRA_HOSTS:-}; do add "$d"; done
  # GitHub publishes its git/web ranges (CDN-fronted IPs change); fetched before the firewall closes
  curl -fsS --max-time 10 https://api.github.com/meta 2>/dev/null \
    | jq -r '(.git + .web + .api)[]' 2>/dev/null | grep -v ':' | while read -r r; do ipset add stem_allow "$r" -exist; done || true
  dns=$(awk '/^nameserver/{print $2}' /etc/resolv.conf | grep -E '^[0-9.]+$' || true)
  iptables -F OUTPUT; iptables -P OUTPUT DROP
  iptables -A OUTPUT -o lo -j ACCEPT
  iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
  for n in $dns; do iptables -A OUTPUT -p udp -d "$n" --dport 53 -j ACCEPT; iptables -A OUTPUT -p tcp -d "$n" --dport 53 -j ACCEPT; done
  iptables -A OUTPUT -m set --match-set stem_allow dst -j ACCEPT
  iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited
  echo "[sandbox] strict network: only Claude API, GitHub and npm/PyPI reachable (+ STEM_EXTRA_HOSTS)" >&2
fi

if [ -n "${GH_TOKEN:-}" ]; then
  su -s /bin/sh $U -c "git config --global credential.https://github.com.helper '!f() { echo username=x-access-token; echo password=\$GH_TOKEN; }; f'"
fi
su -s /bin/sh $U -c "git config --global --get user.name >/dev/null || git config --global user.name \"\${GIT_AUTHOR_NAME:-STEM sandbox}\"; git config --global --get user.email >/dev/null || git config --global user.email \"\${GIT_AUTHOR_EMAIL:-sandbox@localhost}\"; git config --global --add safe.directory '*' 2>/dev/null || true"

exec setpriv --reuid=$U --regid=$U --init-groups --bounding-set=-all --inh-caps=-all "$@"
