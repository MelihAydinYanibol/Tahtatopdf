# Tahtatopdf

Turns a book you can only read on screen into a PDF. Tahtatopdf captures each page with the
Windows Snipping Tool, clicks the viewer's "next page" button, and when it's done combines all
the pages into a single PDF.

## Features

- Captures pages automatically using **Win + Shift + S** (Windows Snipping Tool)
- Saves page locations per **publisher**, so you only enter coordinates once
- Shows a **progress bar** with ETA while capturing and while building the PDF
- **Abort key** (default **F10**) that works from any window, not just the terminal
- After aborting, you can still make a PDF from the pages captured so far
- Never overwrites an existing PDF: saves as `book.pdf`, then `book_02.pdf`, `book_03.pdf`, ...
- Offers to delete the page images after the PDF is created

## Requirements

- Windows 10 or 11 (uses the built-in Snipping Tool)
- Python 3.10+

## Installation

```bash
git clone https://github.com/MelihAydinYanibol/Tahtatopdf.git
cd Tahtatopdf
python -m venv env
env\Scripts\activate
pip install -r requirements.txt
```

## Usage

1. Open the book in its viewer and go to the page you want to start from.
2. Run the program:

   ```bash
   python main.py
   ```

3. Answer the questions:

   | Question | What to enter |
   | --- | --- |
   | Abort key | Press Enter to keep the current key, or type a new one (`f9`, `esc`, `pause`, `q`, ...) |
   | Mode | `1` to start from the first page, `2` to continue from the middle of a book |
   | Publisher name | A saved publisher to reuse its locations, a new name to save them, or empty to skip |
   | Top left / bottom right corner | Screen coordinates of the page area, as `x, y` |
   | Next button location | Screen coordinates of the viewer's next page button, as `x, y` |
   | Number of pages / last page | How many pages to capture |
   | Current page number | (mode 2 only) The page the viewer is currently on |

4. During the 3 second countdown, switch to the book window and don't touch the mouse.
5. When capturing is done, the PDF is written to the project folder and you're asked whether
   to delete the page images.

### Finding screen coordinates

Run this, then move your mouse to the spot you want within 3 seconds:

```bash
python -c "import pyautogui, time; time.sleep(3); print(pyautogui.position())"
```

### Aborting

Press the abort key (**F10** by default) at any time, from any window. The program releases the
mouse, closes the snipping overlay and asks whether to make a PDF from the pages captured so far.
Moving the mouse into a corner of the screen also aborts (pyautogui's fail-safe).

Note that the focused window still receives the key too (for example F11 toggles fullscreen in
browsers), so pick a key that doesn't do anything in your book viewer.

## Files

| Path | Contents |
| --- | --- |
| `cache/` | Captured page images (`001.png`, `002.png`, ...) |
| `book.pdf`, `book_02.pdf`, ... | Generated PDFs |
| `publishers.json` | Saved locations per publisher |
| `settings.json` | Your chosen abort key |

These are all local and ignored by git.

To change a saved publisher's locations, edit or remove its entry in `publishers.json`.

## License

Licensed under the [GNU General Public License v3.0](LICENSE).
