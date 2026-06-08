#!/usr/bin/env python3
"""确定性组装器：把结构化数据渲染成单文件 HTML 综述。纯渲染，不调用模型。

用法: python build_report.py --workdir ./xxx_review

读取 {workdir}/data/:
    digests.json   list[digest]（见 schemas/digest.schema.json）
    sections.json  list[str]，顺序与 cats.json 对齐
    cats.json      list[str]，主线类目（决定分组与顺序）
    recovery.txt   缺失论文检索结果（markdown 文本，可空）
    preface.html   编者"整体判断"HTML 片段（卷首）
    meta.json      {"title","subtitle","note"}（缺省有兜底）
{workdir}/figures/fig_<id>.png  存在则嵌入对应卡片（base64）

产出 {workdir}/report.html （单文件，图以 base64 内联，可离线）
"""
import argparse, json, pathlib, re, html, base64

NUM = "一二三四五六七八九十"


def esc(s): return html.escape(s or "")


def trunc(s, n):
    s = (s or "").strip().replace("\n", " ")
    return esc(s[:n] + "…") if len(s) > n else esc(s)


def md(text):
    """极简 markdown -> html：## ### **粗** --- 列表 段落"""
    text = html.escape(text or "")
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    out, para, in_ul = [], [], False
    def flush():
        nonlocal para
        if para: out.append("<p>" + " ".join(para).strip() + "</p>"); para = []
    def closeul():
        nonlocal in_ul
        if in_ul: out.append("</ul>"); in_ul = False
    for ln in text.split("\n"):
        s = ln.strip()
        if not s: flush(); closeul(); continue
        if s.startswith("### "): flush(); closeul(); out.append("<h4>" + s[4:] + "</h4>")
        elif s.startswith("## "): flush(); closeul(); out.append("<h3>" + s[3:] + "</h3>")
        elif s == "---": flush(); closeul(); out.append("<hr>")
        elif s.startswith("- "):
            flush()
            if not in_ul: out.append("<ul>"); in_ul = True
            out.append("<li>" + s[2:] + "</li>")
        else: para.append(s)
    flush(); closeul()
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    a = ap.parse_args()
    wd = pathlib.Path(a.workdir); D = wd / "data"

    digests = json.loads((D / "digests.json").read_text())
    sections = json.loads((D / "sections.json").read_text()) if (D / "sections.json").exists() else []
    cats = json.loads((D / "cats.json").read_text())
    recovery = (D / "recovery.txt").read_text() if (D / "recovery.txt").exists() else ""
    preface = (D / "preface.html").read_text() if (D / "preface.html").exists() else "<p>（未提供整体判断）</p>"
    meta = json.loads((D / "meta.json").read_text()) if (D / "meta.json").exists() else {}
    title = meta.get("title", "Workshop 论文综述")
    subtitle = meta.get("subtitle", "")
    note = meta.get("note", "")

    def img_data(pid):
        p = wd / "figures" / f"fig_{pid}.png"
        if p.exists():
            return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()
        return None

    by = {c: [] for c in cats}
    for d in digests:
        by.setdefault(d.get("category", "其他"), []).append(d)

    # ---- 总表 ----
    tbl = ['<div class="tblwrap">']
    for ci, c in enumerate(cats):
        ds = by.get(c, [])
        if not ds: continue
        tbl.append(f'<div class="catbar">主线{NUM[ci]}　{esc(c)}　<span class="cnt">{len(ds)} 篇</span></div>')
        tbl.append('<table><thead><tr><th>论文</th><th>团队</th><th>要解决的问题</th><th>关键结果</th><th>码</th></tr></thead><tbody>')
        for d in ds:
            code = (d.get("code_url") or "").strip()
            codecell = f'<a href="{esc(code)}">↗</a>' if code else "—"
            tbl.append("<tr>"
                f'<td class="ti"><b>{esc(d["title"][:46])}</b> <span class="tk">{esc(d.get("track",""))}</span></td>'
                f'<td>{trunc(d.get("team","未标注"),18)}</td>'
                f'<td>{trunc(d.get("problem",""),58)}</td>'
                f'<td>{trunc(d.get("key_results",""),92)}</td>'
                f'<td class="code">{codecell}</td></tr>')
        tbl.append("</tbody></table>")
    tbl.append("</div>")

    # ---- 卡片 ----
    cards = []
    for ci, c in enumerate(cats):
        ds = by.get(c, [])
        if not ds: continue
        cards.append(f'<h3 id="cat{ci}" class="cath">主线{NUM[ci]} · {esc(c)} <span class="cnt">{len(ds)} 篇</span></h3>')
        for d in ds:
            pid = d["id"]
            award = f' <span class="b best">{esc(d["award"])}</span>' if d.get("award") else ""
            fig = img_data(pid)
            figcap = d.get("figure_caption_zh") or (
                f'{esc(d.get("figure_ref",""))} {esc(d.get("figure_caption",""))}'.strip())
            figblk = (f'<figure><img src="{fig}" alt="{esc(d["title"][:30])}">'
                      f'<figcaption>{esc(figcap)}</figcaption></figure>') if fig else ""
            code = (d.get("code_url") or "").strip()
            codeblk = (f'<div class="detail"><span class="k">代码/主页</span>'
                       f'<div class="v"><a href="{esc(code)}">{esc(code)}</a></div></div>') if code else ""
            note_blk = f'<div class="note">{esc(d["cat_note"])}</div>' if d.get("cat_note") else ""
            cards.append(f'''<div class="card" id="{esc(pid)}">
  <div class="chd"><span class="cno">{esc(pid)}</span><span class="ctitle">{esc(d["title"])}</span>{award}</div>
  <div class="badges"><span class="b track">{esc(d.get("track",""))}</span><span class="b team">{esc(d.get("team","未标注"))}</span></div>
  {note_blk}
  {figblk}
  <div class="cardzh">{esc(d.get("card_zh",""))}</div>
  <div class="detail"><span class="k">要解决的问题</span><div class="v">{esc(d.get("problem",""))}</div></div>
  <div class="detail"><span class="k">核心方法</span><div class="v">{esc(d.get("method",""))}</div></div>
  <div class="detail"><span class="k">关键结果</span><div class="v">{esc(d.get("key_results",""))}</div></div>
  <div class="detail"><span class="k">局限</span><div class="v">{esc(d.get("limitations","未报告"))}</div></div>
  <div class="detail rel"><span class="k">相关度与启发</span><div class="v">{esc(d.get("relevance",""))}</div></div>
  {codeblk}
</div>''')

    # ---- 综述 ----
    syn = []
    for ci, c in enumerate(cats):
        sec = sections[ci] if ci < len(sections) else ""
        if not sec: continue
        syn.append(f'<div class="synthblock" id="syn{ci}"><div class="synthtag">主线{NUM[ci]}</div>{md(sec)}</div>')

    recover_html = f'<h2 id="recover">未公开全文 / 缺失论文（检索兜底）</h2><div class="recover">{md(recovery)}</div>' if recovery.strip() else ""

    out = (TPL.replace("__TITLE__", esc(title))
              .replace("__SUBTITLE__", esc(subtitle))
              .replace("__NOTE__", esc(note))
              .replace("__PREFACE__", preface)
              .replace("__TABLES__", "\n".join(tbl))
              .replace("__CARDS__", "\n".join(cards))
              .replace("__SECTIONS__", "\n".join(syn))
              .replace("__RECOVER__", recover_html))
    outp = wd / "report.html"
    outp.write_text(out)
    print(f"成品: {outp} | {len(out)//1024} KB | 论文 {len(digests)} 篇 | "
          f"配图 {sum(1 for d in digests if img_data(d['id']))} 张")


TPL = '''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><title>__TITLE__</title>
<style>
:root{--bg:#f6f5f2;--ink:#1c1c1a;--muted:#6b6960;--line:#ddd9d1;--card:#fff;--accent:#2f6f6a;--accent2:#9a6b2f;--hl:#fbf3e2;--hlbd:#e7d4ab;--pf:#eef4f3;--pfbd:#cfe0dd}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;line-height:1.78;padding:42px 18px;font-size:15px}
.wrap{max-width:1000px;margin:0 auto}
h1{font-size:25px;margin:0 0 6px}
h2{font-size:20px;margin:46px 0 16px;padding-bottom:8px;border-bottom:2px solid var(--accent);color:var(--accent)}
h3{font-size:16.5px;margin:24px 0 8px}h4{font-size:15px;margin:16px 0 4px;color:var(--accent2)}
.sub{color:var(--muted);font-size:14px}
.meta{font-size:13px;color:var(--muted);background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:14px 0}
.preface{background:var(--pf);border:1px solid var(--pfbd);border-radius:14px;padding:22px 26px;margin-top:8px}
.preface .lead{font-size:16px;margin-top:0}
.preface h3{color:#27514c;border-left:4px solid var(--accent);padding-left:10px;margin-top:24px}
ol.judge{padding-left:22px}ol.judge li{margin:10px 0}
.preface .kicker{background:#fff;border:1px dashed var(--accent);border-radius:10px;padding:12px 16px;margin-top:18px;font-size:14.5px}
.tblwrap{overflow-x:auto}
.catbar{background:#eceae4;border-left:4px solid var(--accent);font-weight:700;padding:7px 12px;margin:18px 0 0;border-radius:4px}
.catbar .cnt,.cath .cnt{font-weight:400;color:var(--muted);font-size:13px}
table{border-collapse:collapse;width:100%;font-size:12.6px;background:var(--card);margin-bottom:6px;min-width:900px}
th,td{border:1px solid var(--line);padding:7px 9px;vertical-align:top;text-align:left}
th{background:#f0eee8;font-weight:700}
td.ti{min-width:210px}.tk{color:#999;font-size:11px}
td.code{text-align:center}td.code a{color:var(--accent);text-decoration:none;font-size:16px}
.cath{margin:34px 0 6px;color:var(--accent);border-bottom:1px dashed var(--line);padding-bottom:6px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin:16px 0;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.chd{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.cno{font-weight:800;color:#fff;background:var(--accent);border-radius:6px;padding:1px 8px;font-size:12px}
.ctitle{font-weight:800;font-size:17px}
.badges{margin:8px 0 12px;display:flex;gap:8px;flex-wrap:wrap}
.b{font-size:11.5px;border-radius:20px;padding:2px 11px;font-weight:600}
.b.track{background:#eef0ee;color:#666}.b.team{background:#e3eee9;color:var(--accent)}.b.best{background:#fbe9c8;color:#7a571a}
figure{margin:6px 0 14px}figure img{width:100%;border:1px solid var(--line);border-radius:8px;display:block}
figcaption{font-size:12px;color:var(--muted);margin-top:6px}
.cardzh{background:var(--hl);border:1px solid var(--hlbd);border-radius:10px;padding:12px 15px;font-size:14.5px;margin-bottom:14px}
.detail{margin:10px 0}.detail .k{font-weight:700;color:var(--accent2);font-size:13.5px}.detail .v{font-size:14px;margin-top:2px}
.detail.rel .k{color:var(--accent)}.detail.rel .v{background:#f3f8f6;border-radius:8px;padding:8px 12px}
.note{font-size:12.5px;color:var(--muted);background:#faf6ee;border-left:3px solid var(--hlbd);padding:6px 10px;border-radius:4px;margin:8px 0}
.detail .v a{color:var(--accent);word-break:break-all}
.synthblock{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 24px;margin:16px 0;position:relative}
.synthtag{position:absolute;top:-10px;left:18px;background:var(--accent);color:#fff;font-size:12px;padding:2px 10px;border-radius:10px}
.synthblock h3{color:var(--accent);margin-top:8px}.synthblock hr{border:none;border-top:1px dashed var(--line);margin:16px 0}
.recover{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 22px}
a{color:var(--accent)}
</style></head><body><div class="wrap">
<h1>__TITLE__</h1>
<div class="sub">__SUBTITLE__</div>
<div class="meta">__NOTE__</div>
<h2 id="preface">整体判断（编者）</h2>
<div class="preface">__PREFACE__</div>
<h2 id="tables">分类总表</h2>
__TABLES__
<h2 id="cards">逐篇速查卡</h2>
__CARDS__
<h2 id="synth">主线综述</h2>
__SECTIONS__
__RECOVER__
</div></body></html>'''


if __name__ == "__main__":
    main()
