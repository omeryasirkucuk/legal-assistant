#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
compose=(docker compose --env-file deploy/.env -f deploy/compose.yml)

if [[ $# -gt 1 || ( $# -eq 1 && $1 != --cleanup-only ) ]]; then
    echo "Usage: sudo bash deploy/release.sh [--cleanup-only]" >&2
    exit 2
fi

# Serialize the build, activation and cleanup on the production host.
exec 9>/run/lock/legal-folonto-release.lock
flock -x 9

docker buildx version >/dev/null

running_image() {
    local container
    container=$("${compose[@]}" ps --status running -q "$1")
    if [[ -n $container ]]; then
        docker inspect --format '{{.Image}}' "$container"
    fi
}

probe() {
    local -a args=("$@")
    curl --fail --silent --show-error --max-time 10 "${args[@]}" >/dev/null
}

verify() {
    probe --retry 12 --retry-delay 5 --retry-connrefused \
        -H 'Host: legal.folonto.com' http://127.0.0.1:3100/api/health
    probe --retry 12 --retry-delay 5 https://legal.folonto.com/api/health
    probe --retry 12 --retry-delay 5 https://legal.folonto.com/api/ready
    probe --retry 12 --retry-delay 5 https://legal.folonto.com/login
}

cleanup_images() {
    local containers container image images ref service tag
    local -A keep=()

    # Protect images referenced by any container, including stopped containers.
    containers=$(docker ps -aq)
    while IFS= read -r container; do
        [[ -n $container ]] || continue
        image=$(docker inspect --format '{{.Image}}' "$container")
        keep[$image]=1
    done <<< "$containers"
    for service in api web; do
        for tag in latest rollback release-previous; do
            if image=$(docker image inspect --format '{{.Id}}' "legal-folonto-$service:$tag" 2>/dev/null); then
                keep[$image]=1
            fi
        done
    done

    images=$(docker image ls --no-trunc --format '{{.ID}} {{.Repository}}:{{.Tag}}')
    while read -r image ref; do
        case "$ref" in
            legal-folonto-api:*|legal-folonto-web:*|legal-folonto-mobile-build-api:*|legal-folonto-mobile-build-web:*|legal-folonto-rollback-*-api:*|legal-folonto-rollback-*-web:*)
                if [[ ! ${keep[$image]+present} ]]; then
                    docker image rm "$ref"
                fi
                ;;
        esac
    done <<< "$images"

    docker image prune --force --filter label=com.docker.compose.project=legal-folonto
    # The default builder cache is shared. Prune unused cache and target 1 GB of total cache.
    docker buildx prune --builder default --all --force --max-used-space 1GB
    df -h /
}

if [[ ${1:-} == --cleanup-only ]]; then
    verify
    cleanup_images
    exit
fi

previous_api=$(running_image api)
previous_web=$(running_image web)
if [[ -n $previous_api && -n $previous_web ]] &&
    probe https://legal.folonto.com/api/ready; then
    # Pin the serving pair before build moves the latest tags. This also keeps a
    # recovery pair available when build, migration or verification fails.
    docker image tag "$previous_api" legal-folonto-api:release-previous
    docker image tag "$previous_web" legal-folonto-web:release-previous
fi

"${compose[@]}" build --builder default
"${compose[@]}" up -d --wait db
"${compose[@]}" run --rm api alembic upgrade head
"${compose[@]}" up -d --wait
probe --retry 12 --retry-delay 5 --retry-connrefused \
    -H 'Host: legal.folonto.com' http://127.0.0.1:3100/api/health
if ! probe -H 'Host: legal.folonto.com' http://127.0.0.1:3100/api/ready; then
    "${compose[@]}" run --rm api python -m legal_api.corpus.statutes
fi
verify

# A no-op rebuild should retain the existing, distinct rollback pair.
previous_api=$(docker image ls --no-trunc --format '{{.ID}}' legal-folonto-api:release-previous)
previous_web=$(docker image ls --no-trunc --format '{{.ID}}' legal-folonto-web:release-previous)
if [[ -n $previous_api && -n $previous_web ]]; then
    live_api=$(running_image api)
    live_web=$(running_image web)
    if [[ $previous_api != "$live_api" || $previous_web != "$live_web" ]]; then
        docker image tag "$previous_api" legal-folonto-api:rollback
        docker image tag "$previous_web" legal-folonto-web:rollback
    fi
    docker image rm legal-folonto-api:release-previous legal-folonto-web:release-previous
fi
cleanup_images
