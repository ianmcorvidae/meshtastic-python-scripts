import paho.mqtt.client as mqtt
import sys
from meshtastic import mqtt_pb2, portnums_pb2, mesh_pb2, protocols, BROADCAST_NUM
from google.protobuf.json_format import MessageToJson

import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

root_topic = 'msh'
default_key = "1PG7OiApB1nwvP+rz05pAQ=="

# with thanks to pdxlocs
def try_decode(mp):
    key_bytes = base64.b64decode(default_key.encode('ascii'))

    nonce = getattr(mp, "id").to_bytes(8, "little") + getattr(mp, "from").to_bytes(8, "little")
    cipher = Cipher(algorithms.AES(key_bytes), modes.CTR(nonce), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted_bytes = decryptor.update(getattr(mp, "encrypted")) + decryptor.finalize()

    data = mesh_pb2.Data()
    data.ParseFromString(decrypted_bytes)
    mp.decoded.CopyFrom(data)

def on_connect(client, userdata, flags, reason_code, properties):
    global root_topic
    if reason_code == 0:
        client.subscribe(f'{root_topic}/2/c/#')
        client.subscribe(f'{root_topic}/2/e/#')
    else:
        print(f"{userdata} {flags} {reason_code} {properties}")

def on_disconnect(client, userdata, flags, reason_code, properties):
    print(f"disconnected with reason code {str(reason_code)}")

def on_message(client, userdata, msg):
    se = mqtt_pb2.ServiceEnvelope()
    try:
        se.ParseFromString(msg.payload)
        mp = se.packet
    except Exception as e:
        print(f"ERROR: parsing service envelope: {str(e)}")
        return

    from_id = getattr(mp, 'from')
    to_id = mp.to
    if to_id == BROADCAST_NUM:
        to_id = 'all'
    else:
        to_id = f"{to_id:x}"

    pn = portnums_pb2.PortNum.Name(mp.decoded.portnum)

    prefix = f"{mp.channel} [{from_id:x}->{to_id}] {pn}:"
    if mp.HasField("encrypted") and not mp.HasField("decoded"):
        try:
            try_decode(mp)
            pn = portnums_pb2.PortNum.Name(mp.decoded.portnum)
            prefix = f"{mp.channel} [{from_id:x}->{to_id}] {pn}:"
        except Exception as e:
            print(f"{prefix} could not be decrypted")

    handler = protocols.get(mp.decoded.portnum)
    if handler is None:
        print("nothing came from protocols")
        return

    if handler.protobufFactory is None:
        print(f"{prefix} {mp.decoded.payload}")
    else:
        pb = handler.protobufFactory()
        pb.ParseFromString(mp.decoded.payload)
        p = MessageToJson(pb)
        print(f"{prefix} {p}")

def connect(client, username, pw, broker, port):
    try:
        client.username_pw_set(username, pw)
        client.connect(broker, port, 60)
    except Exception as e:
        print(f"failed connect: {str(e)}")

if __name__ == "__main__":
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="", clean_session=True, userdata=None)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    connect(client, sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]))

    if len(sys.argv) > 5:
        root_topic = sys.argv[5]

    client.loop_forever()
