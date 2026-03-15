#!/usr/bin/env python3
"""
审批系统技能主入口：解析审批类型与参数，调用 OA 连接器发起审批或查询状态。
供容器内 Agent 通过 Bash 调用，例如：
  python index.py --action submit --type leave --reason "家事" --days 3
  python index.py --action query [--approval_id xxx]
"""
import argparse
import json
import sys
from pathlib import Path

# 技能目录：与 index.py 同目录（确保同目录下 oa_connector 可被 import）
SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
CONFIG_PATH = SKILL_DIR / "config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"approval_types": {}, "permission_required": False}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="审批系统 Skill")
    p.add_argument("--action", choices=["submit", "query"], default="submit")
    p.add_argument("--approval_id", default="")
    p.add_argument("--type", dest="approval_type", choices=["leave", "expense", "purchase"])
    p.add_argument("--reason", default="")
    p.add_argument("--days", type=int, default=0)
    p.add_argument("--amount", type=float, default=0)
    p.add_argument("--title", default="")
    p.add_argument("--category", default="")
    p.add_argument("--start_date", default="")
    p.add_argument("--end_date", default="")
    p.add_argument("--attachments", default="")
    p.add_argument("--items", default="")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    action = args.action

    if action == "query":
        from oa_connector import query_approval_status
        result = query_approval_status(args.approval_id or None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result.get("ok") else 1)

    if action == "submit":
        if not args.approval_type:
            parser.error("--type 必填：leave | expense | purchase")
        config = load_config()
        types_cfg = config.get("approval_types", {}).get(args.approval_type, {})
        required = types_cfg.get("required", ["reason"])
        params = {
            "reason": args.reason,
            "days": args.days,
            "amount": args.amount,
            "title": args.title,
            "category": args.category,
            "start_date": args.start_date,
            "end_date": args.end_date,
            "attachments": args.attachments,
            "items": args.items,
        }
        params = {k: v for k, v in params.items() if v not in (None, "", 0)}
        for r in required:
            if r not in params or params[r] in (None, "", 0):
                parser.error(f"缺少必填参数: {r}")
        from oa_connector import submit_approval
        result = submit_approval(args.approval_type, params)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result.get("ok") else 1)

    parser.error("--action 必填：submit | query")


if __name__ == "__main__":
    main()
