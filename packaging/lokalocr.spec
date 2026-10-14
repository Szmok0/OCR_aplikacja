# PyInstaller spec: one-folder Windows build (stage 7, §4 "Pakowanie").
#
#   LOKALOCR_TESSERACT_DIR  folder with tesseract.exe, its DLLs and tessdata/ (bundled)
#   LOKALOCR_BUILD_FULL=1   also bundle Docling (full mode) and models/docling
#
# Run from the repository root:  pyinstaller packaging/lokalocr.spec --noconfirm
import os
from pathlib import Path

from importlib.metadata import distributions
from importlib.util import find_spec

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

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

binaries = []
hiddenimports = ["lokalocr.engines.tesseract", "lokalocr.engines.docling_engine"]
excludes = ["tkinter", "matplotlib", "IPython", "jupyter", "notebook", "pytest"]
if FULL:
    for package in ("docling", "docling_core", "docling_parse", "docling_ibm_models"):
        datas += collect_data_files(package)
        hiddenimports += collect_submodules(package)
    # Docling finds its models (OCR, layout, tables, ...) as plugins through the
    # "docling" entry-point group, read from package metadata (dist-info). PyInstaller
    # does not bundle metadata by default: without it Docling knows no models and
    # full mode fails at once ("No class found with the name ...").
    for dist in distributions():
        if any(ep.group == "docling" for ep in dist.entry_points):
            datas += copy_metadata(dist.metadata["Name"])
            hiddenimports += [ep.module for ep in dist.entry_points if ep.group == "docling"]
    # torchvision loads its compiled operators (_C_stable, image_stable) with
    # torch.ops.load_library from its own folder; PyInstaller cannot see that
    # (its hook still names the old "_C"). Without them: "operator
    # torchvision::nms does not exist" when the layout model starts.
    tv_spec = find_spec("torchvision")
    if tv_spec is not None and tv_spec.submodule_search_locations:
        tv_dir = Path(list(tv_spec.submodule_search_locations)[0])
        for lib in tv_dir.iterdir():
            if lib.suffix in (".pyd", ".so", ".dll") or ".so." in lib.name:
                binaries.append((str(lib), "torchvision"))
    datas.append((str(ROOT / "models"), "models"))
else:
    excludes += ["torch", "torchvision", "transformers", "docling", "docling_core"]

common = dict(
    pathex=[str(ROOT / "src")],
    binaries=binaries,
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
