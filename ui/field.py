import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


def draw_field(ax):
    ax.add_patch(Rectangle((0, 0), 144, 144, color="#0d1117"))
    ax.grid()
    ax.tick_params(colors='#555')
    ax.spines['bottom'].set_color('#333')
    ax.spines['top'].set_color('#333')
    ax.spines['left'].set_color('#333')
    ax.spines['right'].set_color('#333')
    ax.set_xticks([24, 48, 72, 96, 120, 144])
    ax.set_yticks([24, 48, 72, 96, 120, 144])
    ax.set_xlim(0, 144)
    ax.set_ylim(0, 144)
    ax.set_aspect('equal')


def create_field_figure():
    fig, ax = plt.subplots()
    draw_field(ax)
    return fig, ax