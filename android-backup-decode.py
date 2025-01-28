from meshtastic.protobuf import clientonly_pb2
import sys

dp = clientonly_pb2.DeviceProfile()
with open(sys.argv[1], 'br') as f:
    protocontent = f.read()

dp.ParseFromString(protocontent)
print(dp)
