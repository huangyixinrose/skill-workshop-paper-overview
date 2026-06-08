# recon —— 从主页提取完整论文清单

## 通用原则：有标题没链接时，主动找权威出处

当 accepted-papers 页面只列出论文标题（没有 PDF 或详情页链接）时，不要卡住——根据该会议的托管平台，主动去找权威出处把 PDF 链接解析出来：

- **OpenReview 托管**（ICLR / NeurIPS 等 workshop）→ 用 OpenReview API 批量拿链接，见下方专节。
- **CVF 托管**（CVPR / ICCV / ECCV）→ 到 CVF proceedings 索引页，按标题定位 `papers/<STEM>_paper.pdf`。
- **其它平台**→ 根据站点结构推断，或结合 arXiv 检索补链接。
- **实在解析不了**→ 退回让用户手工贴链接清单，不要凭空猜测。

---

把这段作为 WebFetch 的 prompt（对 workshop/会议主页 URL）：

> 提取本页**全部**accepted/收录论文。对每一篇输出：① 完整标题；② 它的 PDF 直链或详情页链接的**精确 href**；③ 赛道（archival/proceedings 还是 non-archival/workshop-only）。不要漏、不要改写标题。若某篇标注"withheld / 不公开 / 仅标题"，单独标出"无全文"。如果分了多个 track，每个 track 都要覆盖。逐条输出，链接照抄原文。

把结果整理成 `manifest.json`：
```json
[{"id":"p01","title":"...","url":"https://...pdf","track":"archival"}, ...]
```

链接补全规则（常见坑）：
- **站内相对链接**：补全为 `<主页域名>/<相对路径>`。
- **CVF openaccess**：详情页 `…/html/<STEM>_paper.html` ⇒ PDF 是 `…/papers/<STEM>_paper.pdf`（STEM 必须逐字一致；个别论文 PDF 可能尚未上线，会 404）。
- **arXiv**：用 `https://arxiv.org/pdf/<id>`。
- **OpenReview**：用 `…/pdf?id=<id>`。
- **无全文/撤稿**：不放进 manifest，放进 `data/missing.json`（只留 title），交给 recovery 子代理检索。

---

## OpenReview 托管的 workshop（ICLR / NeurIPS 等）

**症状**：accepted-papers 页面只列论文标题（可能带作者），但每篇没有 PDF 或 OpenReview 直链。而 OpenReview 的 group 页（`openreview.net/group?id=...`）是 JS 动态渲染的，WebFetch 抓不到论文列表。

**解法**：改用 OpenReview API——不要用 WebFetch 抓 group 页，用 curl 或脚本直接打 API。

### 接口细节（v2）

- **端点**：`https://api2.openreview.net/notes?content.venueid=<VENUEID>&limit=1000`
- **VENUEID 怎么拿**：从 workshop 的 OpenReview group 链接 `openreview.net/group?id=<VENUEID>` 里取。形如 `ICLR.cc/2025/Workshop/World_Models`。
- **返回 JSON 结构**：`notes` 数组，每条 note 含：
  - `id` —— note 唯一标识
  - `content.title.value` —— 论文标题
  - `content.authors.value` —— 作者列表
  - `content.pdf.value` —— 相对路径，形如 `/pdf/<hash>.pdf`
  - `content.abstract.value` —— 摘要全文
  - `content.venueid.value` —— 所属 venue
- **PDF 直链拼法**：`content.pdf.value` 前面拼上 `https://openreview.net`，即 `https://openreview.net/pdf/<hash>.pdf`；或用通用形式 `https://openreview.net/pdf?id=<note id>`。
- **额外好处**：API 返回的 abstract 字段可直接入库，省去后续逐篇抓取摘要的步骤。

### 注意事项

- venueid 过滤返回的结果可能比 accepted-papers 页面公布的"录用篇数"多出几条（含撤稿 / 拒稿未清理的条目）。以 accepted-papers 页面的标题清单为准来确定哪些是真正录用的，必要时按标题与 API 结果对齐、剔除多余条目。
- 如果 API 返回为空或报错，检查 VENUEID 是否正确（大小写、斜杠、下划线都要精确匹配）。

---

id 用 `p01, p02 …` 顺序编号，与后续所有产物对齐。
下载若失败（404/非 PDF），把该篇移入 `data/missing.json` 走 recovery，不要卡住主流程。
