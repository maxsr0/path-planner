import struct

# Explicit little-endian, standard sizes (int32 + 4x float32) to match the
# V5 brain's fread() layout in traj_loader.cpp regardless of host platform.
COUNT_FMT = '<i'
POINT_FMT = '<4f'


def export_trajectory(trajectory, filepath):
    with open(filepath, 'wb') as f:
        f.write(struct.pack(COUNT_FMT, len(trajectory)))
        for x, y, v, t in trajectory:
            f.write(struct.pack(POINT_FMT, x, y, v, t))


def import_trajectory(filepath):
    trajectory = []
    with open(filepath, 'rb') as f:
        count = struct.unpack(COUNT_FMT, f.read(struct.calcsize(COUNT_FMT)))[0]
        size = struct.calcsize(POINT_FMT)
        for _ in range(count):
            trajectory.append(struct.unpack(POINT_FMT, f.read(size)))

    return trajectory
