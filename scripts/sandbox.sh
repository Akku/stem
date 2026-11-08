#!/usr/bin/env bash
# STEM Docker sandbox: Claude Code runs entirely inside a container; the project lives only in a Docker volume.
# Needs only Docker (Mac, Linux, WSL2). Design: docs of the STEM development harness (doc-6).
#
#   sandbox.sh new <name> [--repo URL]   clone the STEM template (or your repo) into a new sandbox and start Claude
#   sandbox.sh start [name]              start/resume the sandbox (default name: stem)
#   sandbox.sh stop [name]               stop the container (volumes stay)
#   sandbox.sh export [name] [dir]       copy the project to the host: <dir>/<name>.tar.gz and <name>.bundle (git);
#                                        default dir: $STEM_SANDBOX_EXPORT_DIR or ~/stem-sandbox-exports (never the current folder)
#   sandbox.sh reset [name]              DELETE the sandbox volumes (asks first); login and project are gone
#   sandbox.sh list                      list sandboxes
# Options for new/start: --strict (only Claude API, GitHub, npm/PyPI reachable), --port N (repeatable, host:container same N),
#   --ubuntu TAG (default: newest LTS = ubuntu:latest, chosen at first build, stored with the sandbox),
#   --allow HOST (repeatable, extra host in --strict mode), --shell (bash instead of claude), -- CMD... (run CMD instead).
# Credentials: ANTHROPIC_API_KEY and GH_TOKEN (scoped to ONE repo) are passed from your environment by name only;
#   never stored in the image or a volume. Without ANTHROPIC_API_KEY, log in with your account inside (/login); it persists in the volume.
#   The login belongs to ONE sandbox (own volume): a new sandbox asks for /login again. Use one sandbox for several projects
#   (git clone inside it) or set ANTHROPIC_API_KEY to avoid repeated logins. The image contains git and gh (GitHub CLI; uses GH_TOKEN).
set -euo pipefail
TEMPLATE_URL=https://github.com/Akku/stem.git
RAW=https://raw.githubusercontent.com/Akku/stem/main/docker
IMG_REV=2   # raise when docker/Dockerfile changes, so existing Ubuntu images are rebuilt
here=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
die() { echo "sandbox: $*" >&2; exit 1; }
command -v docker >/dev/null || die "Docker not found. Install Docker Desktop (Mac/Windows+WSL2) or Docker Engine (Linux)."
docker info >/dev/null 2>&1 || die "Docker is installed but not running. Start it and retry."

cmd=${1:-}; [ $# -gt 0 ] && shift
name=stem; strict=0; ubuntu=; repo=; ports=(); allow=(); shellmode=0; pos=()
extra=()
while [ $# -gt 0 ]; do
  case $1 in
    --) shift; extra=("$@"); break;;
    --strict) strict=1;; --shell) shellmode=1;;
    --port) ports+=("${2:?--port needs a number}"); shift;;
    --ubuntu) ubuntu=${2:?--ubuntu needs a tag}; shift;;
    --repo) repo=${2:?--repo needs a URL}; shift;;
    --allow) allow+=("${2:?--allow needs a host}"); shift;;
    -*) die "unknown option $1";;
    *) pos+=("$1");;
  esac; shift
done
[ ${#pos[@]} -gt 0 ] && name=${pos[0]}
[[ $name =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || die "invalid name '$name' (letters, digits, _ . -)"
home_vol="stem-sbx-$name"; ctr="stem-sbx-$name"

find_docker_dir() {  # docker/ next to scripts/, or downloaded (standalone use)
  if [ -f "$here/../docker/Dockerfile" ]; then dockerdir="$here/../docker"; return; fi
  dockerdir=$(mktemp -d); command -v curl >/dev/null || die "curl needed to fetch docker/ files"
  for f in Dockerfile entrypoint.sh; do curl -fsSL "$RAW/$f" -o "$dockerdir/$f" || die "cannot download $RAW/$f"; done
}
vol_label() { docker volume inspect -f "{{ index .Labels \"$2\" }}" "$1" 2>/dev/null || true; }
build_image() {  # $1 = ubuntu version label (e.g. 24.04); image tag is stem-sandbox:<version>
  local tag=$1 ver
  if [ "$tag" = latest ]; then docker pull -q ubuntu:latest >/dev/null; else docker pull -q "ubuntu:$tag" >/dev/null || die "ubuntu:$tag not found"; fi
  ver=$(docker run --rm "ubuntu:$tag" sh -c '. /etc/os-release; echo $VERSION_ID')
  img="stem-sandbox:$ver-$IMG_REV"; ubuntu_ver=$ver
  if ! docker image inspect "$img" >/dev/null 2>&1; then
    find_docker_dir; echo "[sandbox] building image $img (Ubuntu $ver; first use takes a few minutes)..." >&2
    docker build -q --build-arg "UBUNTU_TAG=$ver" -t "$img" "$dockerdir" >/dev/null || die "image build failed"
  fi
}
run_args() {  # common docker run args
  args=($tty --name "$ctr" -v "$home_vol:/home/stem" -e GH_TOKEN -e ANTHROPIC_API_KEY -e "STEM_STRICT=$strict" --cap-drop ALL
        --cap-add SETUID --cap-add SETGID --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add SETPCAP --cap-add FOWNER
        --security-opt no-new-privileges:false)
  [ $strict = 1 ] && args+=(--cap-add NET_ADMIN --cap-add NET_RAW)
  [ ${#allow[@]} -gt 0 ] && args+=(-e "STEM_EXTRA_HOSTS=${allow[*]}")
  for p in "${ports[@]:-}"; do [ -n "$p" ] && args+=(-p "127.0.0.1:$p:$p"); done
  return 0
}
start_container() {
  if docker ps -q -f "name=^$ctr$" | grep -q .; then
    echo "[sandbox] already running; attaching a second session" >&2
    exec docker exec $tty -u stem -w /home/stem/work "$ctr" "${startcmd[@]}"
  fi
  docker rm "$ctr" >/dev/null 2>&1 || true
  local stored; stored=$(vol_label "$home_vol" stem.ubuntu); [ -z "$ubuntu" ] && ubuntu=${stored:-latest}
  build_image "$ubuntu"
  [ -z "$stored" ] && { docker volume rm "$home_vol" >/dev/null 2>&1 || true; docker volume create --label "stem.ubuntu=$ubuntu_ver" "$home_vol" >/dev/null; }
  [ -n "$stored" ] && [ "$stored" != "$ubuntu_ver" ] && echo "[sandbox] note: sandbox was created with Ubuntu $stored; now using $ubuntu_ver" >&2
  echo "[sandbox] Ubuntu $ubuntu_ver | network: $([ $strict = 1 ] && echo strict || echo 'open outbound, nothing inbound') | ports: ${ports[*]:-none}" >&2
  [ -z "${ANTHROPIC_API_KEY:-}" ] && echo "[sandbox] no ANTHROPIC_API_KEY set: use /login inside (account login, kept in the sandbox volume)" >&2
  run_args
  if [ -n "${cloneurl:-}" ]; then
    # clone as part of the first start, before Claude runs
    startcmd=(bash -c '[ -d .git ] || git clone "$0" . || exit 1; exec "$@"' "$cloneurl" "${startcmd[@]}")
  fi
  exec docker run "${args[@]}" "$img" "${startcmd[@]}"
}
tty=-i; [ -t 0 ] && tty=-it
startcmd=(claude); [ $shellmode = 1 ] && startcmd=(bash); [ ${#extra[@]} -gt 0 ] && startcmd=("${extra[@]}")

case $cmd in
  new)
    [ ${#pos[@]} -ge 1 ] || die "usage: sandbox.sh new <name> [--repo URL]"
    docker volume inspect "$home_vol" >/dev/null 2>&1 && die "sandbox '$name' exists (use start, or reset to delete it)"
    cloneurl=${repo:-$TEMPLATE_URL}; start_container;;
  start)
    if ! docker volume inspect "$home_vol" >/dev/null 2>&1; then
      [ -n "$repo" ] && cloneurl=$repo || echo "[sandbox] new empty sandbox '$name' (use 'new' to clone a repo)" >&2
    fi
    start_container;;
  stop) docker stop "$ctr" >/dev/null 2>&1 && echo "stopped $name" || echo "$name is not running";;
  export)
    docker volume inspect "$home_vol" >/dev/null 2>&1 || die "no sandbox '$name'"
    out=${pos[1]:-${STEM_SANDBOX_EXPORT_DIR:-$HOME/stem-sandbox-exports}}; mkdir -p "$out"; out=$(cd "$out" && pwd); ver=$(vol_label "$home_vol" stem.ubuntu); img="stem-sandbox:${ver:-}-$IMG_REV"
    docker image inspect "$img" >/dev/null 2>&1 || img=$(docker images --format '{{.Repository}}:{{.Tag}}' stem-sandbox | head -1)
    [ -n "$img" ] || die "no sandbox image found; run start once"
    docker run --rm --entrypoint bash -v "$home_vol:/home/stem:ro" -v "$out:/out" "$img" -c \
      "cd /home/stem/work && tar czf /out/$name.tar.gz . && { git -c safe.directory='*' bundle create /out/$name.bundle --all 2>/dev/null || echo 'no git commits: bundle skipped'; }"
    echo "exported to $out/$name.tar.gz (working tree incl. .git) and $out/$name.bundle (git history, if any)";;
  reset)
    read -r -p "Delete sandbox '$name' (project, login, history; cannot be undone)? Export first if unsure. [y/N] " a
    [ "$a" = y ] || [ "$a" = Y ] || die "cancelled"
    docker rm -f "$ctr" >/dev/null 2>&1 || true; docker volume rm "$home_vol" >/dev/null && echo "deleted $name";;
  list)
    docker volume ls -q -f name='^stem-sbx-' | sed 's/^stem-sbx-//' | while read -r n; do
      s=stopped; docker ps -q -f "name=^stem-sbx-$n$" | grep -q . && s=running
      echo "$n  ubuntu=$(vol_label "stem-sbx-$n" stem.ubuntu)  $s"; done;;
  *) sed -n '2,18p' "${BASH_SOURCE[0]:-$0}" | sed 's/^# \{0,1\}//'; [ -z "$cmd" ] || exit 2;;
esac
