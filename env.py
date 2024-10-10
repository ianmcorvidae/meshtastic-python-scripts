#!/usr/bin/env python3

import meshtastic.serial_interface, meshtastic.tcp_interface, meshtastic.ble_interface
try:
    from meshtastic.protobuf import telemetry_pb2, portnums_pb2
except ImportError:
    from meshtastic import telemetry_pb2, portnums_pb2

import argparse
import sys
import time

parser = argparse.ArgumentParser(
        add_help=False,
        epilog="If no connection arguments are specified, we attempt a serial connection and then a TCP connection to localhost.")

connOuter = parser.add_argument_group('Connection', 'Optional arguments to specify a device to connect to and how.')
conn = connOuter.add_mutually_exclusive_group()
conn.add_argument(
    "--port",
    "--serial",
    "-s",
    help="The port to connect to via serial, e.g. `/dev/ttyUSB0`.",
    nargs="?",
    default=None,
    const=None,
)
conn.add_argument(
    "--host",
    "--tcp",
    "-t",
    help="The hostname or IP address to connect to using TCP.",
    nargs="?",
    default=None,
    const="localhost",
)
conn.add_argument(
    "--ble",
    "-b",
    help="The BLE device MAC address or name to connect to.",
    nargs="?",
    default=None,
    const="any"
)

parser.add_argument('nodeid')

args = parser.parse_args()

if args.ble:
    interface = meshtastic.ble_interface.BLEInterface(args.ble if args.ble != "any" else None)
elif args.host:
    interface = meshtastic.tcp_interface.TCPInterface(args.host)
else:
    try:
        interface = meshtastic.serial_interface.SerialInterface(args.port)
    except PermissionError as ex:
        print("You probably need to add yourself to the `dialout` group to use a serial connection.")
    if interface.devPath is None:
        interface = meshtastic.tcp_interface.TCPInterface("localhost")

print(f"Sending environment metrics request to {args.nodeid}")

t = telemetry_pb2.Telemetry()
t.environment_metrics.CopyFrom(telemetry_pb2.EnvironmentMetrics())

gotresp = False
def onresp(packet):
    global gotresp
    print(packet)
    gotresp = True

interface.sendData(
        t,
        destinationId=args.nodeid,
        portNum=portnums_pb2.PortNum.TELEMETRY_APP,
        wantResponse=True,
        onResponse=onresp,
    )

while not gotresp:
    time.sleep(1)
