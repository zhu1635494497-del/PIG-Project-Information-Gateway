"""Create isolated, synthetic V2.1.5 desktop acceptance inputs."""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing acceptance data: {output}")
    output.mkdir(parents=True)

    folder = output / "input-folder"
    (folder / "notes").mkdir(parents=True)
    (folder / "notes" / "decision.txt").write_text(
        "Synthetic decision note. Edit this Working copy during acceptance.\n",
        encoding="utf-8",
    )
    (folder / "reference.csv").write_text(
        "item,value\nalpha,1\nbeta,2\n", encoding="utf-8"
    )
    with ZipFile(output / "nested.zip", "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("mail/attachments/core.txt", "Synthetic nested source.\n")
        archive.writestr("mail/attachments/support.txt", "Secondary file.\n")

    block = bytes(range(256)) * 4096
    with (output / "large-80m.bin").open("wb") as stream:
        for _ in range(80):
            stream.write(block)
    print(f"Synthetic inputs ready: {output}")
    print("Import input-folder, nested.zip, and large-80m.bin into a new Project.")


if __name__ == "__main__":
    main()
