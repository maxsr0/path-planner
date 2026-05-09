import struct


def export_trajectory(trajectory, filepath):
    with open(filepath, 'wb') as f:
        f.write(struct.pack('i', len(trajectory)))
        for i in range(len(trajectory)):
            f.write(struct.pack('4f', trajectory[i][0], trajectory[i][1], trajectory[i][2], trajectory[i][3]))


def import_trajectory(filepath):
    trajectory = []
    with open(filepath, 'rb') as f:
        count = struct.unpack('i', f.read(4))[0]
        for _ in range(count):
            point = struct.unpack('4f', f.read(16))
            trajectory.append(point)

    return trajectory
