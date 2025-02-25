# Create a websocket that wraps a connection to a
# Bosh-Siemens Home Connect device
import json
import re
import socket
import ssl
import sys
from base64 import urlsafe_b64decode as base64url
from datetime import datetime

import websocket
from Crypto.Cipher import AES
from Crypto.Hash import HMAC, SHA256
from Crypto.Random import get_random_bytes


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")


if sys.version_info[1] < 13:
    try:
        import sslpsk

        # Monkey patch for sslpsk in pip using the old _sslobj
        def _sslobj(sock):
            if (3, 5) <= sys.version_info <= (3, 7):
                return sock._sslobj._sslobj
            else:
                return sock._sslobj

        sslpsk.sslpsk._sslobj = _sslobj
    except ImportError:
        print("Unable to import sslpsk library, will use OpenSSL if available")


# Convience to compute an HMAC on a message
def hmac(key, msg):
    mac = HMAC.new(key, msg=msg, digestmod=SHA256).digest()
    return mac


class HCSocket:
    def __init__(self, host, psk64, iv64=None, domain_suffix=""):
        self.host = host
        if domain_suffix:
            self.host = f"{host}.{domain_suffix}"

        self.psk = base64url(psk64 + "===")
        self.debug = False

        if iv64:
            # an HTTP self-encrypted socket
            self.http = True
            self.iv = base64url(iv64 + "===")
            self.enckey = hmac(self.psk, b"ENC")
            self.mackey = hmac(self.psk, b"MAC")
            self.port = 80
            self.uri = f"ws://{host}:80/homeconnect"
        else:
            self.http = False
            self.port = 443
            self.uri = f"wss://{host}:443/homeconnect"

        # don't connect automatically so that debug etc can be set
        # self.reconnect()

    # restore the encryption state for a fresh connection
    # this is only used by the HTTP connection
    def reset(self):
        if not self.http:
            return
        self.last_rx_hmac = bytes(16)
        self.last_tx_hmac = bytes(16)

        self.aes_encrypt = AES.new(self.enckey, AES.MODE_CBC, self.iv)
        self.aes_decrypt = AES.new(self.enckey, AES.MODE_CBC, self.iv)

    # hmac an inbound or outbound message, chaining the last hmac too
    def hmac_msg(self, direction, enc_msg):
        hmac_msg = self.iv + direction + enc_msg
        return hmac(self.mackey, hmac_msg)[0:16]

    def wrap_socket_psk(self, tcp_socket):
        # TLS-PSK implemented in Python3.13
        if sys.version_info[1] >= 13 and ssl.HAS_PSK:
            try:
                self.dprint("Using native TLS-PSK")
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                # TLSv1.3 doesn't appear to be supported
                context.maximum_version = ssl.TLSVersion.TLSv1_2
                context.minimum_version = ssl.TLSVersion.SSLv3
                context.set_ciphers("PSK")  # Originally ECDHE-PSK-CHACHA20-POLY1305a
                # Identity hint from server is HCCOM_Local_App but can be null
                context.set_psk_client_callback(lambda hint: ("HCCOM_Local_App", self.psk))
                return context.wrap_socket(tcp_socket, server_hostname=self.host)
            except Exception as e:
                print(e)
        # sslpsk needs wrap_socket which was removed in 3.12 but may be fixed
        elif "sslpsk" in sys.modules:
            self.dprint("Using sslpsk")
            try:
                return sslpsk.wrap_socket(
                    tcp_socket,
                    ssl_version=ssl.PROTOCOL_TLSv1_2,
                    ciphers="ECDHE-PSK-CHACHA20-POLY1305",
                    psk=self.psk,
                )
            except AttributeError as e:
                raise NotImplementedError("sslpsk requires ssl.wrap_socket") from e
        else:
            raise NotImplementedError("No suitable TLS-PSK mechanism is available.")

    def decrypt(self, buf):
        if len(buf) < 32:
            print("Short message?", buf.hex(), file=sys.stderr)
            return None
        if len(buf) % 16 != 0:
            print("Unaligned message? probably bad", buf.hex(), file=sys.stderr)

        # split the message into the encrypted message and the first 16-bytes of the HMAC
        enc_msg = buf[0:-16]
        their_hmac = buf[-16:]

        # compute the expected hmac on the encrypted message
        our_hmac = self.hmac_msg(b"\x43" + self.last_rx_hmac, enc_msg)

        if their_hmac != our_hmac:
            print("HMAC failure", their_hmac.hex(), our_hmac.hex(), file=sys.stderr)
            return None

        self.last_rx_hmac = their_hmac

        # decrypt the message with CBC, so the last message block is mixed in
        msg = self.aes_decrypt.decrypt(enc_msg)

        # check for padding and trim it off the end
        pad_len = msg[-1]
        if len(msg) < pad_len:
            print("padding error?", msg.hex())
            return None

        return msg[0:-pad_len]

    def encrypt(self, clear_msg):
        # convert the UTF-8 string into a byte array
        clear_msg = bytes(clear_msg, "utf-8")

        # pad the buffer, adding an extra block if necessary
        pad_len = 16 - (len(clear_msg) % 16)
        if pad_len == 1:
            pad_len += 16
        pad = b"\x00" + get_random_bytes(pad_len - 2) + bytearray([pad_len])

        clear_msg = clear_msg + pad

        # encrypt the padded message with CBC, so there is chained
        # state from the last cipher block sent
        enc_msg = self.aes_encrypt.encrypt(clear_msg)

        # compute the hmac of the encrypted message, chaining the
        # hmac of the previous message plus direction 'E'
        self.last_tx_hmac = self.hmac_msg(b"\x45" + self.last_tx_hmac, enc_msg)

        # append the new hmac to the message
        return enc_msg + self.last_tx_hmac

    def reconnect(self):
        self.reset()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.host, self.port))

        if not self.http:
            sock = self.wrap_socket_psk(sock)

        print(now(), "CON:", self.uri)
        self.ws = websocket.WebSocket()
        self.ws.connect(self.uri, socket=sock, origin="")

    def send(self, msg):
        buf = json.dumps(msg, separators=(",", ":"))
        # swap " for '
        buf = re.sub("'", '"', buf)
        self.dprint("TX:", buf)
        if self.http:
            self.ws.send_bytes(self.encrypt(buf))
        else:
            self.ws.send(buf)

    def recv(self):
        buf = self.ws.recv()
        if buf is None or buf == "":
            return None

        if self.http:
            buf = self.decrypt(buf)
        if buf is None:
            return None

        self.dprint("RX:", buf)
        return buf

    def run_forever(self, on_message, on_open, on_close, on_error):
        self.reset()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.host, self.port))

        if not self.http:
            sock = self.wrap_socket_psk(sock)

        def _on_open(ws):
            self.dprint("on connect")
            on_open(ws)

        def _on_close(ws, close_status_code, close_msg):
            self.dprint(f"close: {close_msg}")
            on_close(ws, close_status_code, close_msg)

        def _on_message(ws, message):
            if self.http:
                message = self.decrypt(message)
            self.dprint("RX:", message)
            on_message(ws, message)

        def _on_error(ws, error):
            self.dprint(f"error {error}")
            on_error(ws, error)

        print(now(), "CON:", self.uri)
        self.ws = websocket.WebSocketApp(
            self.uri,
            socket=sock,
            on_open=_on_open,
            on_message=_on_message,
            on_close=_on_close,
            on_error=_on_error,
        )

        websocket.setdefaulttimeout(30)

        self.ws.run_forever(ping_interval=120, ping_timeout=10)

    # Debug print
    def dprint(self, *args):
        if self.debug:
            print(now(), *args)
