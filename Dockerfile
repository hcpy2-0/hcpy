FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt ./

RUN apt-get update && \
  apt-get install -y --no-install-recommends gcc python3-dev libssl-dev && \
  pip3 install -r requirements.txt && \
  apt-get remove -y gcc python3-dev libssl-dev && \
  apt-get autoremove -y

COPY hc2mqtt hc-login HCDevice.py HCSocket.py ./

ENTRYPOINT ["python3"]
CMD ["hc2mqtt", "/config/config.json"]
