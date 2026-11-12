import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from ui.field import create_field_figure
from ui.app import App

root = tk.Tk()
root.title("PRISM Path Planner")
root.configure(bg='#111')

left_frame = tk.Frame(root, bg='#111')
left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

right_frame = tk.Frame(root, width=220, bg='#111')
right_frame.pack(side=tk.RIGHT, fill=tk.Y)
right_frame.pack_propagate(False)

entry_style = {
    'bg': '#222',
    'fg': '#4fc',
    'insertbackground': '#4fc',
    'relief': 'flat',
    'font': ('Courier', 10)
}

label_style = {
    'bg': '#111',
    'fg': '#aaa',
    'font': ('Courier', 9)
}

button_style = {
    'bg': '#1a1a1a',
    'fg': '#4fc',
    'activebackground': '#222',
    'activeforeground': '#4fc',
    'relief': 'flat',
    'font': ('Courier', 10),
    'cursor': 'hand2',
    'borderwidth': 0,
    'highlightthickness': 1,
    'highlightbackground': '#333'
}

tk.Label(right_frame, text="x position", **label_style).pack(pady=(8, 2))
x_entry = tk.Entry(right_frame, **entry_style)
x_entry.pack(padx=12, fill=tk.X)

tk.Label(right_frame, text="y position", **label_style).pack(pady=(8, 2))
y_entry = tk.Entry(right_frame, **entry_style)
y_entry.pack(padx=12, fill=tk.X)

tk.Label(right_frame, text="dx position", **label_style).pack(pady=(8, 2))
dx_entry = tk.Entry(right_frame, **entry_style)
dx_entry.pack(padx=12, fill=tk.X)

tk.Label(right_frame, text="dy position", **label_style).pack(pady=(8, 2))
dy_entry = tk.Entry(right_frame, **entry_style)
dy_entry.pack(padx=12, fill=tk.X)

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

tk.Button(right_frame, text="APPLY", **button_style,
          command=app.on_apply, pady=8).pack(pady=(16, 0), padx=12, fill=tk.X)

tk.Frame(right_frame, bg='#111').pack(fill=tk.BOTH, expand=True)

tk.Button(right_frame, text="EXPORT .bin", **button_style,
          command=app.on_export, pady=10).pack(pady=(0, 4), padx=12, fill=tk.X)

tk.Button(right_frame, text="EXPORT .hpp", **button_style,
          command=app.on_export_header, pady=10).pack(pady=(0, 16), padx=12, fill=tk.X)

fig.canvas.mpl_connect('button_press_event', app.on_click)
fig.canvas.mpl_connect('motion_notify_event', app.on_drag)
fig.canvas.mpl_connect('button_release_event', app.on_release)

root.protocol("WM_DELETE_WINDOW", root.quit)
root.minsize(800, 600)
root.mainloop()
