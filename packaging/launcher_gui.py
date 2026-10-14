"""PyInstaller entry point for the windowed application (LokalOCR.exe)."""

import sys

if __name__ == "__main__":
    from lokalocr.ui.app import main

    sys.exit(main())
