FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt ./

RUN apt-get update && \
  apt-get install -y --no-install-recommends gcc python3-dev libssl-dev libxml2-dev libxslt-dev python3-dev jq && \
  pip3 install -r requirements.txt && \
  apt-get remove -y gcc python3-dev libssl-dev && \
  apt-get autoremove -y

COPY hc2mqtt.py hc-login.py HCDevice.py HCSocket.py HCxml2json.py run.sh ./

RUN chmod a+x ./run.sh

CMD ["./run.sh"]
