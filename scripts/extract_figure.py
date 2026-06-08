#!/usr/bin/env python3
"""定位 / 渲染 / 裁剪论文关键图。配图判断需要"看"，所以分三步，中间由 agent 用视觉定框。

依赖: poppler 的 pdftoppm；Pillow（pip install Pillow）

# 1) 定位：找 figure_caption / figure_ref 在第几页
python extract_figure.py locate --workdir DIR --id p10 --ref "Figure 2" --caption "Framework of NeoVerse"

# 2) 渲染：把某页渲染成整页 png（供 agent 查看定框）
python extract_figure.py render --workdir DIR --id p10 --page 4 [--dpi 150]
#   -> figures/p10_page.png

# 3) 裁剪：按坐标裁出图（left top right bottom，基于渲染出的整页像素），缩到宽<=1100
python extract_figure.py crop --workdir DIR --id p10 --box 28 52 1248 398
#   -> figures/fig_p10.png   （build_report.py 会自动嵌入存在 fig_<id>.png 的卡片）

典型循环: locate -> render -> 查看整页定框 -> crop -> 查看 fig 验证（不满意改 box 重 crop）。
只为少数确有助于理解的架构/流程图做，别每篇都配。
"""
import argparse, pathlib, re, subprocess, sys


def locate(a):
    txt = (pathlib.Path(a.workdir) / "txt" / f"{a.id}.txt").read_text(errors="ignore")
    pages = txt.split("\f")
    num = (a.ref or "").split()[-1] if a.ref else ""
    label = [i + 1 for i, p in enumerate(pages)
             if num and re.search(rf"Figure\s*{num}\s*[.:]", p, re.I)]
    capkey = re.sub(r"\s+", "", a.caption or "")[:18]
    capp = [i + 1 for i, p in enumerate(pages)
            if capkey and capkey in re.sub(r"\s+", "", p)]
    print(f"{a.id} {a.ref}: 共 {len(pages)} 页 | 含'Figure {num}.'的页 {label} | 图注文本所在页 {capp}")
    print("建议渲染页:", (capp or label or ['?'])[0])


def render(a):
    wd = pathlib.Path(a.workdir)
    pdf = wd / "pdf" / f"{a.id}.pdf"
    prefix = wd / "figures" / f"{a.id}_raw"
    subprocess.run(["pdftoppm", "-png", "-f", str(a.page), "-l", str(a.page),
                    "-r", str(a.dpi), str(pdf), str(prefix)],
                   check=True, capture_output=True)
    raws = sorted((wd / "figures").glob(f"{a.id}_raw*.png"))
    if not raws:
        sys.exit("渲染失败")
    out = wd / "figures" / f"{a.id}_page.png"
    raws[0].replace(out)
    from PIL import Image
    w, h = Image.open(out).size
    print(f"渲染 -> {out}  尺寸 {w}x{h}（裁剪 box 坐标基于这个尺寸）")


def crop(a):
    from PIL import Image
    wd = pathlib.Path(a.workdir)
    src = wd / "figures" / f"{a.id}_page.png"
    l, t, r, b = a.box
    im = Image.open(src).crop((l, t, r, b))
    if im.width > 1100:
        im = im.resize((1100, int(im.height * 1100 / im.width)), Image.LANCZOS)
    out = wd / "figures" / f"fig_{a.id}.png"
    im.save(out)
    print(f"裁剪 -> {out}  {im.width}x{im.height}（查看验证；不满意改 box 重裁）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("locate"); p.add_argument("--workdir", required=True); p.add_argument("--id", required=True); p.add_argument("--ref", default=""); p.add_argument("--caption", default=""); p.set_defaults(fn=locate)
    p = sub.add_parser("render"); p.add_argument("--workdir", required=True); p.add_argument("--id", required=True); p.add_argument("--page", type=int, required=True); p.add_argument("--dpi", type=int, default=150); p.set_defaults(fn=render)
    p = sub.add_parser("crop"); p.add_argument("--workdir", required=True); p.add_argument("--id", required=True); p.add_argument("--box", type=int, nargs=4, required=True, metavar=("L", "T", "R", "B")); p.set_defaults(fn=crop)
    a = ap.parse_args(); a.fn(a)
