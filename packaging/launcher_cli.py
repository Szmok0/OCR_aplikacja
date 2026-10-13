"""PyInstaller entry point for the command-line tool (lokalocr-cli.exe)."""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from lokalocr.cli import main

    sys.exit(main())
