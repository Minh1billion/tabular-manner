from pathlib import Path
import zipfile
import pathspec
from tqdm import tqdm

root = Path.cwd()
output = root.parent / f"{root.name}.zip"

with (root / ".gitignore").open("r", encoding="utf-8") as f:
    spec = pathspec.PathSpec.from_lines("gitwildmatch", f)

files = [
    path for path in root.rglob("*")
    if path.is_file() and not spec.match_file(path.relative_to(root))
]

with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in tqdm(files, desc=f"Zipping {root.name}", unit="file"):
        relative = path.relative_to(root)
        zf.write(path, Path(root.name) / relative)

print(f"\nCreated: {output}")