# -*- coding: utf-8 -*-
"""
第一次設定時執行這支程式，用來確認事求人開放資料 XML 的真實欄位長相。
執行方式（GitHub Actions 裡會自動執行，你也可以在 Actions 頁面手動觸發）：
    python scripts/inspect_feed.py

會印出：
1. 偵測到「每一筆職缺」是用哪個 XML 標籤包起來的
2. 總共抓到幾筆資料
3. 前 3 筆資料的「原始欄位名稱: 內容」，方便對照 field_mapping.json

看完之後，把 field_mapping.json 裡每個邏輯欄位改成你在這裡看到的實際標籤名稱即可。
"""
import json
import sys
from common import fetch_raw_xml, parse_records

def main():
    print("正在抓取事求人開放資料 XML …")
    try:
        xml_text = fetch_raw_xml()
    except Exception as e:
        print(f"[錯誤] 抓取失敗：{e}")
        sys.exit(1)

    print(f"抓到內容長度：{len(xml_text)} 字元")
    print("內容開頭 300 字：")
    print(xml_text[:300])
    print("-" * 60)

    try:
        record_tag, records = parse_records(xml_text)
    except Exception as e:
        print(f"[錯誤] XML 解析失敗：{e}")
        print("可能代表抓回來的不是 XML（例如是 HTML 表單頁面），")
        print("請把上面『內容開頭 300 字』的結果貼給 Claude 協助判斷。")
        sys.exit(1)

    print(f"偵測到的『每筆職缺』標籤：{record_tag}")
    print(f"總筆數：{len(records)}")
    print("-" * 60)

    for i, rec in enumerate(records[:3]):
        print(f"== 第 {i+1} 筆原始內容 ==")
        for k, v in rec.items():
            print(f"  {k}: {v}")
        print()

    if records:
        all_keys = set()
        for r in records:
            all_keys.update(r.keys())
        print("此資料集出現過的所有欄位名稱：")
        print(json.dumps(sorted(all_keys), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
