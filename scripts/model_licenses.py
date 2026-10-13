"""Print the licences of the downloaded Docling model repositories (developer/CI only)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.pop("HF_HUB_OFFLINE", None)


def main() -> int:
    from huggingface_hub import model_info

    folder = Path("models/docling")
    repos = sorted(
        p.name.replace("--", "/") for p in folder.iterdir() if p.is_dir() and "--" in p.name
    )
    for repo in repos:
        try:
            info = model_info(repo)
            card = info.card_data.to_dict() if info.card_data else {}
            print(f"{repo}: license={card.get('license')} sha={info.sha}")
        except Exception as exc:  # report and continue
            print(f"{repo}: could not read model card ({type(exc).__name__})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
