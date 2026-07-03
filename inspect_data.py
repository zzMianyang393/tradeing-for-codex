from __future__ import annotations

import csv
import sys
from pathlib import Path


def inspect(path: Path) -> None:
    rows = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        for row in reader:
            rows.append(row)
    print(f"path={path}")
    print(f"fields={fieldnames}")
    print(f"rows={len(rows)}")
    if rows:
        print(f"first={rows[0]}")
        print(f"last={rows[-1]}")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        inspect(Path(arg))
