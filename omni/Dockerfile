# Omni image — wraps @automagik/omni since no official image is published.
#
# Architecture choice: Postgres and NATS are externalized into sibling
# compose services (`omni-postgres`, `nats`) instead of embedded via
# `omni install`. `omni install` is an interactive PM2 wizard with no
# documented non-interactive flag, which makes it unsuitable for a Docker
# build. Externalizing matches Omni's documented `DATABASE_URL` and
# `NATS_URL` env vars and removes the PM2-in-container anti-pattern.
#
# See docs/specs/2026-04-30-reproducible-setup-design.md §4.1.

FROM oven/bun:1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN bun add -g @automagik/omni

EXPOSE 8882

# Foreground entrypoint — omni reads DATABASE_URL, NATS_URL, OMNI_API_KEY,
# and API_PORT from the environment. The exact subcommand for "run the
# API server in foreground without PM2" is not documented on Omni's
# README; `omni` (the CLI entrypoint) is the closest documented path.
# Verify against `omni --help` before relying on this for production.
CMD ["omni"]
