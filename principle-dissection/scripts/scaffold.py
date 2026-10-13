#!/usr/bin/env python3
"""Scaffold a fixed-structure dissection note (<<principle-dissection>> skill).

Usage:
    python scaffold.py <output.md> [--force]

Writes a UTF-8 Markdown skeleton with the fixed sections.
Body is the BASICS (each fundamental explained from zero); verification is optional.
Refuses to overwrite an existing file unless --force is given.

Notes for this machine:
  * File is written UTF-8 explicitly (Windows default would be GBK).
  * stdout is ASCII only, so it is safe on a GBK console.
  * Text mode (not binary) so a failed write cannot truncate an existing file.
"""
import argparse
import os
import sys
from datetime import date

TEMPLATE = """# 原理拆解:{name}

> 拆解日期:{today}　|　产物位置:{where}　|　一句话是什么:
> 主体是**知识**(它用到的每一门基本功,从零讲),不是"怎么验证"。
> 标注约定:每行注明来源 —— [实测] / [我推的] / [黑箱]。

## 0. 产物与它的「声称」
- 它是什么(不含形容词):
- 它声称能做什么(坐标系):
- 谁做的(自己 / AI / 混合):
- 我实际读懂了多少(%):
- 只拆承重的 20%:这次锁哪一块?

## 1. 它用到的每一门基本功(清单,按承重排)
| 基本功 | 出现在项目的哪一块 | 承重吗 | 我现在懂多少 |
|---|---|---|---|
|  |  |  |  |

## 2. 每门从零讲(主体,占全篇一半以上)

### 2.1 <基本功 A>
- **是什么**(一句话,不假设认识任何术语):
- **标准手段有哪些**(2–4 种,各自适用什么):
- **我这项目用的是哪一种**(落到哪块):
- **最小例子**(一条命令 / 一段最小代码 / 一张手画关系):

### 2.2 <基本功 B>
- **是什么**:
- **标准手段有哪些**:
- **我这项目用的是哪一种**:
- **最小例子**:

## 3. 可靠边界(可选:想判它"靠不靠得住"时再做)
（信号地图 / 失效模式 / oracle 实测 / 黑箱层。不做也行。）

## 4. 复述与缺口
- 我能讲清的:
- 我讲不清的(=真没懂的):
- 考官问到我答错的:
"""


def main():
    ap = argparse.ArgumentParser(description="Scaffold a principle-dissection note.")
    ap.add_argument("output", help="path to the .md to create")
    ap.add_argument("--name", default="<产物名>", help="artifact name for the title")
    ap.add_argument("--where", default="<path>", help="artifact location")
    ap.add_argument("--force", action="store_true", help="overwrite if exists")
    args = ap.parse_args()

    path = os.path.abspath(args.output)
    if os.path.exists(path) and not args.force:
        print("REFUSE: exists, use --force to overwrite: " + path)
        return 2

    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)

    body = TEMPLATE.format(name=args.name, today=date.today().isoformat(), where=args.where)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)

    print("OK: wrote %s (%d chars, utf-8)" % (path, len(body)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
