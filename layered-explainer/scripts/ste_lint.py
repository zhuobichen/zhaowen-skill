#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ste_lint.py -- ASD-STE100 heuristic checker (sentence length / style candidates).

It is NOT a compliance checker. The ASD approved-word dictionary is copyrighted;
this script ships no word list. It applies the public writing rules plus a small
table of common substitutions and reports CANDIDATES, never verdicts.

Usage:
    python ste_lint.py <file> [--mode procedural|descriptive|both]
                              [--lang auto|en|zh] [--stdout]

Default: report goes to <file>.ste-lint.md ; terminal prints an ASCII-only
summary. (Windows CJK consoles are GBK -- printing Chinese directly crashes.)
"""

import argparse
import os
import re
import sys

CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
FENCE = re.compile(r"```.*?```", re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")
MD_EMPHASIS = re.compile(r"[*_>#]")

# English: word -> STE-style replacement. Left side is what to look for.
EN_SWAPS = {
    r"\butili[sz]e[sd]?\b": "use",
    r"\bprior to\b": "before",
    r"\bin order to\b": "to",
    r"\bensure[sd]?\b": "make sure",
    r"\badditional\b": "more",
    r"\bcommence[sd]?\b": "start",
    r"\bterminate[sd]?\b": "stop",
    r"\bsufficient\b": "enough",
    r"\battempt(?:s|ed)?\b": "try",
    r"\bassist(?:s|ed)?\b": "help",
    r"\bobtain(?:s|ed)?\b": "get",
    r"\bdemonstrate[sd]?\b": "show",
    r"\bindicate[sd]?\b": "show",
    r"\bapproximately\b": "about",
    r"\bsubsequent\b": "next",
    r"\binitial(?:e|es|ed)\b": "start",
    r"\bmodif(?:y|ies|ied)\b": "change",
    r"\bmain\b": "primary",
    r"\bcomprise[sd]?\b": "have / include",
    r"\bfacilitate[sd]?\b": "help",
}

# Chinese dilution / nominalisation. phrase -> how to fix.
ZH_DILUTION = {
    "进行": "直接动词化：进行检测 -> 检测",
    "实施": "直接动词化：实施测试 -> 测试",
    "予以": "删，直接动词",
    "加以": "删，直接动词",
    "作出": "直接动词化：作出判断 -> 判断",
    "有效地": "删（除非有度量）",
    "一定程度上": "删",
    "值得注意的是": "删，直接说事",
    "综上所述": "删",
    "需要注意的是": "删",
    "相关": "多数可删",
    "能够": "能",
    "是否": "改写或删",
    "众所周知": "删",
}

# Chinese style candidates the rule table names but plain substring search misses.
ZH_STYLE = (
    ("passive", re.compile(r"被[一-鿿]"), "少用被动；改主动"),
    ("perfect", re.compile(r"已(?:经)?[一-鿿]{1,6}(?:了|过)"), "少用完成时"),
    ("-ing", re.compile(r"正在[一-鿿]{0,6}(?:中|着)"), "少用进行时"),
)

PASSIVE_EN = re.compile(
    r"\b(?:is|are|was|were|be|been|being|get|gets|got)\s+\w+(?:ed|en)\b", re.I
)
PERFECT_EN = re.compile(r"\b(?:has|have|had)\s+\w+(?:ed|en)\b", re.I)
PROG_EN = re.compile(r"\b(?:is|are|was|were|be)\s+\w+ing\b", re.I)


def read_text(path):
    """utf-8 first, then gbk (this machine has plenty of GBK files)."""
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def detect_lang(text):
    han = len(CJK.findall(text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if han == 0:
        return "en"
    if latin == 0:
        return "zh"
    return "zh" if han > latin / 2 else "en"


def clean(text):
    text = FENCE.sub("\n", text)
    text = INLINE_CODE.sub(" ", text)
    lines = []
    for ln in text.split("\n"):
        if ln.lstrip().startswith("|"):       # markdown table rows
            continue
        if ln.lstrip().startswith("<!--"):
            continue
        lines.append(MD_EMPHASIS.sub("", ln))
    return "\n".join(lines)


def split_sentences(text, lang):
    out = []
    for ln in text.split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        parts = re.split(r"(?<=[。！？；!?;])\s*|(?<=[.!?])\s+", ln)
        for p in parts:
            p = p.strip()
            if p:
                out.append(p)
    return out


def measure(sentence, lang):
    """Return (count, unit). Chinese counts characters; English counts words."""
    if lang == "zh":
        han = len(CJK.findall(sentence))
        latin = len(re.findall(r"[A-Za-z0-9]+(?:['\-][A-Za-z0-9]+)*", sentence))
        return han + latin, "字"
    return len(re.findall(r"[A-Za-z0-9]+(?:['\-][A-Za-z0-9]+)*", sentence)), "词"


def clip(s, n=70):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--mode", choices=["procedural", "descriptive", "both"], default="both")
    ap.add_argument("--lang", choices=["auto", "en", "zh"], default="auto")
    ap.add_argument("--stdout", action="store_true", help="print report instead of writing a file")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        sys.stdout.write("ERROR: no such file\n")
        return 2

    raw = read_text(args.file)
    text = clean(raw)
    lang = detect_lang(text) if args.lang == "auto" else args.lang

    # --- language-specific limits
    if args.mode == "procedural":
        hard, soft = 20, None
    elif args.mode == "descriptive":
        hard, soft = 25, None
    else:
        hard, soft = 25, 20          # >25 fails; >20 suspect (if procedural)
    default_hard, default_soft = hard, soft

    sentences = split_sentences(text, lang)

    over_hard = []
    over_soft = []
    for s in sentences:
        n, unit = measure(s, lang)
        if hard is not None and n > hard:
            over_hard.append((n, unit, clip(s)))
        elif soft is not None and n > soft:
            over_soft.append((n, unit, clip(s)))

    style_hits = []
    if lang != "zh":
        for label, rx in (("passive", PASSIVE_EN), ("perfect", PERFECT_EN), ("-ing", PROG_EN)):
            for s in sentences:
                if rx.search(s):
                    style_hits.append((label, clip(rx.search(s).group(0)), clip(s)))
    for pat, repl in EN_SWAPS.items():
        rx = re.compile(pat, re.I)
        for s in sentences:
            m = rx.search(s)
            if m:
                style_hits.append(("swap", "%s -> %s" % (m.group(0), repl), clip(s)))
    if lang != "en":
        for phrase, fix in ZH_DILUTION.items():
            for s in sentences:
                if phrase in s:
                    style_hits.append((phrase, fix, clip(s)))
        for label, rx, fix in ZH_STYLE:
            for s in sentences:
                m = rx.search(s)
                if m:
                    style_hits.append((label, "%s (%s)" % (m.group(0), fix), clip(s)))

    # --- report
    L = []
    L.append("# STE100 lint (heuristic candidates, not a verdict)")
    L.append("")
    L.append("- file: `%s`" % args.file)
    L.append("- detected language: `%s`" % lang)
    L.append("- mode: `%s` (hard limit %s%s, soft limit %s)" % (
        args.mode, hard, "", soft if soft else "-"))
    L.append("- sentences: %d" % len(sentences))
    L.append("- over hard limit: %d" % len(over_hard))
    L.append("- over soft limit: %d" % len(over_soft))
    L.append("")
    L.append("> The ASD approved-word dictionary is copyrighted and is NOT in this report.")
    L.append("> Say \"tightened per STE100 rules\", never \"STE100 compliant\".")
    L.append("")

    L.append("## %s" % ("Sentences over the hard limit" if hard else "Sentences over threshold"))
    L.append("")
    if not over_hard:
        L.append("- (none)")
    else:
        L.append("| # | len | text |")
        L.append("|---|---|---|")
        for i, (n, unit, s) in enumerate(over_hard[:60], 1):
            L.append("| %d | %d %s | %s |" % (i, n, unit, s))
    L.append("")

    if over_soft:
        L.append("## Suspect: over %s but under %s (fails only if the sentence is an instruction)"
                 % (soft, hard))
        L.append("")
        L.append("| # | len | text |")
        L.append("|---|---|---|")
        for i, (n, unit, s) in enumerate(over_soft[:60], 1):
            L.append("| %d | %d %s | %s |" % (i, n, unit, s))
        L.append("")

    L.append("## Style candidates")
    L.append("")
    if not style_hits:
        L.append("- (none)")
    else:
        L.append("| kind | found | in sentence |")
        L.append("|---|---|---|")
        for kind, found, s in style_hits[:80]:
            L.append("| %s | %s | %s |" % (kind, found, s))
    L.append("")

    report = "\n".join(L)

    # --- output (ASCII-only on the terminal)
    if args.stdout:
        try:
            sys.stdout.write(report + "\n")
        except UnicodeEncodeError:
            sys.stdout.write(report.encode("ascii", "replace").decode("ascii") + "\n")
    else:
        out = args.file + ".ste-lint.md"
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(report)
        sys.stdout.write("report written: %s\n" % out.encode("ascii", "replace").decode("ascii"))

    sys.stdout.write(
        "lang=%s sentences=%d over_hard=%d over_soft=%d style=%d\n"
        % (lang, len(sentences), len(over_hard), len(over_soft), len(style_hits))
    )
    return 1 if (over_hard or style_hits) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:               # keep the terminal message ASCII
        sys.stdout.write("ERROR: %s\n" % type(exc).__name__)
        sys.exit(3)
