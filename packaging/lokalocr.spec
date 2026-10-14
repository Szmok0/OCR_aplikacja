# PyInstaller spec: one-folder Windows build (stage 7, §4 "Pakowanie").
#
#   LOKALOCR_TESSERACT_DIR  folder with tesseract.exe, its DLLs and tessdata/ (bundled)
#
# Run from the repository root:  pyinstaller packaging/lokalocr.spec --noconfirm
import os
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 (provided by PyInstaller)
RES = ROOT / "src" / "lokalocr" / "ui" / "resources"
TESSERACT = os.environ.get("LOKALOCR_TESSERACT_DIR")

datas = [
    (str(RES), "lokalocr/ui/resources"),
    (str(ROOT / "docs" / "user-guide.md"), "docs"),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "docs"),
]
if TESSERACT:
    datas.append((TESSERACT, "tesseract"))

hiddenimports = ["lokalocr.engines.tesseract"]
# Heavy packages a developer environment may have installed, and every Qt module
# that can talk to the network (§6): never bundle them.
excludes = [
    "tkinter", "matplotlib", "IPython", "jupyter", "notebook", "pytest",
    "torch", "torchvision", "transformers", "docling", "docling_core",
    "PySide6.QtNetwork", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets", "PySide6.QtHttpServer", "PySide6.QtRemoteObjects",
]

common = dict(
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
gui = Analysis([str(ROOT / "packaging" / "launcher_gui.py")], **common)  # noqa: F821
cli = Analysis([str(ROOT / "packaging" / "launcher_cli.py")], **common)  # noqa: F821

# PyInstaller's Qt hooks also collect plugins the app never uses: the virtual
# keyboard input context (pulls in QML/Quick and Qt6Network), the TUIO touch
# plugin (listens on UDP) and network/TLS plugins. Leave them, and with them
# Qt's network library, out of the package (§6). The app only needs QtCore,
# QtGui, QtWidgets and QtSvg.
_UNWANTED = (
    "qt6network", "qt6qml", "qt6quick", "qt6virtualkeyboard", "qt6pdfquick",
    "qtvirtualkeyboardplugin", "qtuiotouchplugin", "networkinformation", "/tls/",
)


def _wanted(entry):
    name = entry[0].replace("\\", "/").lower()
    return not any(part in name for part in _UNWANTED)


for analysis in (gui, cli):
    dropped = sorted(e[0] for e in analysis.binaries if not _wanted(e))
    if dropped:
        print("Left out of the package:", ", ".join(dropped))
    analysis.binaries = [e for e in analysis.binaries if _wanted(e)]
    analysis.datas = [e for e in analysis.datas if _wanted(e)]

icon = str(RES / "app_icon.ico")
gui_exe = EXE(  # noqa: F821
    PYZ(gui.pure),  # noqa: F821
    gui.scripts,
    [],
    exclude_binaries=True,
    name="LokalOCR",
    console=False,
    icon=icon,
    upx=False,
)
cli_exe = EXE(  # noqa: F821
    PYZ(cli.pure),  # noqa: F821
    cli.scripts,
    [],
    exclude_binaries=True,
    name="lokalocr-cli",
    console=True,
    icon=icon,
    upx=False,
)
COLLECT(  # noqa: F821
    gui_exe,
    gui.binaries,
    gui.datas,
    cli_exe,
    cli.binaries,
    cli.datas,
    name="LokalOCR",
    upx=False,
)
