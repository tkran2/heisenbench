"""Materialize pristine or buggy copies of a target, and restore oracle files."""

from __future__ import annotations

import difflib
import shutil
from pathlib import Path

from .bugspecs import Bug
from .targets import TARGETS, Target


def apply_edits(root: Path, bug: Bug) -> None:
    for e in bug.edits:
        path = root / e.file
        text = path.read_text()
        count = text.count(e.old)
        if count != 1:
            raise ValueError(f"{bug.id}: edit target occurs {count} times in {e.file}")
        path.write_text(text.replace(e.old, e.new))


def materialize(target: Target, dest: Path, bug: Bug | None = None) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(target.snapshot, dest, ignore=shutil.ignore_patterns("build", "__pycache__", "ORIGIN"))
    if bug is not None:
        apply_edits(dest, bug)
    return dest


def patch_for(bug: Bug) -> str:
    """Unified diff from the pristine snapshot to the buggy version."""
    target = TARGETS[bug.target]
    out = []
    for e in bug.edits:
        before = (target.snapshot / e.file).read_text()
        after = before.replace(e.old, e.new)
        out.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                        f"a/{e.file}", f"b/{e.file}"))
    return "".join(out)


def restore_protected(target: Target, workdir: Path) -> list[str]:
    """Put the oracle files back to pristine. Returns the paths that had been modified."""
    tampered = []
    for rel in target.protected:
        src, dst = target.snapshot / rel, workdir / rel
        if src.is_dir():
            for f in src.rglob("*"):
                if f.is_file():
                    d = dst / f.relative_to(src)
                    if not d.exists() or d.read_bytes() != f.read_bytes():
                        tampered.append(str(d.relative_to(workdir)))
                        d.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, d)
        elif src.exists():
            if not dst.exists() or dst.read_bytes() != src.read_bytes():
                tampered.append(rel)
                shutil.copy2(src, dst)
    return tampered
