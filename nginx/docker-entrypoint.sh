# #!/bin/sh
# set -e

# TEMPLATE=/etc/nginx/nginx.conf.template
# OUT=/etc/nginx/nginx.conf

# # helper: choose primary/backup based on ACTIVE_POOL
# # expected env:
# #   ACTIVE_POOL (blue|green)
# # app hostnames inside compose are app_blue/app_green on default network:
# BLUE_HOST=app_blue
# GREEN_HOST=app_green
# BLUE_PORT=${PORT:-8081}
# GREEN_PORT=${PORT:-8082}

# render_config() {
#   echo "Rendering nginx config from template (ACTIVE_POOL=${ACTIVE_POOL})..."
#   if [ "${ACTIVE_POOL}" = "green" ]; then
#     PRIMARY_HOST=${GREEN_HOST}
#     PRIMARY_PORT=${GREEN_PORT}
#     BACKUP_HOST=${BLUE_HOST}
#     BACKUP_PORT=${BLUE_PORT}
#   else
#     # default to blue
#     PRIMARY_HOST=${BLUE_HOST}
#     PRIMARY_PORT=${BLUE_PORT}
#     BACKUP_HOST=${GREEN_HOST}
#     BACKUP_PORT=${GREEN_PORT}
#   fi

#   # export values for envsubst
#   export PRIMARY_HOST PRIMARY_PORT BACKUP_HOST BACKUP_PORT
#   # use envsubst to expand placeholders in template
#   /usr/bin/envsubst '${PRIMARY_HOST} ${PRIMARY_PORT} ${BACKUP_HOST} ${BACKUP_PORT}' < "${TEMPLATE}" > "${OUT}"
#   echo "Rendered ${OUT}:"
#   cat "${OUT}" | sed -n '1,120p'
# }

# reload_and_report() {
#   render_config
#   nginx -s reload || { echo "nginx -s reload failed; trying to start nginx"; nginx -g 'daemon off;' & }
# }

# # generate initial config
# render_config

# # create a helper reload script inside container for manual toggles
# cat > /reload_nginx.sh <<'EOF'
# #!/bin/sh
# set -e
# echo "Reload helper: re-rendering config and reloading nginx..."
# /usr/bin/envsubst '${PRIMARY_HOST} ${PRIMARY_PORT} ${BACKUP_HOST} ${BACKUP_PORT}' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf
# nginx -s reload
# EOF
# chmod +x /reload_nginx.sh

# # start nginx in foreground
# echo "Starting nginx..."
# nginx -g 'daemon off;'


#!/bin/sh
set -e

TEMPLATE=/etc/nginx/nginx.conf.template
OUT=/etc/nginx/nginx.conf

# CORRECTION: Fixed port assignments
# LEARNING NOTE: 8081 and 8082 are HOST ports (outside Docker)
# Inside Docker, both apps listen on port 3000
# The docker-compose maps 8081:3000 for blue and 8082:3000 for green
BLUE_HOST=app_blue
GREEN_HOST=app_green
BLUE_PORT=3000   # FIXED: Was 8081, should be 3000 (container port)
GREEN_PORT=3000  # FIXED: Was 8082, should be 3000 (container port)

render_config() {
  echo "Rendering nginx config from template (ACTIVE_POOL=${ACTIVE_POOL})..."
  
  # LEARNING NOTE: This logic determines which pool is primary vs backup
  # based on the ACTIVE_POOL environment variable
  if [ "${ACTIVE_POOL}" = "green" ]; then
    PRIMARY_HOST=${GREEN_HOST}
    PRIMARY_PORT=${GREEN_PORT}
    BACKUP_HOST=${BLUE_HOST}
    BACKUP_PORT=${BLUE_PORT}
    echo "Active: GREEN (app_green:3000), Backup: BLUE (app_blue:3000)"
  else
    # Default to blue as primary
    PRIMARY_HOST=${BLUE_HOST}
    PRIMARY_PORT=${BLUE_PORT}
    BACKUP_HOST=${GREEN_HOST}
    BACKUP_PORT=${GREEN_PORT}
    echo "Active: BLUE (app_blue:3000), Backup: GREEN (app_green:3000)"
  fi

  # Export variables so envsubst can use them
  export PRIMARY_HOST PRIMARY_PORT BACKUP_HOST BACKUP_PORT
  
  # CORRECTION: Template now uses ${PRIMARY_HOST} ${PRIMARY_PORT} etc.
  # This matches what we export above
  envsubst '${PRIMARY_HOST} ${PRIMARY_PORT} ${BACKUP_HOST} ${BACKUP_PORT}' < "${TEMPLATE}" > "${OUT}"
  
  echo "Generated nginx config:"
  cat "${OUT}" | head -40
}

# Generate initial config
render_config

# LEARNING NOTE: This helper allows manual pool switching after container starts
# Usage: docker exec bg_nginx /reload_nginx.sh
cat > /reload_nginx.sh <<'EOF'
#!/bin/sh
set -e
echo "Reloading with current ACTIVE_POOL=${ACTIVE_POOL}..."
# Re-export variables based on current ACTIVE_POOL
if [ "${ACTIVE_POOL}" = "green" ]; then
  export PRIMARY_HOST=app_green
  export PRIMARY_PORT=3000
  export BACKUP_HOST=app_blue
  export BACKUP_PORT=3000
else
  export PRIMARY_HOST=app_blue
  export PRIMARY_PORT=3000
  export BACKUP_HOST=app_green
  export BACKUP_PORT=3000
fi
envsubst '${PRIMARY_HOST} ${PRIMARY_PORT} ${BACKUP_HOST} ${BACKUP_PORT}' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

nginx -s reload
echo "Reload complete!"
EOF
chmod +x /reload_nginx.sh

# Start nginx in foreground (required for Docker containers)
echo "Starting nginx..."
exec nginx -g 'daemon off;'