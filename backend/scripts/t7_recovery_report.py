"""只输出恢复演练聚合结果，无业务标识、金额或凭据。"""

import argparse
import json
from datetime import datetime
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--directory", type=Path, required=True)
parser.add_argument("--rto-seconds", type=int, required=True)
args = parser.parse_args()
state = json.loads((args.directory / "state.json").read_text())
metadata = json.loads((args.directory / "metadata.json").read_text())
before = json.loads((args.directory / "before.json").read_text())["domains"]
after = json.loads((args.directory / "after.json").read_text())["domains"]
if before != after:
    raise SystemExit("恢复前后结构/表行数不一致")
rpo = (datetime.fromisoformat(state["post_backup_commit_at"]) -
       datetime.fromisoformat(metadata["created_at"])).total_seconds()
result = {
    "scope": "隔离合成数据、实际MySQL加密快照恢复；不代表生产异机灾备",
    "table_counts_preserved": True,
    "tables": sum(len(domain["tables"]) for domain in before.values()),
    "rpo_seconds": round(max(0, rpo), 3),
    "rto_seconds": args.rto_seconds,
    "rpo_target_seconds": 900, "rto_target_seconds": 7200,
    "rpo_target_met_in_drill": rpo <= 900,
    "rto_target_met_in_drill": args.rto_seconds <= 7200,
    "post_snapshot_effects_held_unknown": True,
    "restored_real_egress": False, "automatic_outbox_replay": False,
}
print(json.dumps(result, ensure_ascii=False))
