# -*- coding: utf-8 -*-
"""
每日排程主程式
==============
流程：
  1. 抓取事求人開放資料 XML
  2. 依 field_mapping.json 對照出欄位，只保留「簡任／薦任／委任」且非約聘僱等
     人員區分的職缺
  3. 和既有的 data/history.json（累積歸檔，只增不刪）合併
  4. 針對目前仍在刊登中的職缺，計算「上一次相似職缺」與近三/五年刊登次數
  5. 輸出 docs/data.json 給網站前端讀取

用法：
    python scripts/fetch_and_process.py
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from collections import defaultdict

from common import (
    fetch_raw_xml, parse_records, resolve_field, detect_rank_track,
    detect_city, parse_roc_compact_date, extract_work_id,
    make_record_id, days_between, split_bullets,
    EXCLUDE_PERSON_TYPES,
)

ROOT = Path(__file__).resolve().parent.parent
MAPPING_PATH = ROOT / "scripts" / "field_mapping.json"
HISTORY_PATH = ROOT / "data" / "history.json"
OUTPUT_PATH = ROOT / "docs" / "data.json"

TODAY = date.today()
SUMMARY_LEN = 120


def load_mapping():
    with open(MAPPING_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_history():
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize(raw, mapping):
    agency = resolve_field(raw, mapping["agency"])
    person_type = resolve_field(raw, mapping["person_type"])
    rank_text = resolve_field(raw, mapping["rank"])
    family = resolve_field(raw, mapping["family"])
    title = resolve_field(raw, mapping["title"])
    location = resolve_field(raw, mapping["location"])
    date_from = resolve_field(raw, mapping.get("date_from", []))
    date_to = resolve_field(raw, mapping.get("date_to", []))
    job_content = resolve_field(raw, mapping["job_content"])
    work_address = resolve_field(raw, mapping["work_address"])
    view_url = resolve_field(raw, mapping.get("view_url", []))
    work_id = extract_work_id(view_url)

    # 排除非公務人員任用資格
    if person_type and any(ex in person_type for ex in EXCLUDE_PERSON_TYPES):
        return None, "非公務人員任用資格（人員區分排除）"

    rank_track, rank_detail = detect_rank_track(rank_text)
    if rank_track is None:
        return None, f"官職等文字無法判斷是否為簡任/薦任/委任：{rank_text!r}"

    city = detect_city(location) or detect_city(work_address)
    start_iso = parse_roc_compact_date(date_from)
    end_iso = parse_roc_compact_date(date_to)
    if not start_iso or not end_iso:
        return None, f"有效期間格式無法解析：date_from={date_from!r} date_to={date_to!r}"

    summary = (job_content or "").strip()
    if len(summary) > SUMMARY_LEN:
        summary = summary[:SUMMARY_LEN] + "…"

    rec = {
        "work_id": work_id,
        "view_url": view_url,
        "agency": agency,
        "city": city,
        "rank_track": rank_track,
        "rank_detail": rank_detail,
        "family": family,
        "title": title,
        "summary": summary,
        "quota": resolve_field(raw, mapping.get("quota", [])) or "1名",
        "gender": resolve_field(raw, mapping.get("gender", [])) or "不限",
        "email": resolve_field(raw, mapping.get("email", [])),
        "address": work_address,
        "qualification": split_bullets(resolve_field(raw, mapping.get("qualification", []))),
        "job_content_full": split_bullets(job_content),
        "contact": split_bullets(resolve_field(raw, mapping.get("contact", []))),
        "period_start": start_iso,
        "period_end": end_iso,
        "first_seen": TODAY.isoformat(),
    }
    rec["id"] = make_record_id(rec)
    return rec, None


def merge_history(existing, new_records):
    by_id = {r["id"]: r for r in existing}
    added = 0
    for r in new_records:
        if r["id"] not in by_id:
            by_id[r["id"]] = r
            added += 1
    merged = sorted(by_id.values(), key=lambda r: r["period_start"], reverse=True)
    return merged, added


def build_output(history):
    # 依「機關 + 職系」分組，用來找『相似職缺』
    groups = defaultdict(list)
    for r in history:
        key = (r["agency"], r["family"])
        groups[key].append(r)
    for key in groups:
        groups[key].sort(key=lambda r: r["period_start"], reverse=True)

    y3 = (TODAY - timedelta(days=365 * 3)).isoformat()
    y5 = (TODAY - timedelta(days=365 * 5)).isoformat()

    open_jobs = [r for r in history if r["period_end"] >= TODAY.isoformat()]

    output_jobs = []
    for r in open_jobs:
        key = (r["agency"], r["family"])
        siblings = [s for s in groups[key] if s["id"] != r["id"]]
        last_similar = siblings[0] if siblings else None
        freq3y = sum(1 for s in groups[key] if s["period_start"] >= y3)
        freq5y = sum(1 for s in groups[key] if s["period_start"] >= y5)

        job = dict(r)
        job["days"] = days_between(r["period_start"], r["period_end"])
        job["freq3y"] = freq3y
        job["freq5y"] = freq5y
        job["last_similar"] = last_similar
        job["highlight"] = (r["first_seen"] == TODAY.isoformat())
        job["history"] = [
            {
                "id": s["id"],
                "period_start": s["period_start"],
                "period_end": s["period_end"],
                "days": days_between(s["period_start"], s["period_end"]),
                "agency": s["agency"],
                "title": s["title"],
                "rank_detail": s.get("rank_detail"),
                "family": s.get("family"),
                "city": s.get("city"),
                "summary": s.get("summary"),
                "quota": s.get("quota"),
                "gender": s.get("gender"),
                "email": s.get("email"),
                "address": s.get("address"),
                "qualification": s.get("qualification", []),
                "job_content_full": s.get("job_content_full", []),
                "contact": s.get("contact", []),
                "view_url": s.get("view_url"),
            }
            for s in siblings
        ]
        output_jobs.append(job)

    stats = {
        "open_count": len(open_jobs),
        "total_archived": len(history),
        "agency_count": len({r["agency"] for r in history}),
        "generated_at": TODAY.isoformat(),
    }

    return {"stats": stats, "jobs": output_jobs}


def main():
    mapping = load_mapping()

    print("抓取事求人開放資料 …")
    xml_text = fetch_raw_xml()

    record_tag, raw_records = parse_records(xml_text, mapping.get("record_tag_hint"))
    print(f"偵測到資料列標籤：{record_tag}，共 {len(raw_records)} 筆原始資料")

    normalized, skipped = [], []
    for raw in raw_records:
        rec, reason = normalize(raw, mapping)
        if rec:
            normalized.append(rec)
        else:
            skipped.append(reason)

    print(f"符合『簡任／薦任／委任』公務人員資格：{len(normalized)} 筆")
    print(f"被排除：{len(skipped)} 筆")
    if skipped:
        skip_sample = skipped[:5]
        print("被排除原因範例（最多顯示5筆）：")
        for s in skip_sample:
            print(f"  - {s}")

    if not normalized:
        print("[警告] 這次沒有任何一筆資料符合條件，很可能是 field_mapping.json")
        print("       的欄位對照還不正確，請先執行 inspect_feed.py 確認真實欄位名稱。")

    existing = load_history()
    merged, added = merge_history(existing, normalized)
    save_json(HISTORY_PATH, merged)
    print(f"歷史歸檔更新完成，本次新增 {added} 筆，累計 {len(merged)} 筆")

    output = build_output(merged)
    save_json(OUTPUT_PATH, output)
    print(f"已輸出網站資料：{OUTPUT_PATH}（目前刊登中 {output['stats']['open_count']} 筆）")


if __name__ == "__main__":
    main()
