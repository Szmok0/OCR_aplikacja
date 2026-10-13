# PyInstaller spec: one-folder Windows build (stage 7, §4 "Pakowanie").
#
#   LOKALOCR_TESSERACT_DIR  folder with tesseract.exe, its DLLs and tessdata/ (bundled)
#   LOKALOCR_BUILD_FULL=1   also bundle Docling (full mode) and models/docling
#
# Run from the repository root:  pyinstaller packaging/lokalocr.spec --noconfirm
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 (provided by PyInstaller)
RES = ROOT / "src" / "lokalocr" / "ui" / "resources"
FULL = os.environ.get("LOKALOCR_BUILD_FULL") == "1"
TESSERACT = os.environ.get("LOKALOCR_TESSERACT_DIR")

datas = [
    (str(RES), "lokalocr/ui/resources"),
    (str(ROOT / "docs" / "user-guide.md"), "docs"),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "docs"),
]
if TESSERACT:
    datas.append((TESSERACT, "tesseract"))

hiddenimports = ["lokalocr.engines.tesseract", "lokalocr.engines.docling_engine"]
excludes = ["tkinter", "matplotlib", "IPython", "jupyter", "notebook", "pytest"]
if FULL:
    for package in ("docling", "docling_core", "docling_parse", "docling_ibm_models"):
        datas += collect_data_files(package)
        hiddenimports += collect_submodules(package)
    datas.append((str(ROOT / "models"), "models"))
else:
    excludes += ["torch", "torchvision", "transformers", "docling", "docling_core"]

common = dict(
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
gui = Analysis([str(ROOT / "packaging" / "launcher_gui.py")], **common)  # noqa: F821
cli = Analysis([str(ROOT / "packaging" / "launcher_cli.py")], **common)  # noqa: F821

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
