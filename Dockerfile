FROM python:3.10-slim

ARG BASHIO_VERSION="v0.16.2"
ARG BASHIO_SHA256="d0f0c780c4badd103c00c572b1bf9645520d15a8a8070d6e3d64e35cb9f583aa"

WORKDIR /app

COPY requirements.txt ./

RUN apt-get update && \
  apt-get install -y --no-install-recommends curl tar gcc python3-dev libssl-dev libxml2-dev libxslt-dev python3-dev jq && \
  pip3 install -r requirements.txt && \
  apt-get remove -y gcc python3-dev libssl-dev && \
  apt-get autoremove -y \
    && curl -J -L -o /tmp/bashio.tar.gz \
        "https://github.com/hassio-addons/bashio/archive/${BASHIO_VERSION}.tar.gz" \
    && echo "${BASHIO_SHA256} /tmp/bashio.tar.gz" | sha256sum --check \
    && mkdir /tmp/bashio \
    && tar zxvf \
        /tmp/bashio.tar.gz \
        --strip 1 -C /tmp/bashio \
    && mv /tmp/bashio/lib /usr/lib/bashio \
    && ln -s /usr/lib/bashio/bashio /usr/bin/bashio

COPY hc2mqtt.py hc-login.py HADiscovery.py HCDevice.py HCSocket.py HCxml2json.py run.sh ./

RUN chmod a+x ./run.sh

CMD ["./run.sh"]
