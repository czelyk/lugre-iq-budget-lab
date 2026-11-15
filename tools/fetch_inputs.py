"""Fetch and verify the Zenodo archive and the pinned Pocket SDR checkout."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "data" / "NASA-LuGRE-16411687.zip"
SIZE = 256_135_673
CHECKSUM = "cec32df1ca17cb95887762762c16629f"
DATA_URL = "https://zenodo.org/api/records/16411687/files/LuGRE.zip/content"
SDR_URL = "https://github.com/tomojitakasu/PocketSDR.git"
SDR_PATH = ROOT / ".cache" / "PocketSDR"
SDR_COMMIT = "23c91c732365a3668d303656de95a36e7604b58a"


def verify_archive(path):
    if path.stat().st_size != SIZE:
        raise ValueError(f"Unexpected LuGRE archive size: {path}")
    with path.open("rb") as f:
        digest = hashlib.file_digest(f, "md5").hexdigest()
    if digest != CHECKSUM:
        raise ValueError(f"LuGRE archive does not match the Zenodo checksum: {path}")


def ensure_archive():
    if "LUGRE_ARCHIVE" in os.environ:
        path = Path(os.environ["LUGRE_ARCHIVE"])
    elif ARCHIVE.is_file():
        path = ARCHIVE
    else:
        ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ARCHIVE.parent) as folder:
            temporary = Path(folder) / ARCHIVE.name
            with urlopen(DATA_URL, timeout=90) as response, temporary.open("wb") as out:
                shutil.copyfileobj(response, out, length=1024 * 1024)
            verify_archive(temporary)
            temporary.replace(ARCHIVE)
        path = ARCHIVE
    verify_archive(path)
    print(f"Verified {path}")


def git(*args):
    subprocess.run(["git", "-C", str(SDR_PATH), *args], check=True)


def ensure_sdr():
    if not (SDR_PATH / ".git").is_dir():
        SDR_PATH.mkdir(parents=True, exist_ok=True)
        git("init")
    current = subprocess.run(["git", "-C", str(SDR_PATH), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=False)
    if current.stdout.strip() != SDR_COMMIT:
        git("fetch", "--depth=1", SDR_URL, SDR_COMMIT)
        git("checkout", "--detach", SDR_COMMIT)
    print(f"Pocket SDR {SDR_COMMIT}")


if __name__ == "__main__":
    ensure_archive()
    ensure_sdr()
