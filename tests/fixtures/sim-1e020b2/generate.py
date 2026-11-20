"""Real trial MCAP + binding from livingproof-sim-mujoco 1e020b2 (its own test harness, toy robot).

Run inside a livingproof-sim-mujoco checkout at 1e020b2 (paths below are that checkout):
    python generate.py toy clear/ ; python generate.py touch contact/
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/workspace/cody-sim28/tests")
import test_media_binding as t
from livingproof_sim_mujoco import media


class MP:
    def setattr(self, o, n, v):
        setattr(o, n, v)

    def syspath_prepend(self, p):
        sys.path.insert(0, p)


def run(name, robot_cls_name, out):
    d = Path(tempfile.mkdtemp())
    repo = d / "repo"
    repo.mkdir()
    t._repo(repo)
    cls = t.ToyTouch if robot_cls_name == "touch" else t.Toy
    cls.root = repo
    t.test_evidence.Toy.root = repo
    t._nominal_conf(MP(), True)
    evid = (
        f"test_media_binding:{'TOUCH' if robot_cls_name == 'touch' else 'TOY'}"
        if robot_cls_name == "touch"
        else "test_evidence:TOY"
    )
    from livingproof_sim_mujoco import evidence

    evidence.evidence(evid, "stock", d / "ev", trials=2, lock=t._lock(repo))
    v = d / "verification.json"
    v.write_text(
        json.dumps({"trials": [{"index": 1, "status": "PASS"}, {"index": 2, "status": "FAIL"}]})
    )
    doc = media.media(evid, "stock", d / "ev", v, d / "m")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for n in (1, 2):
        for ext in ("mcap", "binding.json"):
            shutil.copy(d / "m" / "mcap" / f"trial-{n:02d}.{ext}", out / f"trial-{n:02d}.{ext}")
    shutil.copytree(d / "ev", out / "evidence", dirs_exist_ok=True)
    return doc


print(json.dumps(run("clear", sys.argv[1], sys.argv[2]), indent=1)[:300])
