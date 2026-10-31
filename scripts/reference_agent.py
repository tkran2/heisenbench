"""Scripted 'agents' used to check the harness itself (no model involved).

  fix <workdir>     undo the injected edit (should score: fixed)
  tamper <workdir>  delete the test sources instead of fixing anything (should score: unit_fail
                    or no_change, with the tampering recorded)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from heisenbench.bugspecs import BUGS  # noqa: E402

mode, work = sys.argv[1], Path(sys.argv[2])
bug = next(b for b in BUGS if work.name.startswith(b.id + "-"))
if mode == "fix":
    for e in bug.edits:
        p = work / e.file
        p.write_text(p.read_text().replace(e.new, e.old, 1) if e.new else p.read_text())
    if any(not e.new for e in bug.edits):
        raise SystemExit("cannot undo a pure deletion by text replacement")
elif mode == "tamper":
    for f in (work / "tests").rglob("*"):
        if f.is_file():
            f.write_text("")
