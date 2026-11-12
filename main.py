import os
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from ui.field import create_field_figure
from ui.app import App

root = tk.Tk()
root.title("PRISM Path Planner")
root.configure(bg='#111')

# Pack the fixed-width side panel first so the field can never squeeze it.
right_frame = tk.Frame(root, width=220, bg='#111')
right_frame.pack(side=tk.RIGHT, fill=tk.Y)
right_frame.pack_propagate(False)

left_frame = tk.Frame(root, bg='#111')
left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

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

file_row = tk.Frame(right_frame, bg='#111')
file_row.pack(pady=(10, 4), padx=12, fill=tk.X)
file_buttons = {}
for i, name in enumerate(("NEW", "OPEN", "SAVE")):
    b = tk.Button(file_row, text=name, **button_style, pady=4)
    b.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0 if i == 0 else 2, 0))
    file_buttons[name] = b

# Waypoint fields, two per row: (x, y) and (tangent dx, dy)
entries = {}
for row_keys, row_labels in ((('x', 'y'), ("x", "y")), (('dx', 'dy'), ("tangent dx", "tangent dy"))):
    row = tk.Frame(right_frame, bg='#111')
    row.pack(pady=(6, 0), padx=12, fill=tk.X)
    for col, (key, label) in enumerate(zip(row_keys, row_labels)):
        row.columnconfigure(col, weight=1, uniform='wp')
        tk.Label(row, text=label, **label_style).grid(row=0, column=col, pady=(0, 2))
        e = tk.Entry(row, width=8, **entry_style)
        e.grid(row=1, column=col, sticky='ew', padx=(0, 2) if col == 0 else (2, 0))
        entries[key] = e

fig, ax, profile_ax = create_field_figure()

canvas = FigureCanvasTkAgg(fig, master=left_frame)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

tk.Label(left_frame,
         text="click: add/select   drag: move   drag ■: tangent   shift+click path: insert\n"
              "right-click/Del: delete   Esc: deselect   hold ctrl: snap   ctrl+z / ctrl+y: undo / redo\n"
              "ctrl+n: new   ctrl+o: open   ctrl+s: save   ctrl+shift+s: save as\n"
              "space / PLAY: play back path   hover speed plot: scrub",
         bg='#111', fg='#666', font=('Courier', 8)).pack(side=tk.BOTTOM, pady=(0, 6))

play_button = tk.Button(left_frame, text="▶ PLAY", **button_style, pady=4, width=12)
play_button.pack(side=tk.BOTTOM, pady=(0, 4))

edit_row = tk.Frame(right_frame, bg='#111')
edit_row.pack(pady=(16, 0), padx=12, fill=tk.X)
apply_button = tk.Button(edit_row, text="APPLY", **button_style, pady=8)
apply_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
reset_button = tk.Button(edit_row, text="AUTO TAN", **button_style, pady=8)
reset_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))

# Robot settings
tk.Label(right_frame, text="ROBOT", bg='#111', fg='#4fc', font=('Courier', 10, 'bold')).pack(pady=(20, 0))
settings_entries = {}
for name, label in App.SETTINGS_FIELDS:
    tk.Label(right_frame, text=label, **label_style).pack(pady=(6, 2))
    e = tk.Entry(right_frame, **entry_style)
    e.pack(padx=12, fill=tk.X)
    settings_entries[name] = e

settings_button = tk.Button(right_frame, text="APPLY SETTINGS", **button_style, pady=8)
settings_button.pack(pady=(12, 0), padx=12, fill=tk.X)

stats_var = tk.StringVar()
tk.Label(right_frame, textvariable=stats_var, justify=tk.LEFT, anchor='w',
         **label_style).pack(pady=(16, 0), padx=12, fill=tk.X)

config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "robot_config.json")
app = App(root, fig, ax, canvas, entries, settings_entries, stats_var, config_path,
          profile_ax=profile_ax)
app.update_stats()
apply_button.configure(command=app.on_apply)
reset_button.configure(command=app.reset_tangent)
file_buttons["NEW"].configure(command=app.new_path)
file_buttons["OPEN"].configure(command=app.open_path)
file_buttons["SAVE"].configure(command=app.save)
settings_button.configure(command=app.on_apply_settings)
play_button.configure(command=app.toggle_play)
app.on_play_state = lambda playing: play_button.configure(text="■ STOP" if playing else "▶ PLAY")

tk.Frame(right_frame, bg='#111').pack(fill=tk.BOTH, expand=True)

tk.Button(right_frame, text="EXPORT .bin", **button_style,
          command=app.on_export, pady=10).pack(pady=(0, 4), padx=12, fill=tk.X)

tk.Button(right_frame, text="EXPORT .hpp", **button_style,
          command=app.on_export_header, pady=10).pack(pady=(0, 16), padx=12, fill=tk.X)

fig.canvas.mpl_connect('button_press_event', app.on_click)
fig.canvas.mpl_connect('motion_notify_event', app.on_drag)
fig.canvas.mpl_connect('button_release_event', app.on_release)
fig.canvas.mpl_connect('key_press_event', app.on_key)
# Focus the field on click so Delete/Escape reach it instead of a text entry.
fig.canvas.mpl_connect('button_press_event', lambda e: canvas.get_tk_widget().focus_set())

for seq in ('<Control-z>', '<Control-Z>'):
    root.bind(seq, lambda e: app.redo() if e.state & 0x1 else app.undo())  # ctrl+shift+z = redo
root.bind('<Control-y>', app.redo)
root.bind('<Control-n>', app.new_path)
root.bind('<Control-o>', app.open_path)
root.bind('<Control-s>', app.save)
root.bind('<Control-S>', app.save_as)  # ctrl+shift+s

root.protocol("WM_DELETE_WINDOW", app.on_quit)
root.minsize(800, 720)
root.mainloop()
