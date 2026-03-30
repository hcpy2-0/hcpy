ARG BUILD_FROM
FROM $BUILD_FROM

LABEL \
  io.hass.version="VERSION" \
  io.hass.type="addon" \
  io.hass.arch="armhf|aarch64|i386|amd64"

RUN apk add --no-cache \
    python3 py3-pip py3-cryptography py3-cffi \
    bash curl \
    openssl-dev gcc musl-dev python3-dev libffi-dev

WORKDIR /app

COPY requirements.txt /app/
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt

COPY requirements-extra.txt /app/
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements-extra.txt

# Build-Dependencies entfernen
RUN apk del gcc musl-dev python3-dev libffi-dev openssl-dev

# Original hcpy Quellcode
COPY hc-login.py hc2mqtt.py HCDevice.py HCSocket.py HCxml2json.py HADiscovery.py /app/
COPY discovery.yaml /app/

# Neue Dateien
COPY web-ui/ /app/web-ui/
COPY scripts/ /app/scripts/
COPY run.sh /app/run.sh
RUN chmod +x /app/run.sh /app/scripts/*.py

CMD [ "/app/run.sh" ]
