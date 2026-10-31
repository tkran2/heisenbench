"""Run a target's build, unit tests and deep verification in a working copy."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .targets import Target


@dataclass
class Run:
    ok: bool
    returncode: int | None
    seconds: float
    tail: str

    def to_dict(self):
        return asdict(self)


def run(cmd: str, cwd: Path, timeout: int, env: dict | None = None) -> Run:
    t0 = time.time()
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, **(env or {})})
        out = (p.stdout + p.stderr)[-1500:]
        return Run(p.returncode == 0, p.returncode, time.time() - t0, out)
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"").decode(errors="replace") + (e.stderr or b"").decode(errors="replace"))[-1500:]
        return Run(False, None, time.time() - t0, "TIMEOUT\n" + out)


def build(target: Target, workdir: Path) -> Run:
    if not target.build:
        return Run(True, 0, 0.0, "")
    (workdir / "build").mkdir(exist_ok=True)
    return run(target.build, workdir, 1200, target.env)


def unit(target: Target, workdir: Path) -> Run:
    return run(target.unit, workdir, target.unit_timeout, target.env)


def deep(target: Target, workdir: Path) -> Run:
    (workdir / "build").mkdir(exist_ok=True)
    t0, tails = time.time(), []
    for cmd in target.deep:
        r = run(target.render(cmd, workdir), workdir, target.deep_timeout, target.env)
        tails.append(r.tail)
        if not r.ok:
            return Run(False, r.returncode, time.time() - t0, r.tail)
    return Run(True, 0, time.time() - t0, tails[-1] if tails else "")
