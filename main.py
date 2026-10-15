import ctypes
import glob
import json
import os
import re
import shutil
import threading
import time
import pyautogui
from PIL import Image, ImageGrab
from pynput import keyboard
from tqdm import tqdm

CACHE_DIR = "cache"
PUBLISHERS_FILE = "publishers.json"
SETTINGS_FILE = "settings.json"
DEFAULT_ABORT_KEY = "f10"
# Keys the program presses itself, so they can't be used to abort
RESERVED_KEYS = {"cmd", "cmd_l", "cmd_r", "shift", "shift_l", "shift_r", "s"}
BAR_FORMAT = "{desc} |{bar}| {n_fmt}/{total_fmt} pages [{elapsed}<{remaining}, {rate_fmt}]{postfix}"

abort_event = threading.Event()


class Aborted(Exception):
    """Raised when the user presses the abort key."""


def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {"abort_key": DEFAULT_ABORT_KEY}
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return {"abort_key": DEFAULT_ABORT_KEY, **json.load(f)}


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)


def key_name(key):
    """Turn a pynput key into a name like 'f11', 'esc' or 'q'."""
    if isinstance(key, keyboard.Key):
        return key.name
    if getattr(key, "char", None):
        return key.char.lower()
    return None


def is_valid_key(name):
    """A valid key is a special key pynput knows (f1-f24, esc, pause, ...) or a single character."""
    return name not in RESERVED_KEYS and (name in keyboard.Key.__members__ or len(name) == 1)


def choose_abort_key():
    """Show the current abort key and let the user change it. The choice is remembered."""
    settings = load_settings()
    current = settings["abort_key"]
    while True:
        new = input(f"Abort key [{current}] (Enter to keep, or type a new key e.g. f10, esc, pause) : ")
        new = new.strip().lower()
        if not new:
            return current
        if is_valid_key(new):
            settings["abort_key"] = new
            save_settings(settings)
            print(f"Abort key set to '{new}'")
            return new
        print(f"'{new}' can't be used. Use a key like f1-f24, esc, pause, end or a single letter (not s).")


def start_abort_listener(abort_key):
    """Watch for the abort key system-wide, even when the terminal isn't focused."""
    def on_press(key):
        if key_name(key) == abort_key:
            abort_event.set()

    listener = keyboard.Listener(on_press=on_press, daemon=True)
    listener.start()
    return listener


def check_abort():
    if abort_event.is_set():
        raise Aborted


def wait(seconds):
    """Sleep, but stop right away if the abort key is pressed."""
    if abort_event.wait(seconds):
        raise Aborted


def header(text):
    """Print a section header."""
    print(f"\n=== {text} ===")


def format_duration(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

def press_win_shift_s():
    KEYEVENTF_KEYUP = 0x0002
    VK_LWIN = 0x5B
    VK_SHIFT = 0x10
    VK_S = 0x53

    """Press Win+Shift+S to open the Windows Snipping Tool overlay."""
    user32 = ctypes.windll.user32
    keys = (VK_LWIN, VK_SHIFT, VK_S)

    for vk in keys:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.02)

    for vk in reversed(keys):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)

def load_publishers():
    """Load saved publisher locations from publishers.json."""
    if not os.path.exists(PUBLISHERS_FILE):
        return {}
    with open(PUBLISHERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_publisher(name, p1, p2, next_btn):
    """Save p1, p2 and next button locations under a publisher name."""
    publishers = load_publishers()
    publishers[name] = {"p1": p1, "p2": p2, "next_btn": next_btn}
    with open(PUBLISHERS_FILE, "w", encoding="utf-8") as f:
        json.dump(publishers, f, indent=4, ensure_ascii=False)
    print(f"Saved locations for '{name}'")


def get_values():
    global mode, p1, p2, next_btn, num_pages, abort_key
    abort_key = choose_abort_key()
    mode = input("Enter mode (1 for from start, 2 for mid): ")

    publishers = load_publishers()
    if publishers:
        print("Saved publishers : " + ", ".join(publishers))
    name = input("Publisher name (leave empty to skip) : ").strip()

    if name in publishers:
        p1 = publishers[name]["p1"]
        p2 = publishers[name]["p2"]
        next_btn = publishers[name]["next_btn"]
        print(f"Using saved locations for '{name}'")
    else:
        p1 = input("Top left corner (x, y) : ").split(",")
        p2 = input("Bottom right corner (x, y) : ").split(",")
        next_btn = input("Next button location (x, y) : ").split(",")
        if name:
            save_publisher(name, p1, p2, next_btn)

    if mode == "1":
        num_pages = int(input("Number of pages to capture : "))
    elif mode == "2":
        num_pages = int(input("last page of book : "))

def save_page(page_number, timeout=5):
    """Save the image currently in the clipboard as cache/000.png, cache/001.png, ..."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    filename = os.path.join(CACHE_DIR, f"{page_number:03d}.png")

    # The snip can take a moment to reach the clipboard, so keep checking
    deadline = time.time() + timeout
    while time.time() < deadline:
        check_abort()
        image = ImageGrab.grabclipboard()
        if isinstance(image, Image.Image):
            image.save(filename)
            return filename
        wait(0.1)

    raise RuntimeError(f"No image found in clipboard for page {page_number}")


def free_filename(path):
    """Return path if it's free, otherwise the first free name like book_02.pdf, book_03.pdf, ..."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{base}_{n:02d}{ext}"):
        n += 1
    return f"{base}_{n:02d}{ext}"


def combine_to_pdf(output="book.pdf"):
    """Combine all cached page images into one PDF, then offer to delete them."""
    output = free_filename(output)  # Never overwrite an existing PDF
    # Accept any numbered PNG (000.png, page_12.png, ...) and sort by the number,
    # so page_99 comes before page_100
    files = [f for f in glob.glob(os.path.join(CACHE_DIR, "*.png"))
             if re.search(r"\d+", os.path.basename(f))]
    files.sort(key=lambda f: int(re.search(r"\d+", os.path.basename(f)).group()))
    if not files:
        raise RuntimeError("No page images found to combine")

    header("Creating PDF")
    print(f"Found {len(files)} page images in '{CACHE_DIR}'")
    start = time.time()

    pages = []
    with tqdm(files, desc="Loading pages", unit="page", bar_format=BAR_FORMAT) as bar:
        for f in bar:
            bar.set_postfix_str(os.path.basename(f))
            with Image.open(f) as image:
                pages.append(image.convert("RGB"))

    print(f"Writing {output} (this can take a moment for big books)...")
    pages[0].save(output, save_all=True, append_images=pages[1:])

    size_mb = os.path.getsize(output) / (1024 * 1024)
    print(f"Saved {len(pages)} pages to {output} ({size_mb:.1f} MB) "
          f"in {format_duration(time.time() - start)}")

    answer = input(f"Delete the {len(files)} page images in '{CACHE_DIR}'? (y/n) : ")
    if answer.strip().lower() == "y":
        shutil.rmtree(CACHE_DIR)
        print("Page images deleted")
    return output


def main_loop():
    get_values()
    if mode == "1":
        page_number = 1
    else:
        page_number = int(input("current page number : "))
    header("Capturing pages")
    print(f"Area     : ({p1[0].strip()}, {p1[1].strip()}) -> ({p2[0].strip()}, {p2[1].strip()})")
    print(f"Next btn : ({next_btn[0].strip()}, {next_btn[1].strip()})")
    print(f"Pages    : {num_pages}, starting at page {page_number}")
    print(f"Saving to: {os.path.abspath(CACHE_DIR)}")
    print(f"Abort    : press {abort_key.upper()} at any time (works from any window)")

    abort_event.clear()
    listener = start_abort_listener(abort_key)
    captured = 0
    snipping = False
    start = time.time()
    try:
        for i in range(3, 0, -1):
            print(f"\rStarting in {i}... switch to the book window", end="", flush=True)
            wait(1)
        print()

        with tqdm(total=num_pages, desc="Capturing", unit="page", bar_format=BAR_FORMAT) as bar:
            for _ in range(num_pages):
                check_abort()
                bar.set_postfix_str(f"page {page_number}: snipping")
                snipping = True
                press_win_shift_s()
                wait(1)  # Wait for the snipping tool to open
                pyautogui.mouseDown(x=int(p1[0]), y=int(p1[1]))
                pyautogui.moveTo(int(p2[0]), int(p2[1]), duration=0.5)
                pyautogui.mouseUp()
                snipping = False

                bar.set_postfix_str(f"page {page_number}: saving")
                filename = save_page(page_number)
                captured += 1
                wait(.7)  # Wait for the snip to be processed

                bar.set_postfix_str(f"page {page_number}: next page")
                pyautogui.click(x=int(next_btn[0]), y=int(next_btn[1]))  # Click the next button
                bar.write(f"  saved {filename}")
                bar.update(1)
                page_number += 1
                wait(1)  # Wait for the next page to be ready
    except (Aborted, pyautogui.FailSafeException):
        pyautogui.mouseUp()  # Don't leave the mouse button held down
        if snipping:
            pyautogui.press("esc")  # Close the snipping overlay
        print(f"\nAborted after {captured} of {num_pages} pages "
              f"({format_duration(time.time() - start)})")
        if captured == 0:
            return
        answer = input(f"Create a PDF from the {captured} pages captured so far? (y/n) : ")
        if answer.strip().lower() != "y":
            print(f"Page images kept in '{CACHE_DIR}'")
            return
    else:
        print(f"Captured {num_pages} pages in {format_duration(time.time() - start)}")
    finally:
        listener.stop()

    combine_to_pdf()

main_loop()