"""Drop the local SQLite database file so the next seed rebuilds the schema."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402

url = get_settings().database_url
print("DATABASE_URL:", url)

if "sqlite" not in url:
    raise SystemExit("Refusing to reset a non-SQLite database")

raw = url.split("///", 1)[1]
path = Path(raw).resolve()
print("resolved path:", path, "exists:", path.exists())

for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
    if candidate.exists():
        os.remove(candidate)
        print("removed", candidate)

print("done")
