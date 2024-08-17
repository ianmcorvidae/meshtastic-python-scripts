import serial.tools.list_ports
from meshtastic.serial_interface import SerialInterface
from meshtastic.tcp_interface import TCPInterface
from meshtastic.ble_interface import BLEInterface
from meshtastic.util import fromPSK, findPorts
from pubsub import pub
import time
try:
    from meshtastic.protobuf import channel_pb2, admin_pb2, portnums_pb2, config_pb2
except ImportError:
    from meshtastic import channel_pb2, admin_pb2, portnums_pb2, config_pb2
import sys
import argparse
import os #OS detect
os.system('') #required for colorama on win cmd
from colorama import Fore #colors

#Color scheme:
#LIGHTRED_EX: errors
#LIGHTRED_EX: warnings
#LIGHTBLUE_EX: informational
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
    print(f"{errormsg}{Fore.LIGHTRED_EX}Quitting...{Fore.RESET}")
    try:
        args
    except:
        print(f"\n{Fore.LIGHTBLUE_EX}Press any key to exit...{Fore.RESET}")
        keypress()
    try:
        client.close()
    except:
        ""
    quit()

requestIds = []
maxattempts = 25
via = ""
errormsg = ""
gotResponse = False
helptext = f"""\nThis is a script to change settings on a remote node that cannot be easily changed via app or CLI. To change a Meshtastic setting, the apps and CLI send a request for the current settings to the remote node via the admin channel and wait for a response. For most settings, this is fine, but for some this doesn't work reliably or at all. Remotely changing a channel, for example, requires receiving multiple packets from the remote node and then sending multiple packets back - due to the architecture of Meshtastic, this is not reliable. Enabling TX requires the remote node to send its current LoRa settings - which it can't do with TX off.\nThis script skips getting the settings from the remote node, and will retry up to 25 times until it succeeds (configurable in argument mode).\nRequires admin access to the remote node (see {Fore.LIGHTBLUE_EX}https://meshtastic.org/docs/configuration/remote-admin/{Fore.RESET}).\n*** {Fore.LIGHTRED_EX}CAREFUL! Don't overwrite/delete admin channel!{Fore.RESET} ***{Fore.LIGHTRED_EX}\nLeave channel list contiguous!{Fore.RESET} Deleting middle channels may lead to unexpected behaviors.\nThis script requires installation of the Meshtastic CLI (see {Fore.LIGHTBLUE_EX}https://meshtastic.org/docs/software/python/cli/installation/{Fore.RESET}).\n"""

if len(sys.argv) == 1: #are there any arguments? if not, use prompts
        print(f"""\nConnection method to local node:
    {Fore.LIGHTBLUE_EX}1.{Fore.RESET} USB Serial
    {Fore.LIGHTBLUE_EX}2.{Fore.RESET} Network/TCP
    {Fore.LIGHTBLUE_EX}3.{Fore.RESET} Bluetooth/BLE
    {Fore.LIGHTBLUE_EX}4.{Fore.RESET} Help
    {Fore.LIGHTBLUE_EX}0.{Fore.RESET} Quit""")
        i = 0
        key = "X" #initial value for keypress detector
        via = "" #port, IP/hostname or BLE mac address/device name
        while key not in ("1", "2", "3", "4", "0"):
            key = keypress()
            i += 1
            if key == "1":
                method = "usb"
                readablemethod="USB Serial"
                availableports = findPorts(True) #mian - this does not work on linux. Leaving this one to you. My head hurts.
                if len(availableports) > 1:
                    print(f"More than one serial device detected: {Fore.LIGHTBLUE_EX}{availableports}{Fore.RESET}.")
                    if os.name == "nt":
                        prefix = "COM"
                    else:
                        prefix = "" #prefix for other OS's? Not really necessary to fill this string.
                    i = 0
                    while via not in availableports:
                        if i>0: print(f"{Fore.LIGHTRED_EX}Enter a valid serial port.{Fore.RESET}")
                        if i==3: exitscript()
                        i += 1
                        via = prefix+input(f"Port: {prefix}")
                elif len(availableports) == 1:
                    via = availableports[0]
                else:
                    print(f"{Fore.LIGHTRED_EX}No USB serial devices detected!{Fore.RESET}")
                    exitscript()
                break
            elif key == "2":
                method = "tcp"
                readablemethod = "Network/TCP"
                i = 0
                while via == "":
                    if i==3: exitscript()
                    i += 1
                    via = input(f"IP/Hostname: ")
                break
            elif key == "3":
                method = "ble"
                readablemethod = "Bluetooth/BLE"
                i = 0
                while via == "":
                    if i==3: exitscript()
                    i += 1
                    via = input(f"Bluetooth MAC address or name: ")
                break
            elif key == "4":
                print(helptext+f"This script can also be used with arguments - run `{Fore.LIGHTBLUE_EX}set-remove_channel.py --help{Fore.RESET}`.")
                exitscript()
            elif key == "0" or key == "\x1b": #0 or esc
                quit()
            else:
                print(f"{Fore.LIGHTRED_EX}You must choose 1, 2, 3, 4 or 0.{Fore.RESET}")

            if i == 3:
                exitscript()

        if via: #if a serial port, ip/hostname or ble mac address/name has been stated, display it to user
            readablemethod += f" {Fore.RESET}via{Fore.LIGHTBLUE_EX} " + via
        print(f"*** Connection method {key}: {Fore.LIGHTBLUE_EX}{readablemethod}{Fore.RESET} ***\n")

        print(f"""    {Fore.LIGHTBLUE_EX}1.{Fore.RESET} Add/replace a channel
    {Fore.LIGHTBLUE_EX}2.{Fore.RESET} Delete a channel
    {Fore.LIGHTBLUE_EX}3.{Fore.RESET} Enable TX
    {Fore.LIGHTBLUE_EX}0.{Fore.RESET} Quit""")
        i = 0
        key = "X" #initial value for keypress detector
        while key not in ("1", "2", "3", "0"):
            key = keypress()
            i += 1
            if key == "1":
                action = "set"
                print(f"*** Mode 1: {Fore.LIGHTBLUE_EX}Add/replace Channel{Fore.RESET} ***\n*** {Fore.LIGHTRED_EX}CAREFUL!{Fore.RESET} Don't overwrite admin channel! ***\n")
            elif key == "2":
                print(f"*** Mode 2: {Fore.LIGHTBLUE_EX}Delete Channel{Fore.RESET} ***\n*** {Fore.LIGHTRED_EX}CAREFUL!{Fore.RESET} Don't delete admin channel! ***\n")
                action = "del"
            elif key == "3":
                print(f"*** Mode 3: {Fore.LIGHTBLUE_EX}Enable TX{Fore.RESET} ***\n")
                action = "tx"
            elif key == "0" or key == "\x1b":
                quit()
            else:
                print(f"{Fore.LIGHTRED_EX}You must choose 1, 2, 3 or 0...{Fore.RESET}")
            if i == 3:
                exitscript()

        nodeid = "!"
        i = 0
        while nodeid == "!":
            nodeid = "!"+input('NodeID (e.g !7d631f7e):\t!')
            if nodeid == "!":
                i += 1
                print(f"{Fore.LIGHTRED_EX}You must enter a nodeID.{Fore.RESET}")
                if i == 3: exitscript()

        if action == "set" or action == "del": channelnum = input('Channel number:\t\t')
        if action == "set":
            channelname = input('Channel name:\t\t')
            channelpsk = input('Channel PSK:\t\t')


        if action == "tx": #Get LoRa settings from user
            LoraSettings = {}
            print(f"\nEnabling TX remotely requires setting all LoRa settings (and will wipe all existing LoRa settings).\n*** {Fore.LIGHTRED_EX}Important! Make sure you use settings that are compatible with your local node!{Fore.RESET} ***\nAll but `{Fore.LIGHTBLUE_EX}Region{Fore.RESET}` can be left blank to use default settings.\nPress {Fore.LIGHTBLUE_EX}ENTER{Fore.RESET} to use default value.\n")
            
            print("Available regions: " + ", ".join([f"'{Fore.LIGHTBLUE_EX}{x}{Fore.RESET}'" for x in config_pb2.Config.LoRaConfig.RegionCode.keys() if x != "UNSET"]) + ".")
            i = 0
            LoraSettings['region'] = ""
            while LoraSettings['region'] == "":
                LoraSettings['region'] = input("Region? ")
                if LoraSettings['region'] == "":
                    print(f"{Fore.LIGHTRED_EX}Region must be specified.{Fore.RESET}")
                else: break
                i += 1
                if i == 3:
                    exitscript()

            print(f"Use preset? ({Fore.LIGHTBLUE_EX}y{Fore.RESET}/{Fore.LIGHTBLUE_EX}n{Fore.RESET})")
            i = 0
            key = "X" #initial value for keypress detector
            while key.lower() not in ("y", "n"):
                key = keypress()
                i += 1
                if key.lower() == "y" or key.lower() == "\r":
                    LoraSettings['use_preset'] = True
                    presetMap = {
                        "1": "SHORT_FAST",
                        "2": "SHORT_SLOW",
                        "3": "MEDIUM_FAST",
                        "4": "MEDIUM_SLOW",
                        "5": "LONG_FAST",
                        "6": "LONG_MODERATE",
                        "7": "LONG_SLOW",
                        "8": "VERY_LONG_SLOW",
                        "\r": ""
                    }
                    print(f"Choose a preset ({Fore.LIGHTBLUE_EX}ENTER{Fore.RESET} to skip):\n" + 
                            "\n".join(f"{Fore.LIGHTBLUE_EX}{x[0]}.{Fore.RESET} {x[1]}{' (default)' if x[1] == 'LONG_FAST' else ''}" for x in presetMap.items() if x[0] != "\r"))
                    ip = 0
                    LoraSettings['modem_preset'] = None
                    while LoraSettings['modem_preset'] == None:
                        LoraSettings['modem_preset'] = presetMap.get(keypress(), None)
                        if LoraSettings['modem_preset'] == None:
                            print(f"{Fore.LIGHTRED_EX}You must choose {Fore.LIGHTBLUE_EX}1{Fore.LIGHTRED_EX}-{Fore.LIGHTBLUE_EX}8{Fore.LIGHTRED_EX} or press {Fore.LIGHTBLUE_EX}ENTER{Fore.LIGHTRED_EX}...{Fore.RESET}")
                            ip += 1
                        if ip == 3: exitscript()
                    print(LoraSettings['modem_preset'])
                    break
                elif key.lower() == "n":
                    LoraSettings['use_preset'] = False
                    LoraSettings['bandwidth'] = LoraSettings['spread_factor'] = LoraSettings['coding_rate'] = False
                    i2 = 0
                    while not LoraSettings['bandwidth'] or not LoraSettings['spread_factor'] or not LoraSettings['coding_rate']:
                        print(f"When {Fore.LIGHTBLUE_EX}preset{Fore.RESET} is disabled, {Fore.LIGHTBLUE_EX}bandwidth{Fore.RESET}, {Fore.LIGHTBLUE_EX}spread factor{Fore.RESET} and {Fore.LIGHTBLUE_EX}coding rate{Fore.RESET} are required.")
                        LoraSettings['bandwidth'] = input("Bandwidth: ")
                        LoraSettings['spread_factor'] = input("Spread factor: ")
                        LoraSettings['coding_rate'] = input("Coding rate: ")
                        if LoraSettings['bandwidth'] and LoraSettings['spread_factor'] and LoraSettings['coding_rate']: break
                        i2 += 1
                        if i2 == 3: 
                            errormsg += f"{Fore.LIGHTRED_EX}When {Fore.LIGHTBLUE_EX}preset{Fore.LIGHTRED_EX} is disabled, {Fore.LIGHTBLUE_EX}bandwidth{Fore.LIGHTRED_EX}, {Fore.LIGHTBLUE_EX}spread factor{Fore.LIGHTRED_EX} and {Fore.LIGHTBLUE_EX}coding rate{Fore.LIGHTRED_EX} are required.{Fore.RESET}\n"
                            exitscript()
                        print(f"{Fore.LIGHTRED_EX}Error: {Fore.RESET}", end="")
                    break
                elif key == "\x1b": #esc key
                        quit()
                else:
                    print(f"{Fore.LIGHTRED_EX}You must choose y or n...{Fore.RESET}")
                if i == 3:
                    exitscript()

            LoraSettings['frequency_offset'] = input(f"Frequency offset ({Fore.LIGHTBLUE_EX}ENTER{Fore.RESET} to skip):\t")
            print(f"*** {Fore.LIGHTRED_EX}Important: make sure to set enough hops for the acknowledgement to get back to you!{Fore.RESET} ***")
            LoraSettings['hop_limit'] = input(f"Hop limit ({Fore.LIGHTBLUE_EX}ENTER{Fore.RESET} to skip):\t")
            LoraSettings['tx_power'] = input(f"TX power ({Fore.LIGHTBLUE_EX}ENTER{Fore.RESET} to skip):\t")
            print(f"*** {Fore.LIGHTRED_EX}Important: if you have a non default primary channel, frequency slot likely needs to be set!{Fore.RESET} ***")
            LoraSettings['channel_num'] = input(f"Frequency slot ({Fore.LIGHTBLUE_EX}ENTER{Fore.RESET} to skip):\t")
            LoraSettings['override_frequency'] = input(f"Override frequency ({Fore.LIGHTBLUE_EX}ENTER{Fore.RESET} to skip):\t")

            if input(f"Override duty cycle ({Fore.LIGHTBLUE_EX}ENTER{Fore.RESET} to skip)? ({Fore.LIGHTBLUE_EX}y{Fore.RESET}/{Fore.LIGHTBLUE_EX}n{Fore.RESET}) ").lower() == "y": #if user presses y, set to true. Any other key, false
                LoraSettings['override_duty_cycle'] = True
            else:
                LoraSettings['override_duty_cycle'] = False

            if input(f"Enable SX126X RX boosted gain ({Fore.LIGHTBLUE_EX}ENTER{Fore.RESET} to skip)? ({Fore.LIGHTBLUE_EX}y{Fore.RESET}/{Fore.LIGHTBLUE_EX}n{Fore.RESET}) ") == "n": #if user presses n, set to false. Any other key, True
                LoraSettings['sx126x_rx_boosted_gain'] = False
            else:
                LoraSettings['sx126x_rx_boosted_gain'] = True

            if input(f"Ignore MQTT ({Fore.LIGHTBLUE_EX}ENTER{Fore.RESET} to skip)? ({Fore.LIGHTBLUE_EX}y{Fore.RESET}/{Fore.LIGHTBLUE_EX}n{Fore.RESET}) ").lower() == "y": #as this value changes by region, it requires special handling - if the user skips this setting, it'll be left blank
                LoraSettings['ignore_mqtt'] = True
            elif LoraSettings['ignore_mqtt'] == "n":
                LoraSettings['ignore_mqtt'] = False
            else:
                LoraSettings['ignore_mqtt'] = ""

            if input(f"Disable PA Fan ({Fore.LIGHTBLUE_EX}ENTER{Fore.RESET} to skip)? ({Fore.LIGHTBLUE_EX}y{Fore.RESET}/{Fore.LIGHTBLUE_EX}n{Fore.RESET}) ").lower() == "y": #if user presses y, set to true. Any other key, set to default (false)
                LoraSettings['pa_fan_disabled'] = True
            else:
                LoraSettings['pa_fan_disabled'] = False

            LoraSettings['ignore_incoming'] = input(f"Ignore list. Up to three comma delineated nodeID's. Example: `{Fore.LIGHTBLUE_EX}!nodeid01,!nodeid02,!nodeid03{Fore.RESET}` ({Fore.LIGHTBLUE_EX}ENTER{Fore.RESET} to skip): ")

        try:
            print("\n"+', '.join(f'{Fore.LIGHTBLUE_EX}{key}{Fore.RESET}: {value if value != "" else "default"}' for key, value in LoraSettings.items()))
        except:
            ""
        """print(f"Send command? ({Fore.LIGHTBLUE_EX}y{Fore.RESET}/{Fore.LIGHTBLUE_EX}n{Fore.RESET})")
        i = 0
        key = "X" #initial value for keypress detector
        while key.lower() not in ("y", "n"):
            key = keypress()
            i += 1
            if key.lower() == "y":
                break
            elif key.lower() == "n":
                exitscript()
            elif key == "\x1b": #esc key
                    quit()
            else:
                print(f"{Fore.LIGHTRED_EX}You must choose y or n...{Fore.RESET}")
            if i == 3:
                exitscript()"""
else:
    #argument mode
    ### Add arguments to parse
    parser = argparse.ArgumentParser(
            add_help=False,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=helptext + f"This script can also be used WITHOUT any arguments - in this case, it will give prompts.")

    helpGroup = parser.add_argument_group("Help")
    helpGroup.add_argument("-h", "--help", action="help", help="Show this help message and exit.")

    connOuter = parser.add_argument_group('Connection', 'Optional arguments to specify a device to connect to and how. When unspecified, will use serial. If more than one serial device is connected, --port is required.')
    conn = connOuter.add_mutually_exclusive_group()
    conn.add_argument(
        "--port",
        help=f"The port to connect to via serial, e.g. `{Fore.LIGHTBLUE_EX}COM5{Fore.RESET}` or `{Fore.LIGHTBLUE_EX}/dev/ttyUSB0{Fore.RESET}`. NOT YET IMPLEMENTED.",
        default=None,
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

    options = parser.add_argument_group("Options")
    options.add_argument(
        "--attempts",
        metavar="#",
        help=f"Maximum number of retries. Default: {Fore.LIGHTBLUE_EX}25{Fore.RESET}. Configurable via argument only.",
        default=25,
    )
    options.add_argument(
        "--confirm",
        help=f"Confirm before sending command. Will display name of remote node if present in nodeDB. Default: off in argument mode. Always on in prompt mode.",
        default=False,
        action='store_true'
    )

    action = parser.add_argument_group('Command', 'What command are we sending? Choose one [REQUIRED].')
    act = action.add_mutually_exclusive_group()
    act.add_argument(
        "--set",
        help="Set a channel.",
        default=False,
        action='store_true',
    )
    act.add_argument(
        "--delete",
        help="Delete a channel.",
        default=False,
        action='store_true',
    )
    act.add_argument(
        "--tx",
        help="Enable TX on remote node. Requires sending all LoRa settings. NOT YET IMPLEMENTED.",
        default=False,
        action='store_true',
    )

    identity = parser.add_argument_group('Node ID', 'Identify the remote node. Specify one. [REQUIRED]')
    id = identity.add_mutually_exclusive_group()
    id.add_argument(
        "--nodeid",
        help=f"nodeID we are sending commands to (e.g `{Fore.LIGHTBLUE_EX}!ba4bf9d0{Fore.RESET}`).",
    )
    id.add_argument(
        "--nodenum",
        help=f"Node number we are sending commands to (e.g `{Fore.LIGHTBLUE_EX}1828779180{Fore.RESET}`).",
    )

    command = parser.add_argument_group('Command contents', 'The contents of the command we are sending to the remote node.')
    command.add_argument(
        "--channum",
        help="Channel number we are setting/deleting. REQUIRED for Set and Delete.",
        default=None,
    )
    command.add_argument(
        "--name",
        help="Optional channel name. If not specified, will leave blank (e.g `LONGFAST`). Not used for Delete or TX commands.",
        default="",
    )
    command.add_argument(
        "--psk",
        help="Optional encryption key. If not specified, will leave blank (`AQ==`). Not used for Delete or TX commands.",
        default="",
    )

    loraset = parser.add_argument_group('LoRa settings', f'Region is REQUIRED if enabling TX - the rest can be specified or left as default. Not used with Set and Delete commands.\n*** {Fore.LIGHTRED_EX}Important! Make sure you use settings that are compatible with your local node!{Fore.RESET} ***\nFor more information on LoRa settings: {Fore.LIGHTBLUE_EX}https://meshtastic.org/docs/configuration/radio/lora/{Fore.RESET}')
    loraset.add_argument(
        "--region",
        help=f"This is always required if enabling TX. Options: "+", ".join([f"'{Fore.LIGHTBLUE_EX}{x}{Fore.RESET}'" for x in config_pb2.Config.LoRaConfig.RegionCode.keys() if x != "UNSET"])+".",
        default=None,
    )
    loraset.add_argument(  #note that this is the opposite of the usual (argument is used to disable preset, not enable)
        "--nopreset",
        help="Don't use modem preset. Default (disabled) if not included.",
        default="",
        action='store_true'
    )
    loraset.add_argument(
        "--preset",
        help="Which modem preset to use. Default (LONG_FAST) if left blank.",
        choices=['SHORT_FAST','SHORT_SLOW','MEDIUM_FAST','MEDIUM_SLOW','LONG_FAST','LONG_MODERATE','LONG_SLOW','VERY_LONG_SLOW'],
        metavar="PRESET",
        default="",
    )
    loraset.add_argument(
        "--bandwidth",
        help="LoRa bandwidth. REQUIRED if not using LoRa preset.",
        default="",
    )
    loraset.add_argument(
        "--spread",
        help="LoRa spread factor. REQUIRED if not using LoRa preset.",
        default="",
    )
    loraset.add_argument(
        "--codingrate",
        help="LoRa coding rate. REQUIRED if not using LoRa preset.",
        default="",
    )
    loraset.add_argument(
        "--freqoffset",
        help="LoRa frequency offset. Default (0) if not included.",
        default="",
    )
    loraset.add_argument(
        "--hoplimit",
        help=f"Hop limit. Default (3) if not included. {Fore.LIGHTRED_EX}Important: make sure to set enough hops for the acknowledgement to get back to you!{Fore.RESET}",
        default="",
    )
    loraset.add_argument(
        "--txpwr",
        help="LoRa TX power. Default (30) if not included.",
        default="",
    )
    loraset.add_argument(
        "--freqslot",
        help=f"Frequency slot. Default (changes according to region and primary channel name) if not included. {Fore.LIGHTRED_EX}Important: if you have a non default primary channel, this likely needs to be set!{Fore.RESET}",
        default="",
    )
    loraset.add_argument(
        "--overfreq",
        help="LoRa Override Frequency (MHz). overrides Frequency slot. Default (changes according to region and primary channel name) if not included.",
        default="",
    )
    loraset.add_argument(
        "--overduty",
        help="Override duty cycle. Default (disabled) if not included.",
        default="",
        action='store_true'
    )
    loraset.add_argument( #note that this is the opposite of the usual (argument is used to disable preset, not enable)
        "--sx126xoff",
        help="Disable SX126X RX boosted gain. Default (disabled) if not included.",
        default=False,
        action='store_true'
    )
    loraset.add_argument(
        "--ignoremqtt",
        help="Ignore MQTT. Default (disabled if in a region with no duty cycle, enabled otherwise) if not included.",
        default="",
        action='store_true',
    )
    loraset.add_argument(
        "--pafanoff",
        help="Disables PA (power amplifier) fan. Default (disabled) if not included. NOT YET IMPLEMENTED.",
        default="",
        action='store_true',
    )
    loraset.add_argument(
        "--ignore",
        help="Ignore list. Default (none) if left blank. Up to three comma-delineated nodeID's including !. Example: `!nodeid01,!nodeid02,!nodeid03`.",
        default=None,
    )
    

    args = parser.parse_args()

    #check args for errors
    i = 0
    if not args.set and not args.delete and not args.tx:
        i += 1
        errormsg += f"{i}. Command must be specified: `{Fore.LIGHTBLUE_EX}--set{Fore.RESET}`, `{Fore.LIGHTBLUE_EX}--delete{Fore.RESET}` or `{Fore.LIGHTBLUE_EX}--tx{Fore.RESET}`.\n"
    if not args.nodeid and not args.nodenum:
        i += 1
        errormsg += f"{i}. Identity of remote node must be specified with `{Fore.LIGHTBLUE_EX}--nodeid{Fore.RESET}` or `{Fore.LIGHTBLUE_EX}--nodenum{Fore.RESET}`.\n"
    if args.set or args.delete:
        if not args.channum:
            i += 1
            errormsg += f"{i}. When using `{Fore.LIGHTBLUE_EX}--set{Fore.RESET}` or `{Fore.LIGHTBLUE_EX}--delete{Fore.RESET}`, `{Fore.LIGHTBLUE_EX}--channum{Fore.RESET}` must be specified.\n"
        else:
            if args.channum is not None:
                try:
                    int(args.channum)  # Attempt to convert to integer
                    if not 0 <= int(args.channum) <= 7:
                        i += 1
                        errormsg += f"{i}. Channel number must be between `{Fore.LIGHTBLUE_EX}0{Fore.RESET}` and `{Fore.LIGHTBLUE_EX}7{Fore.RESET}`.\n"
                except:
                    i += 1
                    errormsg += f"{i}. Channel number must be an integer (whole number).\n"
    maxattempts = int(args.attempts)
    if args.tx:
        if not args.region:
            i += 1
            errormsg += f"{i}. When `{Fore.LIGHTBLUE_EX}--tx{Fore.RESET}` is used, `{Fore.LIGHTBLUE_EX}--region{Fore.RESET}` must be specified.\n"
        if args.nopreset == True & (not args.bandwidth or not args.spread or not args.codingrate):
            i += 1
            errormsg += f"{i}. When using `{Fore.LIGHTBLUE_EX}--tx{Fore.RESET}` and `{Fore.LIGHTBLUE_EX}--nopreset{Fore.RESET}` is used, `{Fore.LIGHTBLUE_EX}--bandwidth{Fore.RESET}`, `{Fore.LIGHTBLUE_EX}--spread{Fore.RESET}` and `{Fore.LIGHTBLUE_EX}--codingrate{Fore.RESET}` must be specified.\n"
        action = "tx"

    if errormsg != "": exitscript()


### Convert arguments to variables
    if args.ble: #set the method argument to the method variable, and also set readablemethod
        method = "ble"
        readablemethod = "Bluetooth/BLE"
    elif args.host:
        method = "tcp"
        readablemethod = "Network/TCP"
    else:
        method = "usb"
        readablemethod = "Serial/USB"

    if args.set: #set the action variable
        action = "set"
    elif args.delete:
        action = "del"
    elif args.tx:
        action = "tx"
    
    if args.nodeid:
        nodeid = args.nodeid
        if not nodeid.startswith('!'): #if nodeid doesn't start with !, add it
            nodeid = "!" + nodeid
    else:
        nodeid = "!" + f"{int(args.nodenum):x}" #if nodenum was used, convert it to hex for nodeid

    ### Convert arguments to variables with proper names to match meshtastic protobuffs
    channelnum = args.channum
    channelname = args.name
    channelpsk = args.psk
    LoraSettings = {}
    LoraSettings['region'] = args.region
    if args.nopreset:
        LoraSettings['use_preset'] = False #This inverts the value to conform with meshtastic, as the argument is backwards (argument disables rather than enables)
    else:
        LoraSettings['use_preset'] = True #default
    LoraSettings['modem_preset'] = args.preset
    LoraSettings['bandwidth'] = args.bandwidth
    LoraSettings['spread_factor'] = args.spread
    LoraSettings['coding_rate'] = args.codingrate
    LoraSettings['frequency_offset'] = args.freqoffset
    LoraSettings['hop_limit'] = args.hoplimit
    LoraSettings['tx_power'] = args.txpwr
    LoraSettings['channel_num'] = args.freqslot
    LoraSettings['override_frequency'] = args.overfreq
    LoraSettings['override_duty_cycle'] = args.overduty
    if args.sx126xoff:
        LoraSettings['sx126x_rx_boosted_gain'] = False #This inverts the value to conform with meshtastic, as the argument is backwards (argument disables rather than enables)
    else:
        LoraSettings['sx126x_rx_boosted_gain'] = True #default
    LoraSettings['ignore_mqtt'] = args.ignoremqtt
    if args.pafanoff:
        LoraSettings['pa_fan_disabled'] = True
    else:
        LoraSettings['pa_fan_disabled'] = "" #default
    LoraSettings['ignore_incoming'] = args.ignore #comma delineated list
if action == "set":
        readableaction = "Set Channel"
elif action == "del":
        readableaction = "Delete Channel"
elif action == "tx":
        readableaction = "Enable TX"



if len(via) > 0:
    if method == "tcp":
        client = TCPInterface(via)
    elif method == "ble":
        client = BLEInterface(via)
    else:
        client = SerialInterface(via)
else:
    client = SerialInterface()
    if client.devPath is None:
        client = TCPInterface("localhost")

for key, value in client.nodes.items():
    if key == nodeid:
        nodeName = value.get('user', {}).get('longName', f'{Fore.LIGHTRED_EX}node name not found in nodeDB{Fore.RESET}')
        break
else:
    nodeName = f'{Fore.LIGHTRED_EX}node ID not in nodeDB{Fore.RESET}'




if len(sys.argv) == 1 or args.confirm: #in prompt mode, ask for confirmation.
    print(f"Send command to {Fore.LIGHTBLUE_EX}{nodeid}{Fore.RESET} ({nodeName})? ({Fore.LIGHTBLUE_EX}y{Fore.RESET}/{Fore.LIGHTBLUE_EX}n{Fore.RESET})")
    i = 0
    key = "X" #initial value for keypress detector
    while key.lower() not in ("y", "n"):
        key = keypress()
        i += 1
        if key.lower() == "y":
            break
        elif key.lower() == "n":
            exitscript()
        elif key == "\x1b": #esc key
                quit()
        else:
            print(f"{Fore.LIGHTRED_EX}You must choose y or n...{Fore.RESET}")
        if i == 3:
            exitscript()

print(f"\nSending \"{Fore.LIGHTBLUE_EX}{readableaction}{Fore.RESET}\" command to {Fore.LIGHTBLUE_EX}{nodeid}{Fore.RESET} ({Fore.LIGHTBLUE_EX}{nodeName}{Fore.RESET}) over {Fore.LIGHTBLUE_EX}{readablemethod}{Fore.RESET}. Will retry up to {Fore.LIGHTBLUE_EX}{maxattempts}{Fore.RESET} times until acknowledgment is received...\n")

if action == "set": #we're adding/setting a channel
    def build_command(index=int(channelnum), role=channel_pb2.Channel.Role.SECONDARY, name=channelname, psk="base64:" + channelpsk):
        ch = channel_pb2.Channel()
        ch.role = role
        ch.index = index
        if role != channel_pb2.Channel.Role.DISABLED:
            if name is not None:
                ch.settings.name = name
            if psk == "base64:":
                psk += "AQ==" #fixes bug when setting channel 0 with no PSK (caused node reboot)
            if psk is not None:
                ch.settings.psk = fromPSK(psk)
        return ch
elif action == "del": #we're deleting a channel
    def build_command(index=int(channelnum), role=channel_pb2.Channel.Role.DISABLED, name=None, psk=None):
        ch = channel_pb2.Channel()
        ch.role = role
        ch.index = index
        if role != channel_pb2.Channel.Role.DISABLED:
            if name is not None:
                ch.settings.name = name
            if psk is not None:
                ch.settings.psk = fromPSK(psk)
        return ch
elif action == "tx": #we're enabling tx
    def build_command():
        command = config_pb2.Config.LoRaConfig()
        command.region = config_pb2.Config.LoRaConfig.RegionCode.Value(LoraSettings['region'].upper())
        if LoraSettings['use_preset']: command.use_preset = LoraSettings['use_preset']
        if LoraSettings['modem_preset']: command.modem_preset = config_pb2.Config.LoRaConfig.ModemPreset.Value(LoraSettings['modem_preset'])
        if LoraSettings.get('bandwidth'): command.bandwidth = int(LoraSettings['bandwidth'])
        if LoraSettings.get('spread_factor'): command.spread_factor = int(LoraSettings['spread_factor']) #should this be a string?
        if LoraSettings.get('coding_rate'): command.coding_rate = int(LoraSettings['coding_rate']) #should this be a string?
        if LoraSettings['frequency_offset']: command.frequency_offset = float(LoraSettings['frequency_offset'])
        if LoraSettings['hop_limit']: command.hop_limit = int(LoraSettings['hop_limit'])
        if LoraSettings['tx_power']: command.tx_power = int(LoraSettings['tx_power'])
        if LoraSettings['channel_num']: command.channel_num = int(LoraSettings['channel_num']) #frequency slot
        if LoraSettings['override_frequency']: command.override_frequency = float(LoraSettings['override_frequency'])
        if LoraSettings['override_duty_cycle']: command.override_duty_cycle = LoraSettings['override_duty_cycle']
        if LoraSettings['sx126x_rx_boosted_gain']: command.sx126x_rx_boosted_gain = LoraSettings['sx126x_rx_boosted_gain']
        if LoraSettings['ignore_mqtt']: command.ignore_mqtt = LoraSettings['ignore_mqtt']
        command.tx_enabled = True #the meat and potatoes
        #ch.pa_fan_disabled = LoraSettings['pa_fan_disabled'] #waiting for library implementation
        try:
            command.ignore_incoming.extend([int(x.strip("!"),16) for x in LoraSettings['ignore_incoming'].split(",")])
        except:
            ""
        return command

### The actual mesh code

def printable_packet(packet):
    ret = f"""
    Packet ID:\t{Fore.LIGHTBLUE_EX}{packet['id']}{Fore.RESET}
    From:\t{Fore.LIGHTBLUE_EX}{packet['from']:08x}{Fore.RESET} (remote node)
    To:\t\t{Fore.LIGHTBLUE_EX}{packet['to']:08x}{Fore.RESET} (you)"""
    #Portnum:\t{Fore.LIGHTBLUE_EX}{packet['decoded']['portnum']}{Fore.RESET}"""
    if 'requestId' in packet['decoded']:
        ret += f"\n    Request ID:\t{Fore.LIGHTBLUE_EX}{packet['decoded']['requestId']}{Fore.RESET}"
    if packet['decoded']['portnum'] == 'ROUTING_APP':
        if not packet['decoded']['routing']['errorReason'] == "NONE":
            colorstart = f"{Fore.LIGHTRED_EX}"
        else:
            colorstart = f"{Fore.LIGHTBLUE_EX}"
        ret += f"\n    Error:\t{colorstart}{packet['decoded']['routing']['errorReason']}{Fore.RESET}"
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
                        print(f"*** Received acknowledgement of channel {Fore.LIGHTBLUE_EX}{channelnum}{Fore.RESET} ***")
                        print(f"************** Took {Fore.LIGHTBLUE_EX}{attempts}{Fore.RESET} attempts **************")
                else:
                    print(f"{Fore.LIGHTRED_EX}Unexpected response:{Fore.RESET} {printable_packet(packet)}")
                    #print(f"*** {Fore.LIGHTRED_EX}THIS IS PROBABLY AN ERROR{Fore.RESET} ***")
                    if packet['decoded']['routing']['errorReason'] == "NO_CHANNEL": print(f"`Error: NO_CHANNEL` indicates that you do not have an admin channel in common with the remote node.\nFor more information, see {Fore.LIGHTBLUE_EX}https://meshtastic.org/docs/configuration/remote-admin/{Fore.RESET}")
                    if packet['decoded']['routing']['errorReason'] == "MAX_RETRANSMIT":
                        print(f"`Error: MAX_RETRANSMIT` Is a nonfatal error that is triggered when no packet relay or acknowledgement is received. It indicates that no other nodes are in range.")
                    else:
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
    ch = build_command(*args, **kwargs)

    p = admin_pb2.AdminMessage()
    if action == "set" or action == "del":
        p.set_channel.CopyFrom(ch)
    elif action == "tx":
        p.set_config.lora.CopyFrom(build_command())

    pkt = sendAdmin(client, p, nodeid)

    requestIds.append(pkt.id)
    print(f"{Fore.LIGHTBLUE_EX}Sent command to remote node (packet ID: {pkt.id}).{Fore.RESET}")
    print("Waiting for acknowledgement...")

if __name__ == "__main__":

    pub.subscribe(onReceive, "meshtastic.receive")
    
    """ if len(via) > 0:
        if method == "tcp":
            client = TCPInterface(via)
        elif method == "ble":
            client = BLEInterface(via)
        else:
            client = SerialInterface(via)
    else:
        client = SerialInterface()
        if client.devPath is None:
            client = TCPInterface("localhost")

    for key, value in client.nodes.items():
        if key == nodeid:
            long_name = value.get('user', {}).get('longName', 'node name not found in nodeDB')
            break
    else:
        long_name = 'node ID not in nodeDB'"""

    sendOnce(client, nodeid)

    i = 0
    attempts = 0
    while not gotResponse:
        if i >= 30:
            attempts += 1
            if attempts > maxattempts:
                errormsg = f"\n{Fore.LIGHTRED_EX}Timed out... Reached max attempts ({maxattempts}).\n{Fore.RESET}"
                exitscript()
            print(f"{Fore.LIGHTRED_EX}Timed out, retrying... (attempt {attempts}/{maxattempts}){Fore.RESET}")
            if action == "set" or action == "del":
                sendOnce(client, nodeid, index=int(channelnum))
            else:
                sendOnce(client, nodeid)

            i = 0
        time.sleep(1)
        i +=1

    try:
        args
    except:
        print(f"\n{Fore.LIGHTBLUE_EX}Press any key to exit...{Fore.RESET}")
        keypress()

    client.close()
