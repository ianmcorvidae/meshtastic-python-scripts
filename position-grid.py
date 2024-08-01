from bitstring import BitArray
from decimal import Decimal
import sys

def _clamp(ll_int, precision):
    barr = BitArray(int=ll_int, length=32)
    clamped = BitArray(bin=(barr.bin[0:precision] + '0'*(32-precision)))
    return clamped.int

def return_position_bounds(precision, lat, lon):
    "Given a precision (1-32) and lat/lon, return bounds as (min_lat, max_lat, min_lon, max_lon)"
    scale_up = Decimal("1e7")
    scale_down = Decimal("1e-7")
    lat_i = int(lat*scale_up)
    lon_i = int(lon*scale_up)
    mod = 1<<(31-precision)
    c_lat = _clamp(lat_i, precision)
    c_lon = _clamp(lon_i, precision)
    return tuple([x*scale_down for x in (c_lat, c_lat+2*mod, c_lon, c_lon+2*mod)])

if __name__ == "__main__":
    lat = Decimal(sys.argv[1])
    lon = Decimal(sys.argv[2])
    precision = int(sys.argv[3])
    print(return_position_bounds(precision, lat, lon))
