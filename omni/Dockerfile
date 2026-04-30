# Omni image — wraps @automagik/omni since no official image is published.
#
# KNOWN ISSUE: Omni's bundled Postgres (pgserve) refuses to run as root
# (initdb safety check). The bun image runs as root by default, and
# attempts to switch to a non-root user broke `bun add -g` permissions.
# `omni install --database-url` saves an external URL into config.json
# but the omni-api PM2 process still tries to start pgserve at boot, so
# external Postgres did not work either. This image therefore builds and
# runs `omni install`, but `omni-api` will sit in PM2 "waiting restart"
# until one of the following is resolved:
#   - Run Omni on the host (as the original nutrition design spec
#     prescribed) and reach it from compose via host.docker.internal.
#   - Build a custom non-root variant where bun's globals land under the
#     non-root user's home and pgserve initdb succeeds.
#   - Force Omni to skip pgserve entirely (no documented flag exists).
#
# See docs/specs/2026-04-30-reproducible-setup-design.md §4.1 risks table.

FROM oven/bun:1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN bun add -g @automagik/omni pm2

COPY entrypoint.sh /usr/local/bin/omni-entrypoint
RUN chmod +x /usr/local/bin/omni-entrypoint

EXPOSE 8882 4222

ENTRYPOINT ["/usr/local/bin/omni-entrypoint"]
