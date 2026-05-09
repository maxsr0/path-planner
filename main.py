import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from ui.field import create_field_figure
from ui.app import App

root = tk.Tk()
root.title("PRISM Path Planner")
root.configure(bg='#1a1a2e')

left_frame = tk.Frame(root, bg='#1a1a2e')
left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

right_frame = tk.Frame(root, bg='#111')
right_frame.pack(side=tk.RIGHT, fill=tk.BOTH)

tk.Label(right_frame, text="x position", bg='#111', fg='#aaa').pack()
x_entry = tk.Entry(right_frame)
x_entry.pack()

tk.Label(right_frame, text="y position", bg='#111', fg='#aaa').pack()
y_entry = tk.Entry(right_frame)
y_entry.pack()

tk.Label(right_frame, text="dx", bg='#111', fg='#aaa').pack()
dx_entry = tk.Entry(right_frame)
dx_entry.pack()

tk.Label(right_frame, text="dy", bg='#111', fg='#aaa').pack()
dy_entry = tk.Entry(right_frame)
dy_entry.pack()

entries = {
    'x': x_entry,
    'y': y_entry,
    'dx': dx_entry,
    'dy': dy_entry
}

fig, ax = create_field_figure()

canvas = FigureCanvasTkAgg(fig, master=left_frame)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


app = App(root, fig, ax, canvas, entries)

tk.Button(right_frame, text="Apply", bg='#111', fg='#aaa', command=app.on_apply).pack()

fig.canvas.mpl_connect('button_press_event', app.on_click)
fig.canvas.mpl_connect('motion_notify_event', app.on_drag)
fig.canvas.mpl_connect('button_release_event', app.on_release)

root.mainloop()
