# main.py
import tkinter as tk
from logic import Simulator
from ui_tk import FlexiCityApp

def main():
    root = tk.Tk()
    sim = Simulator()
    app = FlexiCityApp(root, sim)
    root.mainloop()

if __name__ == "__main__":
    main()
