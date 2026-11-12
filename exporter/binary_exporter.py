import struct

from profiler.trajectory import TrajectoryPoint

# File layout (all little-endian, matching traj_loader.cpp on the V5 brain):
#   char[4]  magic "PRTJ"
#   uint32   format version
#   uint32   point count
#   N x float32[7]: x, y, theta, velocity, omega, curvature, timestamp
MAGIC = b'PRTJ'
VERSION = 2
HEADER_FMT = '<4sII'
POINT_FMT = '<7f'


def export_trajectory(trajectory, filepath):
    with open(filepath, 'wb') as f:
        f.write(struct.pack(HEADER_FMT, MAGIC, VERSION, len(trajectory)))
        for p in trajectory:
            f.write(struct.pack(POINT_FMT, *p))


def import_trajectory(filepath):
    with open(filepath, 'rb') as f:
        magic, version, count = struct.unpack(HEADER_FMT, f.read(struct.calcsize(HEADER_FMT)))
        if magic != MAGIC:
            raise ValueError(f"{filepath} is not a PRISM trajectory file")
        if version != VERSION:
            raise ValueError(f"unsupported trajectory version {version} (expected {VERSION})")
        size = struct.calcsize(POINT_FMT)
        return [TrajectoryPoint(*struct.unpack(POINT_FMT, f.read(size))) for _ in range(count)]
