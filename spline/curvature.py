import numpy as np


def curvature_at_point(a, b, c):
    # κ = 2 * |cross(B-A, C-A)| / (|AB| * |BC| * |AC|)
    npa = np.array(a)
    npb = np.array(b)
    npc = np.array(c)

    ab = npb - npa
    ac = npc - npa

    AB = np.linalg.norm(npb - npa)
    AC = np.linalg.norm(npc - npa)
    BC = np.linalg.norm(npb - npc)

    denominator = AB * BC * AC
    if denominator == 0:
        return 0

    cross = ab[0] * ac[1] - ab[1] * ac[0]  # 2-D scalar cross (np.cross on 2-D is removed in NumPy 2)
    kappa = (2 * abs(cross)) / denominator

    return kappa


def curvature_profile(path):
    curvatures = [0] * len(path)
    for i in range(1, len(path) - 1):
        curvatures[i] = curvature_at_point(path[i-1], path[i], path[i+1])

    curvatures[0] = 0
    curvatures[len(path) - 1] = 0

    return curvatures
