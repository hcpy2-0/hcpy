FROM python:3.13-alpine

WORKDIR /app

COPY requirements.txt ./

RUN pip3 install -r requirements.txt

COPY hc2mqtt.py hc-login.py HADiscovery.py HCDevice.py HCSocket.py HCxml2json.py run.standalone.sh discovery.yaml ./

RUN chmod a+x ./run.standalone.sh

CMD ["./run.standalone.sh"]
