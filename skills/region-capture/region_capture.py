#!/usr/bin/env python3
"""
Tool to capture regions around the mouse and build an AI screen map.

Controls:
  + / =     : Increase overall size (+1px)
  -         : Decrease overall size (-1px)
  x / X     : Increase/Decrease width (+/-1px)
  y / Y     : Increase/Decrease height (+/-1px)
  f         : FREEZE mode - freeze screen, move border, click to capture
  c / Space : Direct capture (without freeze)
  r         : Reset size (200x200)
  q / ESC   : Exit

Filename format: {name}_{x}_{y}.png
Elements: elements.json (JSON format for AI agents)
"""
import sys
import os
from datetime import datetime
import threading
import time
import signal
import csv
import re
import json
from data_paths import (
    LOCAL_DATA_DIR,
    ELEMENTS_FILE as DEFAULT_ELEMENTS_FILE,
    CAPTURES_DIR as DEFAULT_CAPTURES_DIR,
    ensure_local_data,
)

try:
    from pynput import keyboard
except ImportError:
    print("ERROR: pip install pynput")
    sys.exit(1)

try:
    from PIL import Image, ImageDraw, ImageTk, ImageGrab
    import tkinter as tk
except ImportError:
    print("ERROR: pip install Pillow")
    sys.exit(1)

try:
    import pyautogui
except ImportError:
    print("ERROR: pip install pyautogui")
    sys.exit(1)

# Config
DEFAULT_WIDTH = 200
DEFAULT_HEIGHT = 200
MIN_SIZE = 10
MAX_SIZE = 1000
SIZE_STEP = 1

# Parse arguments before defining paths
import argparse
parser = argparse.ArgumentParser(description='Capture screen regions')
parser.add_argument('--data-dir', help='Directory to store captures and map')
_args, _ = parser.parse_known_args()

# By default use skill data/local; --data-dir overrides it.
if _args.data_dir:
    DATA_DIR = os.path.abspath(os.path.expanduser(_args.data_dir))
    CAPTURES_DIR = os.path.join(DATA_DIR, 'captures')
    ELEMENTS_FILE = os.path.join(DATA_DIR, 'elements.json')
    os.makedirs(CAPTURES_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(ELEMENTS_FILE), exist_ok=True)
else:
    ensure_local_data()
    DATA_DIR = str(LOCAL_DATA_DIR)
    CAPTURES_DIR = str(DEFAULT_CAPTURES_DIR)
    ELEMENTS_FILE = str(DEFAULT_ELEMENTS_FILE)

def sanitize_filename(name):
    """Converts a name to a valid filename format."""
    # Replace spaces with underscores
    name = name.strip().replace(' ', '_')
    # Remove special characters
    name = re.sub(r'[^\w\-]', '', name)
    # Limit length
    return name[:50] if name else 'capture'


# ============================================
# FUNCTIONS FOR ELEMENTS.JSON
# ============================================

def load_elements() -> dict:
    """Loads elements from JSON."""
    if not os.path.exists(ELEMENTS_FILE):
        return {}
    with open(ELEMENTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_elements(elements: dict):
    """Saves elements to JSON."""
    with open(ELEMENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(elements, f, indent=2, ensure_ascii=False)


def get_element_names() -> list:
    """Returns list of existing element names."""
    elements = load_elements()
    return list(elements.keys())


def add_image_to_element(element_name: str, image_file: str, description: str = "", tags: list = None):
    """Adds an image to an existing element or creates a new one."""
    elements = load_elements()
    name_key = element_name.lower().replace(' ', '_')
    
    if name_key in elements:
        # Add image to existing element
        if image_file not in elements[name_key]['images']:
            elements[name_key]['images'].append(image_file)
    else:
        # Create new element
        elements[name_key] = {
            "name": name_key,
            "description": description,
            "images": [image_file],
            "tags": tags or []
        }
    
    save_elements(elements)
    return elements[name_key]


def count_elements() -> int:
    """Counts elements in JSON."""
    return len(load_elements())


def ask_capture_info():
    """Asks for name and description. Allows adding to an existing element."""
    result = {'name': None, 'description': None, 'tags': None, 'is_new': True}
    
    root = tk.Tk()
    root.title("Capture information")
    root.attributes('-topmost', True)
    root.geometry("550x400")
    root.configure(bg='#2d2d2d')
    
    # Center window
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - 275
    y = (root.winfo_screenheight() // 2) - 200
    root.geometry(f"+{x}+{y}")
    
    # Load existing elements
    existing_elements = get_element_names()
    
    # === Selector: New or Existing ===
    mode_var = tk.StringVar(value="new")
    
    mode_frame = tk.Frame(root, bg='#2d2d2d')
    mode_frame.pack(pady=(15, 5))
    
    rb_new = tk.Radiobutton(
        mode_frame, text="Create new element", variable=mode_var, value="new",
        bg='#2d2d2d', fg='white', selectcolor='#444444', font=('Sans', 10),
        activebackground='#2d2d2d', activeforeground='white'
    )
    rb_new.pack(side=tk.LEFT, padx=10)
    
    rb_existing = tk.Radiobutton(
        mode_frame, text="Add to existing", variable=mode_var, value="existing",
        bg='#2d2d2d', fg='white', selectcolor='#444444', font=('Sans', 10),
        activebackground='#2d2d2d', activeforeground='white'
    )
    rb_existing.pack(side=tk.LEFT, padx=10)
    
    # === Frame for existing element ===
    existing_frame = tk.Frame(root, bg='#2d2d2d')
    
    lbl_existing = tk.Label(
        existing_frame, text="Select element:",
        bg='#2d2d2d', fg='white', font=('Sans', 11)
    )
    lbl_existing.pack(pady=(5, 5))
    
    # Element listbox
    listbox_frame = tk.Frame(existing_frame, bg='#2d2d2d')
    listbox_frame.pack(pady=5)
    
    scrollbar = tk.Scrollbar(listbox_frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    listbox = tk.Listbox(
        listbox_frame, font=('Sans', 10), width=45, height=6,
        yscrollcommand=scrollbar.set
    )
    listbox.pack(side=tk.LEFT)
    scrollbar.config(command=listbox.yview)
    
    for elem in existing_elements:
        listbox.insert(tk.END, elem)
    
    # === Frame for new element ===
    new_frame = tk.Frame(root, bg='#2d2d2d')
    
    # Name
    lbl_name = tk.Label(
        new_frame, text="Name (this becomes the filename):",
        bg='#2d2d2d', fg='white', font=('Sans', 11)
    )
    lbl_name.pack(pady=(5, 5))
    
    hint_name = tk.Label(
        new_frame, text="(e.g. btn_save, chrome_icon, search_field)",
        bg='#2d2d2d', fg='#888888', font=('Sans', 9)
    )
    hint_name.pack()
    
    entry_name = tk.Entry(new_frame, font=('Sans', 12), width=45)
    entry_name.pack(pady=5)
    
    # Description
    lbl_desc = tk.Label(
        new_frame, text="Description (so the AI understands what it is):",
        bg='#2d2d2d', fg='white', font=('Sans', 11)
    )
    lbl_desc.pack(pady=(10, 5))
    
    entry_desc = tk.Entry(new_frame, font=('Sans', 12), width=45)
    entry_desc.pack(pady=5)
    
    # Tags
    lbl_tags = tk.Label(
        new_frame, text="Tags (comma-separated, for search):",
        bg='#2d2d2d', fg='white', font=('Sans', 11)
    )
    lbl_tags.pack(pady=(10, 5))
    
    hint_tags = tk.Label(
        new_frame, text="(ej: browser, button, whatsapp)",
        bg='#2d2d2d', fg='#888888', font=('Sans', 9)
    )
    hint_tags.pack()
    
    entry_tags = tk.Entry(new_frame, font=('Sans', 12), width=45)
    entry_tags.pack(pady=5)
    
    def update_mode(*args):
        """Shows/hides frames based on selected mode."""
        if mode_var.get() == "new":
            existing_frame.pack_forget()
            new_frame.pack(pady=10)
            entry_name.focus_set()
        else:
            new_frame.pack_forget()
            existing_frame.pack(pady=10)
            listbox.focus_set()
    
    mode_var.trace('w', update_mode)
    new_frame.pack(pady=10)  # Show "new" mode by default
    entry_name.focus_set()
    
    def on_submit(event=None):
        if mode_var.get() == "new":
            result['name'] = entry_name.get().strip()
            result['description'] = entry_desc.get().strip()
            tags_str = entry_tags.get().strip()
            result['tags'] = [t.strip() for t in tags_str.split(',') if t.strip()] if tags_str else []
            result['is_new'] = True
        else:
            selection = listbox.curselection()
            if selection:
                result['name'] = listbox.get(selection[0])
                result['is_new'] = False
            else:
                return  # No selection
        root.destroy()
        
    def on_cancel(event=None):
        root.destroy()
    
    # Buttons
    btn_frame = tk.Frame(root, bg='#2d2d2d')
    btn_frame.pack(pady=15, side=tk.BOTTOM)
    
    btn_ok = tk.Button(btn_frame, text="Save", command=on_submit, width=12)
    btn_ok.pack(side=tk.LEFT, padx=5)
    
    btn_cancel = tk.Button(btn_frame, text="Cancel", command=on_cancel, width=12)
    btn_cancel.pack(side=tk.LEFT, padx=5)
    
    # Key bindings
    entry_name.bind('<Return>', lambda e: entry_desc.focus_set())
    entry_desc.bind('<Return>', lambda e: entry_tags.focus_set())
    entry_tags.bind('<Return>', on_submit)
    listbox.bind('<Double-1>', on_submit)
    root.bind('<Escape>', on_cancel)
    
    root.mainloop()
    
    return result['name'], result['description'], result['tags'], result['is_new']


class FreezeCapture:
    """Freezes the screen and lets the user select a region with a visual border."""
    
    def __init__(self, width, height, on_done):
        self.width = width
        self.height = height
        self.on_done = on_done
        self.result = None
        self.last_x = 0
        self.last_y = 0
        
    def run(self):
        """Runs freeze mode."""
        # Take screenshot
        screenshot = ImageGrab.grab()
        
        # Create window
        root = tk.Tk()
        root.attributes('-fullscreen', True)
        root.attributes('-topmost', True)
        root.config(cursor="crosshair")
        
        # Canvas with screenshot
        photo = ImageTk.PhotoImage(screenshot)
        canvas = tk.Canvas(root, highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_image(0, 0, anchor=tk.NW, image=photo)
        
        # Border elements
        rect_id = [None]
        cross_h = [None]
        cross_v = [None]
        
        # Info bar - movable
        info_x = [10]
        info_y = [10]
        dragging_info = [False]
        drag_offset = [0, 0]
        
        info = tk.Label(
            root, 
            text=f"Region: {self.width}x{self.height} | +/-=Size | x/X y/Y=Axes | Click=Capture | ESC=Cancel",
            bg='#333333', fg='white', font=('Mono', 11), padx=10, pady=5,
            cursor="fleur"  # Move cursor
        )
        info.place(x=info_x[0], y=info_y[0])
        
        # Functions to drag the info bar
        def info_start_drag(event):
            dragging_info[0] = True
            drag_offset[0] = event.x
            drag_offset[1] = event.y
        
        def info_drag(event):
            if dragging_info[0]:
                new_x = info.winfo_x() + event.x - drag_offset[0]
                new_y = info.winfo_y() + event.y - drag_offset[1]
                info.place(x=new_x, y=new_y)
                info_x[0] = new_x
                info_y[0] = new_y
        
        def info_stop_drag(event):
            dragging_info[0] = False
        
        # Bindings for dragging the info bar
        info.bind('<Button-1>', info_start_drag)
        info.bind('<B1-Motion>', info_drag)
        info.bind('<ButtonRelease-1>', info_stop_drag)
        
        # State
        captured = [False]
        capture_data = [None, None, None]  # image, x, y
        
        def draw_border(x, y):
            """Draws border at the given position."""
            self.last_x = x
            self.last_y = y
            
            half_w = self.width // 2
            half_h = self.height // 2
            
            # Clear previous
            if rect_id[0]: canvas.delete(rect_id[0])
            if cross_h[0]: canvas.delete(cross_h[0])
            if cross_v[0]: canvas.delete(cross_v[0])
            
            # Draw border
            rect_id[0] = canvas.create_rectangle(
                x - half_w, y - half_h, 
                x + half_w, y + half_h,
                outline='#FF0000', width=2
            )
            
            # Center cross
            cross_h[0] = canvas.create_line(x-12, y, x+12, y, fill='#FF0000', width=1)
            cross_v[0] = canvas.create_line(x, y-12, x, y+12, fill='#FF0000', width=1)
            
            info.config(text=f"({x}, {y}) | Region: {self.width}x{self.height} | +/-=Size | x/X y/Y=Axes | Click=Capture")
        
        def on_motion(event):
            draw_border(event.x, event.y)
            
        def on_key(event):
            """Handles keys in freeze mode."""
            key = event.char
            keysym = event.keysym
            
            if key in ('+', '='):
                self.width = min(self.width + SIZE_STEP, MAX_SIZE)
                self.height = min(self.height + SIZE_STEP, MAX_SIZE)
                draw_border(self.last_x, self.last_y)
            elif key == '-':
                self.width = max(self.width - SIZE_STEP, MIN_SIZE)
                self.height = max(self.height - SIZE_STEP, MIN_SIZE)
                draw_border(self.last_x, self.last_y)
            elif key == 'x':
                self.width = min(self.width + SIZE_STEP, MAX_SIZE)
                draw_border(self.last_x, self.last_y)
            elif key == 'X':
                self.width = max(self.width - SIZE_STEP, MIN_SIZE)
                draw_border(self.last_x, self.last_y)
            elif key == 'y':
                self.height = min(self.height + SIZE_STEP, MAX_SIZE)
                draw_border(self.last_x, self.last_y)
            elif key == 'Y':
                self.height = max(self.height - SIZE_STEP, MIN_SIZE)
                draw_border(self.last_x, self.last_y)
            
        def on_click(event):
            x, y = event.x, event.y
            half_w = self.width // 2
            half_h = self.height // 2
            
            # Crop region from screenshot
            region = screenshot.crop((x - half_w, y - half_h, x + half_w, y + half_h))
            capture_data[0] = region
            capture_data[1] = x
            capture_data[2] = y
            captured[0] = True
            root.destroy()
            
        def on_cancel(event=None):
            root.destroy()
            
        canvas.bind('<Motion>', on_motion)
        canvas.bind('<Button-1>', on_click)
        root.bind('<Escape>', on_cancel)
        root.bind('<q>', on_cancel)
        root.bind('<Key>', on_key)  # Capture all keys
        
        root.mainloop()
        
        # Callback with result (includes updated size)
        if captured[0] and self.on_done:
            self.on_done(capture_data[0], capture_data[1], capture_data[2], self.width, self.height)
        elif self.on_done:
            # Even if canceled, return updated size
            self.on_done(None, 0, 0, self.width, self.height)


class RegionCapture:
    """Region capture app."""
    
    def __init__(self):
        self.width = DEFAULT_WIDTH
        self.height = DEFAULT_HEIGHT
        self.running = True
        self.capture_count = 0
        self.freeze_active = False
        
        os.makedirs(CAPTURES_DIR, exist_ok=True)
        
        # Keyboard listener
        self.kb_listener = keyboard.Listener(on_press=self.on_key)
        self.kb_listener.start()
        
        # Update thread
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()
        
    def update_loop(self):
        """Shows live info in terminal."""
        while self.running:
            if not self.freeze_active:
                x, y = pyautogui.position()
                print(
                    f"\r  Mouse: ({x:4d}, {y:4d}) | "
                    f"Region: {self.width}x{self.height} | "
                    f"Captures: {self.capture_count}    ",
                    end='', flush=True
                )
            time.sleep(0.1)
            
    def on_key(self, key):
        """Handles keyboard input."""
        if self.freeze_active:
            return
            
        try:
            if hasattr(key, 'char') and key.char:
                c = key.char
                
                if c in ('+', '='):
                    self.width = min(self.width + SIZE_STEP, MAX_SIZE)
                    self.height = min(self.height + SIZE_STEP, MAX_SIZE)
                    
                elif c == '-':
                    self.width = max(self.width - SIZE_STEP, MIN_SIZE)
                    self.height = max(self.height - SIZE_STEP, MIN_SIZE)
                    
                elif c == 'x':
                    self.width = min(self.width + SIZE_STEP, MAX_SIZE)
                elif c == 'X':
                    self.width = max(self.width - SIZE_STEP, MIN_SIZE)
                    
                elif c == 'y':
                    self.height = min(self.height + SIZE_STEP, MAX_SIZE)
                elif c == 'Y':
                    self.height = max(self.height - SIZE_STEP, MIN_SIZE)
                    
                elif c == 'f':
                    self.start_freeze()
                    
                elif c in ('c', 'C'):
                    self.capture_direct()
                    
                elif c in ('r', 'R'):
                    self.width = DEFAULT_WIDTH
                    self.height = DEFAULT_HEIGHT
                    print(f"\n✓ Reset: {DEFAULT_WIDTH}x{DEFAULT_HEIGHT}")
                    
                elif c in ('q', 'Q'):
                    self.quit()
                    return False
                    
            elif key == keyboard.Key.space:
                self.capture_direct()
            elif key == keyboard.Key.esc:
                self.quit()
                return False
                
        except Exception as e:
            pass
            
    def start_freeze(self):
        """Starts freeze mode in a separate thread."""
        print("\n🔒 FREEZE - +/-=Size | x/X=Width | y/Y=Height | Click=Capture | ESC=Cancel")
        self.freeze_active = True
        
        def run_freeze():
            freeze = FreezeCapture(self.width, self.height, self.on_freeze_done)
            freeze.run()
            self.freeze_active = False
            
        # Run in a separate thread (tkinter requirement in this flow)
        threading.Thread(target=run_freeze).start()
        
    def on_freeze_done(self, image, x, y, new_width, new_height):
        """Called when freeze ends: updates size and stores image if captured."""
        # Update size (it may have changed in freeze mode)
        self.width = new_width
        self.height = new_height
        
        # Save if a capture was made
        if image is not None:
            self.save_capture(image, x, y)
        
    def capture_direct(self):
        """Direct capture without freeze mode."""
        x, y = pyautogui.position()
        half_w = self.width // 2
        half_h = self.height // 2
        
        try:
            img = ImageGrab.grab(bbox=(x-half_w, y-half_h, x+half_w, y+half_h))
            self.save_capture(img, x, y)
        except Exception as e:
            print(f"\n✗ Error: {e}")
            
    def save_capture(self, image, x, y):
        """Saves capture and updates elements JSON."""
        if image is None:
            return
        
        # Save image temporarily
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_filename = f"temp_{timestamp}.png"
        temp_filepath = os.path.join(CAPTURES_DIR, temp_filename)
        image.save(temp_filepath)
        
        print(f"\n📷 Capture taken at ({x}, {y})")
        print("📝 Select an element or create a new one...")
        
        # Ask for name/description
        name, description, tags, is_new = ask_capture_info()
        
        # If canceled, remove temporary image
        if not name:
            os.remove(temp_filepath)
            print("✗ Capture canceled\n")
            return
        
        # Rename using chosen name
        safe_name = sanitize_filename(name)
        final_filename = f"{safe_name}_{timestamp}.png"
        final_filepath = os.path.join(CAPTURES_DIR, final_filename)
        
        os.rename(temp_filepath, final_filepath)
        
        self.capture_count += 1
        
        # Add to JSON
        if is_new:
            # Create new element
            add_image_to_element(name, final_filename, description, tags)
            print(f"✓ #{self.capture_count}: New element '{name}' created")
        else:
            # Add image to existing element
            add_image_to_element(name, final_filename)
            print(f"✓ #{self.capture_count}: Image added to '{name}'")
        
        total_elements = count_elements()
        print(f"✓ Saved: {final_filename}")
        print(f"✓ elements.json updated ({total_elements} elements)\n")
        
    def quit(self):
        """Exit."""
        self.running = False
        total_elements = count_elements()
        print(f"\n\n✓ {self.capture_count} captures in this session")
        print(f"  Folder: {CAPTURES_DIR}")
        print(f"✓ elements.json ({total_elements} elements)")
        print(f"  {ELEMENTS_FILE}\n")
        self.kb_listener.stop()
        os._exit(0)
        
    def run(self):
        """Run app."""
        try:
            self.kb_listener.join()
        except:
            self.quit()


def main():
    print("=" * 60)
    print("  REGION CAPTURE + AI MAP (JSON)")
    print("=" * 60)
    print("\n  + / -     Size (±1px)")
    print("  x / X     Width (±1px)")
    print("  y / Y     Height (±1px)")
    print("  f         FREEZE (freeze screen + visual border)")
    print("  c/Space   Direct capture")
    print("  r         Reset (200x200)")
    print("  q/ESC     Exit")
    print(f"\n  Folder: {CAPTURES_DIR}")
    print(f"  Elements: {ELEMENTS_FILE}")
    
    # Show existing elements
    total = count_elements()
    if total > 0:
        print(f"\n  📍 Registered elements: {total}")
    
    print("-" * 60 + "\n")
    
    signal.signal(signal.SIGINT, lambda s,f: os._exit(0))
    
    app = RegionCapture()
    app.run()


if __name__ == '__main__':
    main()
