"""PyInstaller entry point for the command-line tool (lokalocr-cli.exe)."""

import sys

if __name__ == "__main__":
    from lokalocr.cli import main

    sys.exit(main())
