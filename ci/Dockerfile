# CI on Coolify: building this image is the check, so a failed build is a failed check and Coolify sends the alert.
# Replaces the GitHub Actions workflow. Build context: the repository root.
FROM ghcr.io/home-assistant/hassfest:latest AS check
WORKDIR /github/workspace
COPY beacon.py ./
COPY custom_components ./custom_components
RUN python3 -m py_compile beacon.py custom_components/weather_beacon/*.py \
 && python3 -I custom_components/weather_beacon/looks.py \
 && /usr/src/homeassistant/script/hassfest/docker/entrypoint.sh

# Coolify wants a running container; this one only records which version passed.
FROM busybox:1.37
# the COPY makes the check stage a dependency, so BuildKit can't skip it
COPY --from=check /github/workspace/custom_components/weather_beacon/manifest.json /passed/manifest.json
CMD ["sleep", "infinity"]
