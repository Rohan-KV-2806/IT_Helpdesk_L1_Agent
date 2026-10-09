import tkinter as tk

root = tk.Tk()
root.title("Test Application")
root.geometry("500x300")

label = tk.Label(
    root,
    text="Application is running...",
    font=("Arial", 16)
)
label.pack(expand=True)

def freeze():

    while True:
        pass

root.after(2000, freeze)

root.mainloop()