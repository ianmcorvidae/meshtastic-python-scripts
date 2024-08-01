from meshtastic.serial_interface import SerialInterface
#from meshtastic.tcp_interface import TCPInterface
from meshtastic.util import fromPSK
from pubsub import pub
import time
try:
    from meshtastic.protobuf import channel_pb2, admin_pb2, portnums_pb2
except ImportError:
    from meshtastic import channel_pb2, admin_pb2, portnums_pb2# Set/remove a channel
#
# Connect node via USB
#
# To set a channel:
# Launch script and answer prompts, OR
# Use arguments as follows (last two arguments optional)
# set-remove_channel.py set !nodeID channel_number channel_name channel_PSK
#
# To delete a channel:
# Launch script and answer prompts, OR
# Use arguments as follows (last two arguments optional)
# set-remove_channel.py del !nodeID channel_number
# !! Deleting middle channels (such as deleting channel 2 on a node with 6 channels) may lead to unexpected behaviors. It is best practice to leave the channel list contiguous.

from meshtastic.serial_interface import SerialInterface
#from meshtastic.tcp_interface import TCPInterface
from meshtastic.util import fromPSK
from pubsub import pub
import time
try:
    from meshtastic.protobuf import channel_pb2, admin_pb2, portnums_pb2
except ImportError:
    from meshtastic import channel_pb2, admin_pb2, portnums_pb2
import sys
import msvcrt

requestIds = []
gotResponse = False

try:
    action = sys.argv[1] #are there any arguments?
except: #if not, use prompts
    print("\n*** CAREFUL! Don't overwrite/delete admin channel! ***")
    print("1. Add/replace a channel\n2. Delete a channel\n0. Quit")
    key = msvcrt.getche().decode('ASCII')
    print("")
    if key == "0":
        quit()
    elif key != "1" and key != "2":
        print("You must choose 1, 2 or 0. Quitting...")
        quit()
    if key == "2": print("*** Leave channel list contiguous! Deleting middle channels may lead to unexpected behaviors ***")
    nodeid = "!"+input('NodeID (for example, !7d631f7e): !')
    channelnum = input('Channel number: ')
    if key == "1":
        action = "set"
        channelname = input('Channel name: ')
        channelpsk = input('Channel PSK: ')
    elif key == "2":
        action = "del"
else: #argument mode
    nodeid = sys.argv[2]
    channelnum = sys.argv[3]
    if action == "set":
        channelname = channelpsk = ""
        if len(sys.argv) > 4: #if arguments for channel name is present, use it. Otherwise, leave blank
            channelname = sys.argv[4]
            if len(sys.argv) > 5: #if arguments for channel psk is present, use it. Otherwise, leave blank
                channelpsk = sys.argv[5]
    elif action == "del":
        action = "del"
    else:
        print("When using arguments, first argument must be \"set\" or \"del\".")
        quit()

if action == "set":
    print(f"\n*** Sending channel {channelnum} to {nodeid}. Will retry until acknowledgment is received ***")
else:
    print(f"\n*** Sending \"Delete Channel\" {channelnum} command to {nodeid}. Will retry until acknowledgment is received ***")

time.sleep(2)

if action == "set": #we're adding/setting a channel
    def make_channel(index=int(channelnum), role=channel_pb2.Channel.Role.SECONDARY, name=channelname, psk="base64:" + channelpsk):
        ch = channel_pb2.Channel()
        ch.role = role
        ch.index = index
        if role != channel_pb2.Channel.Role.DISABLED:
            if name is not None:
                ch.settings.name = name
            if psk is not None:
                ch.settings.psk = fromPSK(psk)
        return ch
else: #we're deleting a channel
    def make_channel(index=int(channelnum), role=channel_pb2.Channel.Role.DISABLED, name=None, psk=None):
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
    if 'requestId' in packet['decoded']:
        ret += f"\n    Req:  {packet['decoded']['requestId']}"
    if packet['decoded']['portnum'] == 'ROUTING_APP':
        ret += f"\n    Err:  {packet['decoded']['routing']['errorReason']}"
    return ret

def onReceive(packet, interface):
    global gotResponse, requestIds
    if 'decoded' in packet:
        if 'requestId' in packet['decoded']:
            if packet['decoded']['requestId'] in requestIds:
                if packet['decoded']['portnum'] == 'ROUTING_APP' and packet['decoded']['routing']['errorReason'] == "NONE":
                    if packet['from'] == interface.localNode.nodeNum:
                        print(f"Observed packet relay, continuing to wait...")
                    else:
                        print(f"Received acknowledgement: {printable_packet(packet)}")
                        gotResponse = True
                        print("\n***************    SUCCESS    ***************")
                        print("*** Received acknowledgement of channel", channelnum, "***")
                        print("************** Took", t, "attempts **************")
                else:
                    print(f"{packet['id']}\t|| Got response for packet but it was not routing_app/reason none: {printable_packet(packet)}")
                    print("*********************************")
                    print("*** THIS IS PROBABLY AN ERROR ***")
                    print("*********************************")
            #else:
                #print(f"{packet['id']}\t|| got response for different packet: {packet['decoded']['requestId']}")
        #else:
            #print(f"{packet['id']}\t|| no requestId in decoded packet")
    #else:
        #print(f"{packet['id']}\t|| no decoded in packet")

def sendAdmin(client, packet, nodeid):
    adminIndex = client.localNode._getAdminChannelIndex()
    return client.sendData(
            packet,
            nodeid,
            portNum=portnums_pb2.PortNum.ADMIN_APP,
            wantAck=True,
            channelIndex=adminIndex,
    )

def sendOnce(client, nodeid, *args, **kwargs):
    ch = make_channel(*args, **kwargs)

    p = admin_pb2.AdminMessage()
    p.set_channel.CopyFrom(ch)

    pkt = sendAdmin(client, p, nodeid)

    requestIds.append(pkt.id)
    print(f"\nSent channel to remote node (packet ID: {pkt.id})")
    print("Waiting for acknowledgement...")

if __name__ == "__main__":

    pub.subscribe(onReceive, "meshtastic.receive")

    client = SerialInterface()

    sendOnce(client, nodeid, index=int(channelnum))

    i = 0
    t = 1
    while not gotResponse:
        if i >= 30:
            print("\nTimed out, retrying... (attempt #",t,")")
            sendOnce(client, nodeid, index=int(channelnum))
            t = t + 1
            i = 0
        time.sleep(1)
        i = i + 1

    try:
        sys.argv[1] = nodeid
    except:
        print("\nPress any key to exit...")
        msvcrt.getch()

    client.close()
import sys
import msvcrt

requestIds = []
gotResponse = False

try:
    action = sys.argv[1] #are there any arguments?
except: #if not, use prompts
    print("\n*** CAREFUL! Don't overwrite/delete admin channel! ***")
    print("1. Add/replace a channel\n2. Delete a channel\n0. Quit")
    key = msvcrt.getche().decode('ASCII')
    print("")
    if key == "0":
        quit()
    elif key != "1" and key != "2":
        print("You must choose 1, 2 or 0. Quitting...")
        quit()
    nodeid = "!"+input('NodeID (for example, !7d631f7e): !')
    channelnum = input('Channel number: ')
    if key == "1":
        action = "set"
        channelname = input('Channel name: ')
        channelpsk = input('Channel PSK: ')
    elif key == "2":
        action = "del"
else: #argument mode
    nodeid = sys.argv[2]
    channelnum = sys.argv[3]
    if action == "set":
        channelname = channelpsk = ""
        if len(sys.argv) > 4: #if arguments for channel name is present, use it. Otherwise, leave blank
            channelname = sys.argv[4]
            if len(sys.argv) > 5: #if arguments for channel psk is present, use it. Otherwise, leave blank
                channelpsk = sys.argv[5]
    elif action == "del":
        action = "del"
    else:
        print("When using arguments, first argument must be \"set\" or \"del\".")
        quit()

if action == "set":
    print(f"\n*** Sending channel {channelnum} to {nodeid}. Will retry until acknowledgment is received ***")
else:
    print(f"\n*** Sending \"Delete Channel\" {channelnum} command to {nodeid}. Will retry until acknowledgment is received ***")

time.sleep(2)

if action == "set": #we're adding/setting a channel
    def make_channel(index=int(channelnum), role=channel_pb2.Channel.Role.SECONDARY, name=channelname, psk="base64:" + channelpsk):
        ch = channel_pb2.Channel()
        ch.role = role
        ch.index = index
        if role != channel_pb2.Channel.Role.DISABLED:
            if name is not None:
                ch.settings.name = name
            if psk is not None:
                ch.settings.psk = fromPSK(psk)
        return ch
else: #we're deleting a channel
    def make_channel(index=int(channelnum), role=channel_pb2.Channel.Role.DISABLED, name=None, psk=None):
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
    if 'requestId' in packet['decoded']:
        ret += f"\n    Req:  {packet['decoded']['requestId']}"
    if packet['decoded']['portnum'] == 'ROUTING_APP':
        ret += f"\n    Err:  {packet['decoded']['routing']['errorReason']}"
    return ret

def onReceive(packet, interface):
    global gotResponse, requestIds
    if 'decoded' in packet:
        if 'requestId' in packet['decoded']:
            if packet['decoded']['requestId'] in requestIds:
                if packet['decoded']['portnum'] == 'ROUTING_APP' and packet['decoded']['routing']['errorReason'] == "NONE":
                    if packet['from'] == interface.localNode.nodeNum:
                        print(f"Observed packet relay, continuing to wait...")
                    else:
                        print(f"Received acknowledgement: {printable_packet(packet)}")
                        gotResponse = True
                        print("\n***************    SUCCESS    ***************")
                        print("*** Received acknowledgement of channel", channelnum, "***")
                        print("************** Took", t, "attempts **************")
                else:
                    print(f"{packet['id']}\t|| Got response for packet but it was not routing_app/reason none: {printable_packet(packet)}")
                    print("*********************************")
                    print("*** THIS IS PROBABLY AN ERROR ***")
                    print("*********************************")
            #else:
                #print(f"{packet['id']}\t|| got response for different packet: {packet['decoded']['requestId']}")
        #else:
            #print(f"{packet['id']}\t|| no requestId in decoded packet")
    #else:
        #print(f"{packet['id']}\t|| no decoded in packet")

def sendAdmin(client, packet, nodeid):
    adminIndex = client.localNode._getAdminChannelIndex()
    return client.sendData(
            packet,
            nodeid,
            portNum=portnums_pb2.PortNum.ADMIN_APP,
            wantAck=True,
            channelIndex=adminIndex,
    )

def sendOnce(client, nodeid, *args, **kwargs):
    ch = make_channel(*args, **kwargs)

    p = admin_pb2.AdminMessage()
    p.set_channel.CopyFrom(ch)

    pkt = sendAdmin(client, p, nodeid)

    requestIds.append(pkt.id)
    print(f"\nSent channel to remote node (packet ID: {pkt.id})")
    print("Waiting for acknowledgement...")

if __name__ == "__main__":

    pub.subscribe(onReceive, "meshtastic.receive")

    client = SerialInterface()

    sendOnce(client, nodeid, index=int(channelnum))

    i = 0
    t = 1
    while not gotResponse:
        if i >= 30:
            print("\nTimed out, retrying... (attempt #",t,")")
            sendOnce(client, nodeid, index=int(channelnum))
            t = t + 1
            i = 0
        time.sleep(1)
        i = i + 1

    try:
        sys.argv[1] = nodeid
    except:
        print("\nPress any key to exit...")
        msvcrt.getch()

    client.close()
