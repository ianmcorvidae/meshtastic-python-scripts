from meshtastic.serial_interface import SerialInterface
from meshtastic.tcp_interface import TCPInterface
from meshtastic.util import fromPSK
from pubsub import pub
import time
try:
    from meshtastic.protobuf import channel_pb2, admin_pb2, portnums_pb2
except ImportError:
    from meshtastic import channel_pb2, admin_pb2, portnums_pb2
import sys

requestId = None
gotResponse = False

def make_channel(role=channel_pb2.Channel.Role.DISABLED, index=0, name=None, psk=None):
    ch = channel_pb2.Channel()
    ch.role = role
    ch.index = index
    if role != channel_pb2.Channel.Role.DISABLED:
        if name is not None:
            ch.settings.name = name
        if psk is not None:
            ch.settings.psk = fromPSK(psk)
    return ch

def printable_packet(packet):
    ret = f"""
    ID:   {packet['id']}
    From: {packet['from']:08x}
    To:   {packet['to']:08x}
    Port: {packet['decoded']['portnum']}"""
    if packet['decoded']['portnum'] == 'ROUTING_APP':
        ret += f"\n    Err: {packet['decoded']['routing']['errorReason']}"
    return ret

def onReceive(packet, interface):
    global gotResponse, requestId
    if 'decoded' in packet:
        if 'requestId' in packet['decoded']:
            if packet['decoded']['requestId'] == requestId:
                if packet['decoded']['portnum'] == 'ROUTING_APP' and packet['decoded']['routing']['errorReason'] == "NONE":
                    if packet['from'] == interface.localNode.nodeNum:
                        print(f"{packet['id']}\t|| Got implicit ack, continuing to wait...")
                    else:
                        print(f"{packet['id']}\t|| Got ack: {printable_packet(packet)}")
                        gotResponse = True
                else:
                    print(f"{packet['id']}\t|| got response for packet but it was not routing_app/reason none: {printable_packet(packet)}")
                    print("*********************************")
                    print("*** THIS IS PROBABLY AN ERROR ***")
                    print("*********************************")
            else:
                print(f"{packet['id']}\t|| got response for different packet: {packet['decoded']['requestId']}")
        else:
            print(f"{packet['id']}\t|| no requestId in decoded packet")
    else:
        print(f"{packet['id']}\t|| no decoded in packet")

def sendAdmin(client, packet, remote_node):
    adminIndex = client.localNode._getAdminChannelIndex()
    return client.sendData(
            packet,
            remote_node,
            portNum=portnums_pb2.PortNum.ADMIN_APP,
            wantAck=True,
            channelIndex=adminIndex,
    )

if __name__ == "__main__":
    remote_node = sys.argv[1]

    ch = make_channel(index=int(sys.argv[2]))

    pub.subscribe(onReceive, "meshtastic.receive")

    client = SerialInterface()
    #client = TCPInterface()
    node = client.getNode(remote_node, False) # false prevents channel requests

    p = admin_pb2.AdminMessage()
    p.set_channel.CopyFrom(ch)

    pkt = sendAdmin(client, p, remote_node)

    requestId = pkt.id
    print(f"SENT: request id {pkt.id}")
    print("      waiting for ack")

    while not gotResponse:
        time.sleep(1)

    client.close()
