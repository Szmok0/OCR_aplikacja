"""PyInstaller entry point for the windowed application (LokalOCR.exe)."""

import multiprocessing
import sys

if __name__ == "__main__":
    # Must run first: full mode spawns a child process from the frozen exe.
    multiprocessing.freeze_support()
    from lokalocr.ui.app import main

    sys.exit(main())
