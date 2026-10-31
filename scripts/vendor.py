"""Vendor pinned snapshots of the target systems into targets/.

The benchmark injects bugs into these snapshots, so they are pinned by commit and
copied without git history, large recorded data and personal notes.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "quorumlog": ("https://github.com/tkran2/QuorumLog", "2f32dd6247ed0ebb2da6b96716a804edf644415f"),
    "matching-engine": ("https://github.com/tkran2/matching-engine", "9df7d6e13b38bf20d10222a916b0ebb3278e52e6"),
    "runledger": ("https://github.com/tkran2/RunLedger", "d436cb7f51f9364f91bc9ecffbc6a4f475f96e71"),
    "tickforge": ("https://github.com/tkran2/TickForge", "1c2d27ffb68336ca53033742d05fe950635c9d28"),
}
EXCLUDE = (".git/", "benchmarks/", "reports/", "docs/RESUME_ENTRY.md", "docs/INTERVIEW_GUIDE.md",
           "docs/mac-and-github.md", "PACKAGE_MANIFEST.json", "PROVENANCE.md", ".github/")


def vendor(name, url, commit):
    dest = ROOT / "targets" / name
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "clone", "-q", url, tmp], check=True)
        subprocess.run(["git", "-C", tmp, "checkout", "-q", commit], check=True)
        files = subprocess.run(["git", "-C", tmp, "ls-files"], check=True, capture_output=True, text=True).stdout.split()
        if dest.exists():
            shutil.rmtree(dest)
        for f in files:
            if any(f.startswith(e) or f == e for e in EXCLUDE):
                continue
            (dest / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(tmp) / f, dest / f)
    (dest / "ORIGIN").write_text(f"{url} {commit}\n")
    print(f"{name}: {sum(1 for _ in dest.rglob('*') if _.is_file())} files")


if __name__ == "__main__":
    for name in sys.argv[1:] or TARGETS:
        vendor(name, *TARGETS[name])
