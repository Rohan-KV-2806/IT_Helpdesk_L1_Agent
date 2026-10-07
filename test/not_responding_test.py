import tkinter as tk
import time

# Simple Windows "Not Responding" test app.
# Run this file normally with Python.
# The window becomes unresponsive after 3 seconds and stays frozen
# until you terminate it from Task Manager.

root = tk.Tk()
root.title("Not Responding Test App")
root.geometry("420x220")

label = tk.Label(
    root,
    text="This app will become NOT RESPONDING\nin 3 seconds.",
    font=("Segoe UI", 14),
)
label.pack(expand=True)

def freeze_app():
    label.config(text="Freezing now...")
    root.update()

    # Intentionally block Tkinter's main/UI thread.
    # Windows should eventually mark the window as "Not Responding".
    while True:
        time.sleep(1)

root.after(3000, freeze_app)

root.mainloop()
