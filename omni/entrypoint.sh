#!/bin/sh
# Fix the persisted config volume ownership before dropping privileges, then
# provision Omni and keep PM2 in the foreground.
set -e

mkdir -p /home/omni/.omni
chown -R omni:omni /home/omni/.omni /home/omni/.bun /home/omni/.local 2>/dev/null || true
export PATH="/home/omni/.local/bin:/home/omni/.bun/bin:$PATH"

exec su omni -s /bin/sh -c "
export PATH=/home/omni/.local/bin:/home/omni/.bun/bin:\$PATH
omni install --port \"${API_PORT:-8882}\" ${OMNI_API_KEY:+--api-key \"$OMNI_API_KEY\"}
omni start
exec pm2 logs --raw
"
