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
    # Intentionally freeze the GUI thread
    while True:
        pass

# Give Windows time to display the window first
root.after(2000, freeze)

root.mainloop()