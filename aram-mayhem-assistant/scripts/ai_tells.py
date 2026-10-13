# -*- coding: utf-8 -*-
"""数一份 HTML 报告里有多少「AI 味」标记。

用法：
    python ai_tells.py 报告.html

判据抄自 khazix-writer 的「绝对禁区」：不用冒号、不用破折号、不用直双引号，
不大量加粗、不堆编号小标题，外加一批禁用词。改稿前后各跑一次，看数字掉没掉。

⚠️ **计数只是线索，必须配上下文看。** 这个脚本为了数标点会先把空白删掉，
结果会把表格里相邻单元格的占位符「—」**粘成**「——」，凭空造出假命中
（我第一版就被它骗过一次，差点去修一个不存在的问题）。所以看到破折号非零，
先用 grep 把上下文打出来再决定。
"""
import io
import re
import sys

BAN_WORDS = ["换句话说", "本质上", "值得注意", "综上所述", "首先", "其次",
             "说白了", "这意味着", "不可否认", "接下来让我们", "让我们"]


def main(path):
    s = io.open(path, encoding="utf-8").read()

    # 只留可见文字：剔掉图和样式，再剥标签
    t = re.sub(r"<svg.*?</svg>", " ", s, flags=re.S)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r'data:image/[^"]+', " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    flat = re.sub(r"\s+", "", t)
    print("可见文字约 %d 字" % len(flat))

    print("\n-- 禁用词 --")
    hit = [(w, flat.count(w)) for w in BAN_WORDS if flat.count(w)]
    print("  " + ("、".join("%s×%d" % h for h in hit) if hit else "(无)"))

    print("\n-- 标点（目标全是 0）--")
    for ch, lab in [("：", "冒号"), ("——", "破折号"),
                    ("“", "左双引号"), ('"', "直双引号")]:
        print("  %-6s %d" % (lab, flat.count(ch)))

    print("\n-- 结构量 --")
    for lab, pat in [("加粗", r"<(b|strong)[ >]"), ("表格", r"<table"),
                     ("小标题", r"<h[23][ >]"), ("列表项", r"<li[ >]")]:
        print("  %-6s %d" % (lab, len(re.findall(pat, s))))

    print("\n破折号非零时，先把上下文打出来再判断（见文件头那条警告）。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("用法: python ai_tells.py <报告.html>")
    main(sys.argv[1])
