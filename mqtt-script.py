import paho.mqtt.client as mqtt
import sys
from meshtastic import mqtt_pb2, portnums_pb2, protocols, BROADCAST_NUM
from google.protobuf.json_format import MessageToJson

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        client.subscribe('msh/2/c/#')
        client.subscribe('msh/2/e/#')
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
        print(f"err parsing service envelope: {str(e)}")
        return

    if mp.HasField("encrypted") and not mp.HasField("decoded"):
        print("encrypted, not continuing")
        return

    handler = protocols.get(mp.decoded.portnum)
    if handler is None:
        print("nothing came from protocols, or not protobuf")
        return

    from_id = getattr(mp, 'from')
    to_id = mp.to
    if to_id == BROADCAST_NUM:
        to_id = 'all'
    else:
        to_id = f"{to_id:x}"

    pn = portnums_pb2.PortNum.Name(mp.decoded.portnum)
    if handler.protobufFactory is None:
        print(f"{mp.channel} [{from_id:x}->{to_id}] {pn}: {mp.decoded.payload}")
    else:
        pb = handler.protobufFactory()
        pb.ParseFromString(mp.decoded.payload)
        p = MessageToJson(pb)
        print(f"{mp.channel} [{from_id:x}->{to_id}] {pn}: {p}")

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

    client.loop_forever()
