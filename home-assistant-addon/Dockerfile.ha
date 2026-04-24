FROM ghcr.io/hassio-addons/base-python:18.0.0

WORKDIR /app

COPY requirements.txt .

RUN pip3 install -r requirements.txt

COPY hc2mqtt.py .
COPY hc-login.py .
COPY HADiscovery.py .
COPY HCDevice.py .
COPY HCSocket.py .
COPY HCxml2json.py .
COPY discovery.yaml .

COPY run.hass.sh .
RUN chmod +x /app/run.hass.sh
CMD /app/run.hass.sh
