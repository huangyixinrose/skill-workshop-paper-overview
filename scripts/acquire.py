#!/usr/bin/env python3
"""采集 + 预处理：下载 manifest 列出的 PDF，抽文本，打印体量画像。

用法:
    python acquire.py --workdir ./xxx_review [--jobs 8]

读取: {workdir}/manifest.json   形如 [{"id":"p01","title":"...","url":"https://..."}, ...]
产出: {workdir}/pdf/<id>.pdf, {workdir}/txt/<id>.txt, {workdir}/data/acquire_report.json

依赖: curl, poppler 的 pdftotext / pdfinfo（macOS: brew install poppler）
设计要点: 抽成纯文本喂模型，不要把整页 PDF 当图片喂——省约 3× token。
"""
import argparse, json, os, subprocess, shutil, concurrent.futures, pathlib


def need(bin_):
    if not shutil.which(bin_):
        raise SystemExit(f"缺少依赖: {bin_}（macOS: brew install poppler；curl 系统自带）")


def download(item, pdfdir):
    pid, url = item["id"], item["url"]
    out = os.path.join(pdfdir, pid + ".pdf")
    try:
        subprocess.run(["curl", "-sL", "--max-time", "180", "-o", out, url],
                       check=True, capture_output=True)
        kind = subprocess.run(["file", "-b", out], capture_output=True, text=True).stdout
        if "PDF" not in kind:
            return pid, "fail-not-pdf", 0
        return pid, "ok", os.path.getsize(out)
    except Exception as e:
        return pid, f"fail:{str(e)[:50]}", 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    need("curl"); need("pdftotext"); need("pdfinfo")

    wd = pathlib.Path(a.workdir)
    pdfdir = wd / "pdf"; txtdir = wd / "txt"; datadir = wd / "data"
    for d in (pdfdir, txtdir, datadir, wd / "figures"):
        d.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((wd / "manifest.json").read_text())
    print(f"清单 {len(manifest)} 篇，开始下载（并发 {a.jobs}）…")

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for pid, status, size in ex.map(lambda it: download(it, str(pdfdir)), manifest):
            results[pid] = {"download": status, "pdf_bytes": size}

    report = []
    total_chars = 0
    for it in manifest:
        pid = it["id"]; r = results[pid]
        if r["download"] == "ok":
            pdf = pdfdir / (pid + ".pdf"); txt = txtdir / (pid + ".txt")
            subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)],
                           capture_output=True)
            chars = len(txt.read_text(errors="ignore")) if txt.exists() else 0
            pages = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
            pages = next((ln.split()[1] for ln in pages.splitlines()
                          if ln.startswith("Pages")), "?")
            r.update(chars=chars, pages=pages); total_chars += chars
        report.append({"id": pid, "title": it.get("title", ""), **r})

    ok = sum(1 for x in report if x["download"] == "ok")
    fail = [x for x in report if x["download"] != "ok"]
    (datadir / "acquire_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2))

    print(f"\n成功 {ok}/{len(manifest)}；总文本 {total_chars:,} 字符（≈ {total_chars//4:,} token）")
    if fail:
        print("失败（需手工补链接或归入 recovery）:")
        for x in fail:
            print(f"  {x['id']}  {x['download']}  {x['title'][:50]}")
    print(f"画像写入 {datadir/'acquire_report.json'}")


if __name__ == "__main__":
    main()
