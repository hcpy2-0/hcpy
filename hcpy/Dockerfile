ARG BUILD_FROM
FROM $BUILD_FROM

LABEL \
  io.hass.version="VERSION" \
  io.hass.type="addon" \
  io.hass.arch="armhf|aarch64|i386|amd64|armv7"

RUN apk add --no-cache \
    python3 py3-pip py3-cryptography py3-cffi \
    bash curl jq \
    openssl-dev gcc musl-dev python3-dev libffi-dev

WORKDIR /app

COPY requirements.txt /app/
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt

COPY requirements-extra.txt /app/
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements-extra.txt

# Build-Dependencies entfernen
RUN apk del --no-cache gcc musl-dev python3-dev libffi-dev openssl-dev

# Original hcpy Quellcode
COPY hc-login.py hc2mqtt.py HCDevice.py HCSocket.py HCxml2json.py HADiscovery.py /app/
COPY discovery.yaml /app/

# Neue Dateien
COPY web-ui/ /app/web-ui/
COPY scripts/ /app/scripts/

# run.sh als S6 Service einrichten
COPY run.sh /etc/services.d/hcpy/run
RUN chmod +x /etc/services.d/hcpy/run /app/scripts/*.py
