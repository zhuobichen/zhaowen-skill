#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""填表前的预检：三样东西在不在——browser-act、weflow-cli（Jev）、profile。

只读，不改任何东西。三样都齐了才动手填表，缺哪样就说清怎么补。
退出码：0 = 都齐；1 = 有缺项（browser-act 缺了就没法填，其余缺了可以降级）。
"""
import os
import shutil
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# browser-act 本机是 uv tool 装的：可执行文件名与包名不同，`uvx browser-act-cli` 会失败，
# 必须 `uvx --from browser-act-cli browser-act`（这个坑实测过，写死在这里省得再踩）
UVX_FORM = ['uvx', '--from', 'browser-act-cli', 'browser-act']


def resolve_browser_act():
    """返回 (调用方式, 说明)。调用方式是列表，交给 subprocess 用 shell=False 执行。"""
    p = shutil.which('browser-act')
    if p:
        return [p], 'PATH 上的 browser-act'
    for cand in (os.path.expanduser('~/.local/bin/browser-act.exe'),
                 os.path.expanduser('~/.local/bin/browser-act')):
        if os.path.exists(cand):
            return [cand], 'uv tool 的 shim（不在 PATH，用绝对路径）'
    if shutil.which('uvx'):
        try:
            r = subprocess.run(UVX_FORM + ['--version'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
            if r.returncode == 0:
                return UVX_FORM, 'uvx --from browser-act-cli（每次都走 uv 解析，慢一点但可用）'
        except Exception:
            pass
    return None, '三种方式都没找到'


def main():
    ok = True
    print('== browser-act ==')
    exe, how = resolve_browser_act()
    if exe:
        print('  ✓ %s' % how)
        r = subprocess.run(exe + ['--version'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
        print('    版本: %s' % (r.stdout or r.stderr).strip()[:60])
        # 浏览器实例：**不要只认 `chrome-direct` 这个字面量**。实测本机连着的是
        # `chrome_local_...`（type=chrome），只找 "chrome-direct" 会误报"没有浏览器"——
        # 那就成了一条看着像结论的假阴性（第一次跑就是这么误报的）。
        r2 = subprocess.run(exe + ['browser', 'list'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
        text = (r2.stdout or '') + (r2.stderr or '')
        instances = [ln.strip() for ln in text.splitlines() if 'id=' in ln]
        if not instances:
            print('    浏览器实例: **一个都没有** —— 先把 browser-act 扩展连上（它自己会显示连接状态）')
        else:
            print('    浏览器实例 %d 个（拿 id= 后面那串去 `browser open`）：' % len(instances))
            for ln in instances[:5]:
                print('      %s' % ln[:120])
    else:
        print('  ✗ 找不到 browser-act（%s）' % how)
        print('    装法：uv tool install browser-act-cli   或者让它进 PATH')
        ok = False

    print('== weflow-cli（Jev 决策模型）==')
    wf = shutil.which('weflow-cli')
    if wf:
        print('  ✓ %s' % wf)
        print('    调 Jev：weflow-cli decide --request <file> --dry-run 先看形状，再 --yes 真调')
    else:
        print('  ✗ PATH 上没有 weflow-cli —— 闭合选项就没法交给 Jev，只能助手自己判（准确率会低一些）')

    print('== profile（简历的结构化事实）==')
    p = os.environ.get('JOB_PROFILE') or os.path.expanduser('~/.job-apply/profile.md')
    if os.path.exists(p):
        size = os.path.getsize(p)
        print('  ✓ %s（%d 字节）' % (p, size))
        print('    提醒：这里是个人数据，**不要**拷进技能包目录（那是个公开仓库）')
    else:
        # profile 缺失**不**让预检失败：它只影响"能自动抄的字段有多少"，不影响能不能填
        print('  ✗ 还没有：%s' % p)
        print('    先建一份：把简历里能直接抄的事实抄成 `key: value` 行，成段的（自我介绍/项目描述）放"自由文本片段"')

    print()
    print('结论：%s' % ('可以开始' if ok else '先补齐上面 ✗ 的项'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
