from meshtastic.serial_interface import SerialInterface
from datetime import datetime
import timeago
import json

client = SerialInterface()

def formatFloat(value, precision=2, unit=""):
    """Format a float value with precision."""
    return f"{value:.{precision}f}{unit}" if value else None

def getLH(ts):
    """Format last heard"""
    return (
        datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else None
    )

def getTimeAgo(ts):
    """Format how long ago have we heard from this node (aka timeago)."""
    return (
        timeago.format(datetime.fromtimestamp(ts), datetime.now())
        if ts
        else None
    )

if client.nodesByNum:
    for node in client.nodesByNum.values():
        row = {"User": f"UNK: {node['num']}", "ID": f"!{node['num']:x}"}

        user = node.get("user")
        if user:
            row.update(
                {
                    "User": user.get("longName", "N/A"),
                    "AKA": user.get("shortName", "N/A"),
                    "ID": user["id"],
                }
            )

        pos = node.get("position")
        if pos:
            row.update(
                {
                    "Latitude": formatFloat(pos.get("latitude"), 4, "°"),
                    "Longitude": formatFloat(pos.get("longitude"), 4, "°"),
                    "Altitude": formatFloat(pos.get("altitude"), 0, " m"),
                }
            )

        metrics = node.get("deviceMetrics")
        if metrics:
            batteryLevel = metrics.get("batteryLevel")
            if batteryLevel is not None:
                if batteryLevel == 0:
                    batteryString = "Powered"
                else:
                    batteryString = str(batteryLevel) + "%"
                row.update({"Battery": batteryString})
            row.update(
                {
                    "Channel util.": formatFloat(
                        metrics.get("channelUtilization"), 2, "%"
                    ),
                    "Tx air util.": formatFloat(
                        metrics.get("airUtilTx"), 2, "%"
                    ),
                }
            )

        row.update(
            {
                "SNR": formatFloat(node.get("snr"), 2, " dB"),
                "Channel": node.get("channel"),
                "LastHeard": getLH(node.get("lastHeard")),
                "Since": getTimeAgo(node.get("lastHeard")),
            }
        )

        print(json.dumps(row))
