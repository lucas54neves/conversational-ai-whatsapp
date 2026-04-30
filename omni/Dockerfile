# Omni image — install the CLI via the repo-local installer wrapper.
FROM debian:bookworm-slim

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        nodejs \
        passwd \
        tar \
        unzip \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --uid 1001 --create-home --shell /bin/sh omni || true

USER omni

ENV HOME=/home/omni
ENV PATH=/home/omni/.local/bin:/home/omni/.bun/bin:${PATH}

COPY scripts/omni/install.sh /tmp/omni-install.sh
RUN bash /tmp/omni-install.sh

COPY omni/entrypoint.sh /usr/local/bin/omni-entrypoint
USER root
RUN chmod +x /usr/local/bin/omni-entrypoint /tmp/omni-install.sh

EXPOSE 8882 4222

ENTRYPOINT ["/usr/local/bin/omni-entrypoint"]
