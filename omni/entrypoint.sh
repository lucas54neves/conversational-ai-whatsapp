#!/bin/sh
# Fix the persisted config volume ownership before dropping privileges, then
# provision Omni and keep PM2 in the foreground.
set -e

mkdir -p /home/omni/.omni
mkdir -p /home/omni/.pm2
rm -f /home/omni/.pm2/rpc.sock /home/omni/.pm2/pub.sock /home/omni/.pm2/pm2.pid 2>/dev/null || true
chown -R omni:omni /home/omni/.omni /home/omni/.bun /home/omni/.local /home/omni/.pm2 2>/dev/null || true
export PATH="/home/omni/.local/bin:/home/omni/.bun/bin:$PATH"
export PM2_HOME="/home/omni/.pm2"

exec su omni -s /bin/sh -c "
export PATH=/home/omni/.local/bin:/home/omni/.bun/bin:\$PATH
export PM2_HOME=/home/omni/.pm2
omni install --port \"${API_PORT:-8882}\" ${OMNI_API_KEY:+--api-key \"$OMNI_API_KEY\"}
omni start
exec pm2 logs --raw
"
