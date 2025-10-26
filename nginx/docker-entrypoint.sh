#!/bin/sh
set -e

TEMPLATE=/etc/nginx/nginx.conf.template
OUT=/etc/nginx/nginx.conf

# helper: choose primary/backup based on ACTIVE_POOL
# expected env:
#   ACTIVE_POOL (blue|green)
# app hostnames inside compose are app_blue/app_green on default network:
BLUE_HOST=app_blue
GREEN_HOST=app_green
BLUE_PORT=${PORT:-8081}
GREEN_PORT=${PORT:-8082}

render_config() {
  echo "Rendering nginx config from template (ACTIVE_POOL=${ACTIVE_POOL})..."
  if [ "${ACTIVE_POOL}" = "green" ]; then
    PRIMARY_HOST=${GREEN_HOST}
    PRIMARY_PORT=${GREEN_PORT}
    BACKUP_HOST=${BLUE_HOST}
    BACKUP_PORT=${BLUE_PORT}
  else
    # default to blue
    PRIMARY_HOST=${BLUE_HOST}
    PRIMARY_PORT=${BLUE_PORT}
    BACKUP_HOST=${GREEN_HOST}
    BACKUP_PORT=${GREEN_PORT}
  fi

  # export values for envsubst
  export PRIMARY_HOST PRIMARY_PORT BACKUP_HOST BACKUP_PORT
  # use envsubst to expand placeholders in template
  /usr/bin/envsubst '${PRIMARY_HOST} ${PRIMARY_PORT} ${BACKUP_HOST} ${BACKUP_PORT}' < "${TEMPLATE}" > "${OUT}"
  echo "Rendered ${OUT}:"
  cat "${OUT}" | sed -n '1,120p'
}

reload_and_report() {
  render_config
  nginx -s reload || { echo "nginx -s reload failed; trying to start nginx"; nginx -g 'daemon off;' & }
}

# generate initial config
render_config

# create a helper reload script inside container for manual toggles
cat > /reload_nginx.sh <<'EOF'
#!/bin/sh
set -e
echo "Reload helper: re-rendering config and reloading nginx..."
/usr/bin/envsubst '${PRIMARY_HOST} ${PRIMARY_PORT} ${BACKUP_HOST} ${BACKUP_PORT}' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf
nginx -s reload
EOF
chmod +x /reload_nginx.sh

# start nginx in foreground
echo "Starting nginx..."
nginx -g 'daemon off;'
