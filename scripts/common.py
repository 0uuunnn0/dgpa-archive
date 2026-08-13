# -*- coding: utf-8 -*-
"""
共用工具模組
============
給 inspect_feed.py 與 fetch_and_process.py 共用的抓取／解析／判斷邏輯。

重要提醒：
- 事求人官方開放資料 XML 網址記錄在 data.gov.tw 資料集 7229：
  https://web3.dgpa.gov.tw/WANT03FRONT/AP/WANTF00003.aspx?GETJOB=Y
  更新頻率官方標示為「每12時」。
- 這是政府資料開放平臺登記的合法開放資料下載網址，使用時建議遵守
  「政府資料開放授權條款」，並在網站上註明資料來源。
- 早期（約 2015 年）有其他社群專案顯示這個頁面曾經需要先 GET 拿
  ASP.NET 的 __VIEWSTATE 等欄位、再用 POST 觸發下載，才能拿到 XML。
  目前是否仍需要這個步驟未知（本機無法連網驗證），因此下面同時準備了
  「直接 GET」與「兩段式 POST」兩種抓取方式，會自動嘗試。
"""
import re
import json
import hashlib
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime

import requests

FEED_URL = "https://web3.dgpa.gov.tw/WANT03FRONT/AP/WANTF00003.aspx?GETJOB=Y"
FEED_PAGE_URL = "https://web3.dgpa.gov.tw/WANT03FRONT/AP/WANTF00003.aspx"

# 依 jwlin/dgpa-job-site 專案經驗，這些「人員區分」代表非公務人員任用資格，
# 一律排除。實際文字請以第一次執行 inspect_feed.py 看到的內容為準，
# 若有出入請直接在這個清單增減。
EXCLUDE_PERSON_TYPES = [
    "約僱人員", "約用人員", "駐外人員", "代理教師", "代課教師",
    "實習教師", "實習老師", "聘用人員", "聘僱人員", "派用人員",
    "臨時人員", "工友", "駐衛警",
]

RANK_TRACKS = ["簡任", "薦任", "委任"]

CITIES = [
    "台北市", "臺北市", "新北市", "桃園市", "台中市", "臺中市", "台南市", "臺南市",
    "高雄市", "基隆市", "新竹市", "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣",
    "嘉義市", "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "臺東縣", "澎湖縣",
    "金門縣", "連江縣",
]


def fetch_raw_xml(session=None):
    """嘗試抓取事求人開放資料 XML，回傳原始文字內容。"""
    s = session or requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; DGPA-Archive-Bot/1.0; +for-personal-use)"
    })

    # 方法一：直接 GET 官方登記的下載網址
    resp = s.get(FEED_URL, timeout=30)
    text = resp.text.strip()
    if text.startswith("<?xml") or text.startswith("<NewDataSet") or text.startswith("<Table"):
        return text

    # 方法二：兩段式 ASP.NET postback（沿用舊版社群作法）
    resp1 = s.get(FEED_PAGE_URL, timeout=30)
    viewstate = _extract_hidden(resp1.text, "__VIEWSTATE")
    eventvalidation = _extract_hidden(resp1.text, "__EVENTVALIDATION")
    viewstategen = _extract_hidden(resp1.text, "__VIEWSTATEGENERATOR")
    form = {
        "__VIEWSTATE": viewstate or "",
        "__EVENTVALIDATION": eventvalidation or "",
        "__VIEWSTATEGENERATOR": viewstategen or "",
        "ctl00$ContentPlaceHolder1$btn_DownloadXML": "職缺 Open Data(XML)",
    }
    resp2 = s.post(FEED_PAGE_URL, data=form, timeout=30)
    return resp2.text


def _extract_hidden(html, field_id):
    m = re.search(rf'id="{field_id}"[^>]*value="([^"]*)"', html)
    return m.group(1) if m else None


def parse_records(xml_text, record_tag_hint=None):
    """
    解析 XML，回傳 (record_tag, [dict, dict, ...])
    每個 dict 是 {原始標籤名: 文字內容}，不做任何欄位對照，
    保留原始樣貌方便診斷。
    """
    root = ET.fromstring(xml_text)

    tag_counter = Counter()
    for el in root.iter():
        tag_counter[el.tag] += 1

    if record_tag_hint and tag_counter.get(record_tag_hint, 0) >= 1:
        record_tag = record_tag_hint
    else:
        # 猜測：出現次數最多、且不是根節點本身的標籤，就是「一筆一筆的資料列」
        candidates = [t for t, c in tag_counter.most_common() if t != root.tag and c > 1]
        record_tag = candidates[0] if candidates else None

    records = []
    if record_tag:
        for node in root.iter(record_tag):
            rec = {}
            for child in node:
                rec[child.tag] = (child.text or "").strip()
            if rec:
                records.append(rec)

    return record_tag, records


def resolve_field(record, mapping_list):
    """依對照表候選清單，取出第一個存在且非空的欄位值。"""
    for key in mapping_list:
        if key in record and record[key]:
            return record[key]
    return ""


def detect_rank_track(rank_text):
    """從『官職等』文字判斷屬於簡任／薦任／委任哪一軌，判斷不出來回傳 None。"""
    if not rank_text:
        return None, None
    for track in RANK_TRACKS:
        if track in rank_text:
            return track, rank_text.strip()
    return None, rank_text.strip()


def detect_city(text):
    if not text:
        return ""
    for c in CITIES:
        if c in text:
            return c.replace("臺", "台")
    return ""


ROC_RANGE_RE = re.compile(
    r"(\d{2,3})[/.\-年](\d{1,2})[/.\-月](\d{1,2})日?\s*[~～\-至]\s*(\d{2,3})[/.\-年](\d{1,2})[/.\-月](\d{1,2})日?"
)
AD_RANGE_RE = re.compile(
    r"(\d{4})[/.\-年](\d{1,2})[/.\-月](\d{1,2})日?\s*[~～\-至]\s*(\d{4})[/.\-年](\d{1,2})[/.\-月](\d{1,2})日?"
)


def parse_period(period_text):
    """
    解析『有效期間』文字，回傳 (start_iso, end_iso)。
    同時處理民國年（如 115/08/12）與西元年格式；解析不出來回傳 (None, None)，
    上層需自行決定如何處理（例如跳過該筆並記錄警告）。
    """
    if not period_text:
        return None, None

    m = AD_RANGE_RE.search(period_text)
    if m:
        y1, m1, d1, y2, m2, d2 = map(int, m.groups())
        try:
            return date(y1, m1, d1).isoformat(), date(y2, m2, d2).isoformat()
        except ValueError:
            return None, None

    m = ROC_RANGE_RE.search(period_text)
    if m:
        y1, m1, d1, y2, m2, d2 = map(int, m.groups())
        # 民國年轉西元年（民國年通常是 2~3 位數，且比對應西元年小 1911）
        y1 += 1911
        y2 += 1911
        try:
            return date(y1, m1, d1).isoformat(), date(y2, m2, d2).isoformat()
        except ValueError:
            return None, None

    return None, None


def make_record_id(rec):
    """
    幫每筆職缺產生一個穩定的識別碼，優先用官方的職缺編號；
    若沒有編號欄位，退而用『機關+職稱+期間』做 hash，
    避免同一筆職缺被重複收錄成兩筆歷史紀錄。
    """
    wid = rec.get("work_id")
    if wid:
        return f"wid:{wid}"
    raw = f"{rec.get('agency','')}|{rec.get('title','')}|{rec.get('period_start','')}|{rec.get('period_end','')}"
    return "h:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def split_bullets(text):
    """
    把『資格條件』『工作項目』『聯絡方式』這類原始長文字，
    盡量拆成一條一條的清單，方便網站用條列方式呈現。
    依序嘗試：換行 → 全形分號/頓號分隔的編號 → 句號斷句 → 整段當一條。
    """
    if not text:
        return []
    text = text.strip()

    # 先試著用換行拆
    parts = [p.strip() for p in re.split(r"[\r\n]+", text) if p.strip()]
    if len(parts) > 1:
        return [re.sub(r"^[一二三四五六七八九十\d]+[、.．)）]\s*", "", p) for p in parts]

    # 試著用「一、二、三、」或「1. 2. 3.」這類編號拆
    numbered = re.split(r"(?=[一二三四五六七八九十]+、)|(?=\d+[.、])", text)
    numbered = [p.strip() for p in numbered if p.strip()]
    if len(numbered) > 1:
        return [re.sub(r"^[一二三四五六七八九十\d]+[、.．)）]\s*", "", p) for p in numbered]

    # 最後試著用句號拆
    sentences = [p.strip() for p in re.split(r"[。；]", text) if p.strip()]
    if len(sentences) > 1:
        return sentences

    return [text]


def days_between(start_iso, end_iso):
    if not start_iso or not end_iso:
        return None
    d1 = date.fromisoformat(start_iso)
    d2 = date.fromisoformat(end_iso)
    return (d2 - d1).days + 1
