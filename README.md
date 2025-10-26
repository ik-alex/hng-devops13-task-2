# How to run and verify

# Setup

1. in the .env file fill in BLUE_IMAGE and GREEN_IMAGE and RELEASE_IDs
2. docker compose up -d

# Ports

- Nginx entry: http://localhost:8080
- Blue direct (for chaos): http://localhost:8081
- Green direct: http://localhost:8082

# Normal baseline check (Blue active by default)

curl -i http://localhost:8080/version

# Expect 200 and headers:

# X-App-Pool: blue

# X-Release-Id: <RELEASE_ID_BLUE>

# Start chaos on Blue (grader uses this)

curl -X POST "http://localhost:8081/chaos/start?mode=error"

# After the app starts failing, next request should succeed from green (within seconds)

curl -i http://localhost:8080/version

# Expect 200 and headers:

# X-App-Pool: green

# X-Release-Id: <RELEASE_ID_GREEN>

# Stop chaos:

curl -X POST "http://localhost:8081/chaos/stop"

# Manual toggle of ACTIVE_POOL:

# If you change .env ACTIVE_POOL, restart the nginx container so it gets the updated env:

docker compose restart nginx

# or

docker compose up -d --force-recreate nginx

# Alternatively, within the running container you can re-render/reload if you updated the template or environment

# (Note: changing host .env doesn't change container env. To pick a new ACTIVE_POOL the container must be restarted.)

docker exec bg_nginx /reload_nginx.sh
