import serial.tools.list_ports
from meshtastic.serial_interface import SerialInterface
from meshtastic.tcp_interface import TCPInterface
from meshtastic.ble_interface import BLEInterface
from meshtastic.util import fromPSK
from pubsub import pub
import time
try:
    from meshtastic.protobuf import channel_pb2, admin_pb2, portnums_pb2
except ImportError:
    from meshtastic import channel_pb2, admin_pb2, portnums_pb2
import sys
import argparse
from colorama import Fore #colors
import os #OS detect


#Color scheme:
#RED: errors
#MAGENTA: warnings
#BLUE: informational
#GREEN: only used when script succeeds

def keypress(): #input single character, cross-platform
    if os.name == 'nt':
        import msvcrt
        return msvcrt.getch().decode('utf-8')
    else:
        import tty
        import termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            char = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return char

def exitscript():
    print(f"{Fore.RED}Quitting...{Fore.RESET}")
    quit()

requestIds = []
gotResponse = False
if len(sys.argv) == 1: #are there any arguments? if not, use prompts
        print(f"""\nConnection method:
    {Fore.BLUE}1.{Fore.RESET} USB Serial
    {Fore.BLUE}2.{Fore.RESET} Network/TCP
    {Fore.BLUE}3.{Fore.RESET} Bluetooth/BLE
    {Fore.BLUE}0.{Fore.RESET} Quit""")
        i = 0
        key = "X" #initial value for keypress detector
        via = "" #port, IP/hostname or BLE mac address/device name
        while key not in ("1", "2", "3", "0"):
            key = keypress()
            i += 1
            match key:
                case "1":
                    method = "usb"
                    readablemethod="USB Serial"
                    availableports = [comport.device for comport in serial.tools.list_ports.comports()] #mian - this does not work on linux. Leaving this one to you. My head hurts.
                    if len(availableports) > 2:
                        print(f"More than one serial device detected: {Fore.BLUE}{availableports}{Fore.RESET}.")
                        if os.name == "nt":
                            prefix = "COM"
                        else:
                            prefix = "" #prefix for other OS's? Not really necessary to fill this string.
                        i = 0
                        while via not in availableports:
                            if i>0: print(f"{Fore.RED}Enter a valid serial port.{Fore.RESET}")
                            if i==3: exitscript()
                            i += 1
                            via = prefix+input(f"Port: {prefix}")
                    elif len(availableports) == 2:
                        via = availableports[1]
                    else:
                        print(f"{Fore.RED}No USB serial devices detected!{Fore.RESET}")
                        exitscript()
                    break
                case "2":
                    method = "tcp"
                    readablemethod = "Network/TCP"
                    i = 0
                    while via == "":
                        if i==3: exitscript()
                        i += 1
                        via = input(f"IP/Hostname: ")
                    break
                case "3":
                    method = "ble"
                    readablemethod = "Bluetooth/BLE"
                    i = 0
                    while via == "":
                        if i==3: exitscript()
                        i += 1
                        via = input(f"Bluetooth MAC address or name: ")
                    break
                case "0":
                    quit()
                case "\x1b": #esc key
                    quit()
                case _:
                    print(f"{Fore.RED}You must choose 1, 2, 3 or 0.{Fore.RESET}")
            if i == 3:
                exitscript()

        if via: #if a serial port, ip/hostname or ble mac address/name has been stated, display it to user
            readablemethod = readablemethod + f" {Fore.RESET}via{Fore.BLUE} " + via
                
        print(f"*** Connection method {key}: {Fore.BLUE}{readablemethod}{Fore.RESET} ***\n")

        print(f"""*** {Fore.MAGENTA}CAREFUL!{Fore.RESET} Don't overwrite/delete admin channel! ***
    {Fore.BLUE}1.{Fore.RESET} Add/replace a channel
    {Fore.BLUE}2.{Fore.RESET} Delete a channel
    {Fore.BLUE}0.{Fore.RESET} Quit""")
        i = 0
        key = "X" #initial value for keypress detector
        while key not in ("1", "2", "0"):
            key = keypress()
            i += 1
            match key:
                case "1":
                    action = "set"
                    print(f"*** Mode 1: {Fore.BLUE}Add/replace Channel{Fore.RESET} ***\n")
                case "2":
                    print(f"*** Mode 2: {Fore.BLUE}Delete Channel{Fore.RESET} ***\n")
                    action = "del"
                case "0":
                    quit()
                case "\x1b": #esc key
                    quit()
                case _:
                    print(f"{Fore.RED}You must choose 1, 2 or 0...{Fore.RESET}")
            if i == 3:
                exitscript()

        nodeid = "!"+input('NodeID (e.g !7d631f7e):\t!')
        channelnum = input('Channel number:\t\t')
        if action == "set":
            channelname = input('Channel name:\t\t')
            channelpsk = input('Channel PSK:\t\t')

        print(f"Send command? {Fore.BLUE}(y/n){Fore.RESET}")
        i = 0
        key = "X" #initial value for keypress detector
        while key.lower() not in ("y", "n"):
            key = keypress()
            i += 1
            if key.lower() == "y":
                break
            elif key.lower() == "n":
                print(f"{Fore.RED}Quitting...{Fore.RESET}")
                quit()
            elif key == "\x1b": #esc key
                    quit()
            else:
                print(f"{Fore.RED}You must choose y or n...{Fore.RESET}")
            if i == 3:
                exitscript()
else:
    #argument mode
    ### Add arguments to parse
    parser = argparse.ArgumentParser(
            add_help=False,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=f"{Fore.BLUE}This is a script to add/set or delete a channel remotely.\nMeshtastic apps are not able to reliably alter channels remotely (via admin channel) due to their requirement to get all remote channels before changing them.\nThis script skips getting the channels from the remote node, and will retry until it succeeds.\nRequires admin access to the remote node. For more information, visit: https://meshtastic.org/docs/configuration/remote-admin/\n*** {Fore.MAGENTA}CAREFUL! Don't overwrite/delete admin channel!{Fore.BLUE} ***{Fore.MAGENTA}\nLeave channel list contiguous!{Fore.BLUE} Deleting middle channels may lead to unexpected behaviors.\nThis script can also be used WITHOUT any arguments - in this case, it will give prompts.{Fore.RESET}")

    helpGroup = parser.add_argument_group("Help")
    helpGroup.add_argument("-h", "--help", action="help", help="Show this help message and exit.")

    connOuter = parser.add_argument_group('Connection', 'Optional arguments to specify a device to connect to and how. When unspecified, will use serial. If more than one serial device is connected, --port is required.')
    conn = connOuter.add_mutually_exclusive_group()
    conn.add_argument(
        "--port",
        help=f"The port to connect to via serial, e.g. `{Fore.BLUE}COM5{Fore.RESET}` or `{Fore.BLUE}/dev/ttyUSB0{Fore.RESET}`. NOT YET IMPLEMENTED.",
        default=None,
        action=
    )
    conn.add_argument(
        "--host",
        help="The hostname or IP address to connect to using if using network. NOT YET IMPLEMENTED.", 
        default=None,
    )
    conn.add_argument(
        "--ble",
        "--bt",
        help="The Bluetooth device MAC address or name to connect to. NOT YET IMPLEMENTED.",
        default=None,
    )

    action = parser.add_argument_group('Mode', 'What mode are we using? Choose one.')
    act = action.add_mutually_exclusive_group()
    act.add_argument(
        "--set",
        "--add",
        help="Set a channel [DEFAULT].",
        default=True,
        action='store_true',
    )
    act.add_argument(
        "--delete",
        "--del",
        help="Delete a channel.",
        default=False,
        action='store_true',
    )

    identity = parser.add_argument_group('Node ID', 'Identify the remote node. Choose one. [REQUIRED]')
    id = identity.add_mutually_exclusive_group(required=True)
    id.add_argument(
        "--nodeid",
        help=f"nodeID we are sending commands to (e.g `{Fore.BLUE}!ba4bf9d0{Fore.RESET}`).",
        type=str.lower,
    )
    id.add_argument(
        "--nodenum",
        help=f"Node number we are sending commands to (e.g `{Fore.BLUE}1828779180{Fore.RESET}`).",
        type=str.lower,
    )

    command = parser.add_argument_group('Command contents', 'The contents of the command we are sending to the remote node.')
    command.add_argument(
        "--channum",
        help="Channel number we are setting/deleting. [REQUIRED]",
        required=True,
    )
    command.add_argument(
        "--name",
        help="Optional channel name. If not specified, will leave blank (e.g `LONGFAST`). Not used for Delete Mode.",
        default="",
    )
    command.add_argument(
        "--psk",
        help="Optional encryption key. If not specified, will leave blank (`AQ==`). Not used for Delete Mode.",
        default="",
    )

    args = parser.parse_args()

    if args.ble: #set the method argument to the method variable, and also set readablemethod
        method = "ble"
        readablemethod = "Bluetooth/BLE"
    elif args.host:
        method = "tcp"
        readablemethod = "Network/TCP"
    else:
        method = "usb"
        readablemethod = "Bluetooth/BLE"

    if args.delete: #set the action variable
        action="del"
    else:
        action="set"
    
    if args.nodeid:
        nodeid = args.nodeid
    else:
        nodeid = "!" + f"{int(args.nodenum):x}"
    channelnum = args.channum
    channelname = args.name
    channelpsk = args.psk

try:
    via
except:
    via = ""
else:
    viatext = f" via {via}"
if action == "set":
    print(f"\n*** {Fore.BLUE}Sending channel to {nodeid} over {readablemethod}{viatext}. Will retry until acknowledgment is received{Fore.RESET} ***")
else:
    print(f"\n*** {Fore.BLUE}Sending \"Delete Channel {channelnum}\" command to {nodeid}. Will retry until acknowledgment is received{Fore.RESET} ***")


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
    Packet ID:\t{Fore.BLUE}{packet['id']}{Fore.RESET}
    From:\t{Fore.BLUE}{packet['from']:08x}{Fore.RESET} (remote node)
    To:\t\t{Fore.BLUE}{packet['to']:08x}{Fore.RESET} (you)
    Port:\t{Fore.BLUE}{packet['decoded']['portnum']}{Fore.RESET}"""
    if 'requestId' in packet['decoded']:
        ret += f"\n    Request ID:\t{Fore.BLUE}{packet['decoded']['requestId']}{Fore.RESET}"
    if packet['decoded']['portnum'] == 'ROUTING_APP':
        ret += f"\n    Error:\t{Fore.RED}{packet['decoded']['routing']['errorReason']}{Fore.RESET}"
    return ret

def onReceive(packet, interface):
    global gotResponse, requestIds
    if 'decoded' in packet:
        if 'requestId' in packet['decoded']:
            if packet['decoded']['requestId'] in requestIds:
                if packet['decoded']['portnum'] == 'ROUTING_APP' and packet['decoded']['routing']['errorReason'] == "NONE":
                    if packet['from'] == interface.localNode.nodeNum:
                        print(f"Observed packet rebroadcast, continuing to wait...")
                    else:
                        print(f"{Fore.GREEN}Received acknowledgement:{Fore.RESET} {printable_packet(packet)}")
                        gotResponse = True
                        print(f"\n***************    {Fore.GREEN}SUCCESS{Fore.RESET}    ***************")
                        print(f"*** Received acknowledgement of channel {channelnum} ***")
                        print(f"************** Took {attempts} attempts **************")
                else:
                    print(f"{Fore.RED}Unexpected response:{Fore.RESET} {printable_packet(packet)}")
                    print(f"*** {Fore.RED}THIS IS PROBABLY AN ERROR{Fore.RESET} ***")
                    if packet['decoded']['routing']['errorReason'] == "NO_CHANNEL": print("`Error: NO_CHANNEL` indicates that you do not have an admin channel in common with the remote node.")
                    gotResponse = True
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
    print(f"{Fore.BLUE}Sent channel to remote node (packet ID: {pkt.id}){Fore.RESET}")
    print("Waiting for acknowledgement...")

if __name__ == "__main__":

    pub.subscribe(onReceive, "meshtastic.receive")

    if len(via) > 0:
        client = SerialInterface(via)
    else:
        client = SerialInterface()

    sendOnce(client, nodeid, index=int(channelnum))

    i = 0
    attempts = 1
    while not gotResponse:
        if i >= 30:
            print(f"{Fore.RED}Timed out, retrying... (attempt #{attempts}){Fore.RESET}")
            sendOnce(client, nodeid, index=int(channelnum))
            attempts += 1
            i = 0
        time.sleep(1)
        i +=1

    try:
        args
    except:
        print("\nPress any key to exit...")
        keypress()

    client.close()
