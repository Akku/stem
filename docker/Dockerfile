# STEM sandbox image: Claude Code runs entirely inside the container (doc-6).
# Built by scripts/sandbox.sh; UBUNTU_TAG is chosen there (newest LTS by default).
ARG UBUNTU_TAG=latest
FROM ubuntu:${UBUNTU_TAG}
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      git python3 nodejs npm ripgrep curl ca-certificates jq less \
      iptables ipset dnsutils iproute2 util-linux \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code backlog.md && npm cache clean --force
# Non-root user "stem" with fixed UID 1000 (Ubuntu 24.04+ ships a user "ubuntu" with that UID)
RUN (userdel -r ubuntu 2>/dev/null || true) \
    && useradd -m -u 1000 -s /bin/bash stem
COPY entrypoint.sh /usr/local/bin/stem-entrypoint
RUN chmod 755 /usr/local/bin/stem-entrypoint
ENV HOME=/home/stem
WORKDIR /home/stem/work
ENTRYPOINT ["/usr/local/bin/stem-entrypoint"]
CMD ["claude"]
