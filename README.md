# 公職缺歷史檔案庫 — 部署教學（免寫程式版）

這份教學假設你**沒有寫過程式**，全程只需要用瀏覽器點按鈕。完成後，你會有一個
每天自動更新一次、網址可以分享給任何人看的網站。

> **這一版說明**：網站介面已經是最終的橘藍配色版本，並且已經接上真實的
> 「事求人」開放資料。**留言板（面試心得／職缺心得）這次先不上線**，
> 之後想加的話再跟 Claude 說一聲即可，現有的查詢／搜尋／篩選／完整公告功能都是完整的。

---

## 第一部分：把專案放到你自己的 GitHub 帳號下

1. **申請 GitHub 帳號**（如果還沒有）：前往 https://github.com/signup，用 Email 註冊，免費。
2. **建立一個新的 Repository（專案倉庫）**：
   - 登入後點右上角「+」→「New repository」
   - Repository name 填 `dgpa-archive`（或你喜歡的名字）
   - 選擇 **Public**（GitHub Pages 免費方案需要公開倉庫）
   - 其他選項不用動，按「Create repository」
3. **把 Claude 給你的檔案上傳上去**：
   - 在剛建立的空倉庫頁面，點「uploading an existing file」
   - 把整個資料夾（`.github`、`scripts`、`docs`、`data`、`README.md`）拖進去上傳
   - 下方填寫 commit 訊息（隨便寫，例如「初始上傳」），按「Commit changes」
   - **注意**：資料夾裡有一個看不見的 `.github` 資料夾，網頁上傳介面通常抓得到，但如果你是把整個資料夾壓縮成 zip 再上傳，記得先解壓縮再逐一拖曳資料夾進去，不要整包 zip 上傳（GitHub 網頁版不會自動解壓縮）。

---

## 第二部分：打開兩個必要開關

1. **允許 Actions 有寫入權限**（不然它沒辦法把每天抓到的新資料存回去）：
   - 倉庫頁面 → `Settings` → 左側選單 `Actions` → `General`
   - 拉到最下面「Workflow permissions」，選 **Read and write permissions**
   - 按「Save」
2. **開啟 GitHub Pages**（讓網站有公開網址）：
   - `Settings` → 左側選單 `Pages`
   - 「Build and deployment」→ Source 選 **GitHub Actions**（不要選 Deploy from a branch，那個模式會自動套用 GitHub 內建的 Jekyll 建置，跟我們的純 HTML 網站不合，容易出現 `jekyll-theme-primer` 之類的錯誤）
   - 這個專案裡已經附了一個 `.github/workflows/deploy_pages.yml`，它會直接把 `docs` 資料夾原封不動部署成網站，完全不會經過 Jekyll
   - 等 1～2 分鐘，Pages 頁面上方會出現你的網址，長得像：
     `https://你的帳號.github.io/dgpa-archive/`

---

## 第三部分：手動跑第一次，確認資料抓得到

1. 倉庫頁面上方點 `Actions`
2. 左側選「每日更新職缺資料」
3. 右邊點「Run workflow」→ 再點一次綠色的「Run workflow」按鈕
4. 等它跑完（通常 1 分鐘內），點進去那次執行紀錄，展開每個步驟看 log

**這一步很關鍵，請看兩個地方：**

- 「執行診斷」那個步驟：會印出真實抓到的 XML 欄位名稱和前 3 筆資料內容
- 「抓取並更新資料」那個步驟：最後會告訴你「符合公務人員資格：N 筆」

如果 N 是 0，代表 `scripts/field_mapping.json` 裡的欄位名稱對不上真實資料，
**這時候請把「執行診斷」那個步驟的完整輸出複製起來，貼給 Claude**，
我會幫你把 `field_mapping.json` 改成正確的欄位名稱（大概 5 分鐘內可以搞定），
你只要把改好的檔案內容貼回 GitHub 網頁版覆蓋掉原本的檔案即可，一樣不用寫程式。

---

## 之後就不用管了

`.github/workflows/daily_fetch.yml` 已經設定好**每天台北時間凌晨 1 點自動執行**，
會自己抓資料、更新 `data/history.json`（永久歸檔，只會增加不會刪除）、
重新產生 `docs/data.json`，網站會自動反映最新內容。

---

## 檔案說明

| 檔案 | 用途 |
|---|---|
| `scripts/field_mapping.json` | 真實 XML 欄位名稱對照表（初次需要確認一次） |
| `scripts/common.py` | 抓取、解析、日期換算、職等/縣市判斷等共用邏輯 |
| `scripts/inspect_feed.py` | 診斷用，印出真實資料長相 |
| `scripts/fetch_and_process.py` | 每天真正執行的主程式 |
| `data/history.json` | 累積歸檔的完整歷史資料（不會被覆蓋刪除） |
| `docs/data.json` | 網站讀取用的資料（每天自動重新產生） |
| `docs/index.html` | 網站畫面本身 |
| `.github/workflows/daily_fetch.yml` | 每日排程設定 |
| `.github/workflows/deploy_pages.yml` | 網站部署設定（不經過 Jekyll，直接部署 docs 資料夾） |

## 之後想調整的地方

- **排除規則**：`scripts/common.py` 裡的 `EXCLUDE_PERSON_TYPES`，可以增減要排除的人員類別文字。
- **相似職缺的判斷邏輯**：目前是用「同機關＋同職系」判斷是否為相似職缺（見
  `scripts/fetch_and_process.py` 的 `build_output` 函式），如果想改成「同機關＋同職稱關鍵字」
  或加入縣市條件，跟 Claude 說一聲，我可以幫你調整。
- **排程時間**：改 `.github/workflows/daily_fetch.yml` 裡的 `cron` 那一行即可。

有任何一步卡住，把錯誤訊息或截圖貼給我，我可以繼續協助排查。
