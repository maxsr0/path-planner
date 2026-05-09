from spline.hermite import sample_hermite_path
from spline.curvature import curvature_profile
from profiler.velocity_profiler import velocity_profile
from profiler.velocity_profiler import compute_timestamps


def generate_trajectory(waypoints, tangents, num_points_per_segment, v_max, a_max):
    path = sample_hermite_path(waypoints, tangents, num_points_per_segment)
    curvatures = curvature_profile(path)
    velocities = velocity_profile(path, curvatures, v_max, a_max)
    timestamps = compute_timestamps(path, velocities)

    return [(x, y, v, t) for (x, y), v, t in zip(path, velocities, timestamps)]
