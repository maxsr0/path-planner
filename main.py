import math

import matplotlib.pyplot as plt
from ui.field import create_field_figure
from ui.waypoint import Waypoint
from spline.hermite import sample_hermite_path

fig, ax = create_field_figure()

waypoints = []
dot_artists = []

spline_line = None
selected_waypoint = None
is_dragging = False


def check_distance(click_x, click_y, w):
    # c represents click waypoint, w represents waypoint
    # within area of circle so if (x-xc)^2 + (y-yc)^2 <=  r^2 (r =5) then we are selecting the point
    r = 5
    return math.pow(w.x - click_x, 2) + math.pow(w.y - click_y, 2) <= math.pow(r,2)


def draw_spline(wps):
    if len(wps) < 2:
        return

    points = [(w.x, w.y) for w in wps]
    tangents = [(w.dx, w.dy) for w in wps]

    path = sample_hermite_path(points, tangents, 20)
    xs, ys = zip(*path)

    global spline_line
    spline_line = ax.plot(xs, ys, '-', color='black')[0]


def draw_waypoint(w):
    dot = ax.plot(w.x, w.y, 'o', color='black')[0]
    dot_artists.append(dot)


def draw_all():
    global spline_line
    if spline_line is not None:
        spline_line.remove()

    for d in dot_artists:
        d.remove()
    dot_artists.clear()

    for w in waypoints:
        draw_waypoint(w)

    draw_spline(waypoints)

    fig.canvas.draw()


def compute_tangents():
    for i in range(1, len(waypoints) - 1):
        waypoints[i].auto_tangent(waypoints[i - 1], waypoints[i + 1])

    if len(waypoints) >= 2:
        waypoints[0].dx = waypoints[1].x - waypoints[0].x
        waypoints[0].dy = waypoints[1].y - waypoints[0].y
        waypoints[-1].dx = waypoints[-1].x - waypoints[-2].x
        waypoints[-1].dy = waypoints[-1].y - waypoints[-2].y

def on_click(event):
    global selected_waypoint, is_dragging
    if event.xdata is None or event.ydata is None:
        return

    for w in waypoints:
        if check_distance(event.xdata, event.ydata, w):
            is_dragging = True
            selected_waypoint = w
            return

    w = Waypoint(event.xdata, event.ydata)
    waypoints.append(w)

    compute_tangents()

    draw_all()


def on_drag(event):
    global is_dragging, selected_waypoint

    if not is_dragging or selected_waypoint is None:
        return
    if event.xdata is None or event.ydata is None:
        return

    selected_waypoint.x = event.xdata
    selected_waypoint.y = event.ydata

    compute_tangents()

    draw_all()


def on_release(event):
    global is_dragging, selected_waypoint
    is_dragging = False
    selected_waypoint = None


fig.canvas.mpl_connect('button_press_event', on_click)
fig.canvas.mpl_connect('motion_notify_event', on_drag)
fig.canvas.mpl_connect('button_release_event', on_release)

ax.plot()

plt.show()
