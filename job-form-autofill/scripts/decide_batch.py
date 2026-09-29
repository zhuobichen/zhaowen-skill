#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把表单里的**闭合选项字段**（下拉/单选/勾选）一次性交给 Jev 判定。

为什么单独一个脚本：`decide` 的请求形状容易写错，而写错的后果是**静默的**——
少一个 `criteria` 就不是"问得含糊"，而是请求直接被拒或者答案没有依据。
这里负责三件事：校验形状、组装**一个**请求（几十个字段也是一次调用）、把答案连同概率打出来。

用法：
    # 1) 先拿骨架：它会按你给的选项列表生成待填的 criteria 模板
    python decide_batch.py --fields fields.json --scaffold > filled.json
    #    把每个选项后面的"什么时候选它"补上（这是要动脑的部分，脚本不替你想）

    # 2) 校验形状，不调模型、不出境
    python decide_batch.py --fields filled.json --dry-run

    # 3) 真调（会出境：state 与选项会发到 api.typesafe.ai）
    python decide_batch.py --fields filled.json --yes

fields.json 形状：
{
  "state": "岗位：数据分析（南宁，某环保科技）。我的资料：学历=本科，专业=环境工程，政治面貌=中共党员……",
  "fields": [
    {"key": "zzmm", "label": "政治面貌",
     "criteria": {"中共党员": "资料里写了党员", "共青团员": "资料里写了团员", "群众": "以上都不是"}}
  ]
}

**state 只放回答这些问题需要的字段**（在 profile 里挑相关的几行），不要把整份简历倒进去：
出境的数据越少越好，这是这个仓库一贯的做法。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

QUESTION_TYPES = ('choice', 'score', 'noul')   # 与 scripts/decide.py 的 QUESTION_TYPES 对齐


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def scaffold(payload):
    """按选项列表生成待填的 criteria 模板：值留空，等人补"什么时候选它"。"""
    out = {'state': payload.get('state', ''), 'fields': []}
    for f in payload.get('fields', []):
        opts = f.get('options') or list((f.get('criteria') or {}).keys())
        if not opts:
            print('!! 字段 %s 既没有 options 也没有 criteria，跳过' % f.get('key'), file=sys.stderr)
            continue
        out['fields'].append({
            'key': f['key'], 'label': f.get('label', f['key']),
            'criteria': {o: '' for o in opts},
        })
    return out


def validate(payload):
    """返回错误列表。**空列表才算过**——每一条都是实测会静默出问题的地方。"""
    errs = []
    state = payload.get('state')
    if not isinstance(state, str) or not state.strip():
        errs.append('缺少 state（字符串，且不能为空）——Jev 需要背景才能判，空 state 等于让它猜')
    fields = payload.get('fields')
    if not isinstance(fields, list) or not fields:
        errs.append('fields 必须是非空数组')
        return errs
    seen = set()
    for i, f in enumerate(fields):
        key = f.get('key')
        if not key:
            errs.append('第 %d 个字段缺少 key' % (i + 1))
            continue
        if key in seen:
            errs.append('字段 key 重复：%s（请求里 questions 是对象，重名会**悄悄少一个问题**）' % key)
        seen.add(key)
        crit = f.get('criteria')
        if not isinstance(crit, dict) or not crit:
            # 最常见的形态：传进来的是带 options 的**未填模板**。报错要说清下一步做什么，
            # 而不是说"格式不对"——那会让人去改 JSON 结构，而其实只差"补判定依据"。
            if f.get('options'):
                errs.append('%s：只有 options、还没有 criteria —— 先 `--scaffold` 生成模板，'
                            '再把每个选项后面补上"什么时候选它"' % key)
            else:
                errs.append('%s：缺少 criteria（「选项名 → 什么时候选它」的对象）' % key)
            continue
        if len(crit) < 2:
            errs.append('%s：criteria 只有一个选项 —— 不是选择题，直接填那个值就行' % key)
            continue
        empty = [o for o, when in crit.items() if not str(when or '').strip()]
        if empty:
            errs.append('%s：这些选项还没写"什么时候选它"：%s —— 留着空等于让模型自己发挥' % (key, '、'.join(empty)))
    return errs


def build_request(payload):
    questions = {}
    for f in payload['fields']:
        questions[f['key']] = {
            'type': 'choice',
            'instructions': f.get('label', f['key']),
            'criteria': f['criteria'],
        }
    return {'state': payload['state'], 'questions': questions}


def find_weflow():
    """返回 weflow-cli 的调用命令（列表）。

    顺序：`$WEFLOW_CLI` → PATH → npm 全局 shim。
    `$WEFLOW_CLI` 允许带参数（如 `npx tsx bin/weflow-cli.ts`），用 shlex 拆——同
    ai-job-command-center 里 `browser_act.py` 处理 `uvx browser-act-cli` 的做法。
    **为什么要这个覆盖**：本机实测 npm 全局装的那份是坏的（shim 在、包文件缺了，
    报 `Cannot find module .../weflow-cli/cli.cjs`），这时只能指到能跑的那一份。
    """
    import shlex

    def resolve(parts):
        """把首段解析成真实可执行路径。**Windows 上必须做**：`npx` 实际是 `npx.cmd`，
        `subprocess` 不开 shell 时按原名找不到 → `FileNotFoundError: [WinError 2]`（实测踩到）。"""
        if not parts:
            return parts
        found = shutil.which(parts[0]) or parts[0]
        return [found] + list(parts[1:])

    env = (os.environ.get('WEFLOW_CLI') or '').strip()
    if env:
        return resolve(shlex.split(env))
    p = shutil.which('weflow-cli')
    if p:
        return [p]
    for cand in (os.path.expanduser('~/AppData/Roaming/npm/weflow-cli.cmd'),
                 os.path.expanduser('~/AppData/Roaming/npm/weflow-cli')):
        if os.path.exists(cand):
            return [cand]
    return None


def print_answers(data, fields):
    """把答案按字段打印出来，**带置信度**：低置信度的要人去复核，不是照抄。

    字段名按**真实返回**写（2026-09-30 实测一次调用得到的形状，不是猜的）：
        {"answers": {"<key>": {"type":"choice", "choice":"中共党员",
                               "confidence":1.0, "probabilities":{...}}},
         "usage": {...}, "costUsd": 2.9e-05}
    一度按 `probability`/`alternatives` 取，结果什么都没打出来——猜 schema 的代价就是静默。
    """
    label = {f['key']: f.get('label', f['key']) for f in fields}
    answers = data.get('answers') if isinstance(data, dict) else None
    if not isinstance(answers, dict):
        print('（没拿到 answers，原始返回如下）')
        print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
        return
    low = []
    for key, ans in answers.items():
        name = label.get(key, key)
        if not isinstance(ans, dict):
            print('  · %s = %s' % (name, ans))
            continue
        chosen = ans.get('choice', ans.get('value', ans.get('answer')))
        conf = ans.get('confidence')
        dist = ans.get('probabilities') or {}
        line = '  · %s = %s' % (name, chosen)
        if isinstance(conf, (int, float)):
            line += '（%.2f）' % conf
        print(line)
        if isinstance(dist, dict) and dist:
            rest = sorted(((k, v) for k, v in dist.items()
                           if k != chosen and isinstance(v, (int, float)) and v > 0.01),
                          key=lambda kv: -kv[1])[:2]
            if rest:
                print('      次优：%s' % '、'.join('%s %.2f' % (k, v) for k, v in rest))
        # 阈值 0.85 是量出来的，不是拍的：实测无歧义的字段回 1.00，真正拿不准的（资料里
        # 根本没提期望薪资）回 0.70。用 0.7 当阈值时那个 0.70 **正好卡在边界上不报警**。
        if isinstance(conf, (int, float)) and conf < 0.85:
            low.append(name)
            print('      ⚠ 置信度不高，让用户复核（别默默照填）')
    if isinstance(data.get('costUsd'), (int, float)):
        model = (data.get('usage') or {}).get('model') or data.get('model') or '?'
        print('（本次判定 %s，$%.5f）' % (model, data['costUsd']))
    if low:
        print('需要复核：%s' % '、'.join(low))


def main():
    ap = argparse.ArgumentParser(description='闭合选项字段 → 一次 Jev 判定')
    ap.add_argument('--fields', required=True, help='字段 JSON 路径')
    ap.add_argument('--scaffold', action='store_true', help='只生成待填的 criteria 骨架（stdout）')
    ap.add_argument('--dry-run', action='store_true', help='只校验并回显请求形状，不调模型、不出境')
    ap.add_argument('--yes', action='store_true', help='确认把 state 与选项发到决策模型服务')
    ap.add_argument('--out', help='把请求 JSON 写到指定文件（默认临时文件）')
    args = ap.parse_args()

    payload = load(args.fields)

    if args.scaffold:
        print(json.dumps(scaffold(payload), ensure_ascii=False, indent=2))
        return 0

    errs = validate(payload)
    if errs:
        print('请求不合法，先修这些：', file=sys.stderr)
        for e in errs:
            print('  ✗ %s' % e, file=sys.stderr)
        return 2

    req = build_request(payload)
    n = len(req['questions'])
    # 出境要说清楚：这几个字段名会被发出去（值不发，选项与 state 会发）
    print('将问 Jev %d 个字段：%s' % (n, '、'.join(req['questions'].keys())))

    if args.dry_run:
        print('（dry-run，没有出境）请求形状：')
        print(json.dumps({'state_chars': len(req['state']),
                          'questions': {k: {'type': v['type'],
                                            'options': list(v['criteria'].keys())}
                                        for k, v in req['questions'].items()}},
                         ensure_ascii=False, indent=2))
        return 0

    if not args.yes:
        print('没有 --yes：不调模型。先 --dry-run 看一眼，再由用户确认。', file=sys.stderr)
        return 1

    wf = find_weflow()
    if not wf:
        print('找不到 weflow-cli —— 它必须在 PATH 上（npm 全局装的）', file=sys.stderr)
        return 1

    path = args.out or os.path.join(tempfile.gettempdir(), 'job-decide-request.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(req, f, ensure_ascii=False, indent=2)

    cmd = wf + ['decide', '--request', path, '--yes', '--json']
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)
    out = (r.stdout or '').strip()
    if r.returncode != 0:
        raw = (r.stderr or out)
        print('decide 失败（退出码 %d）：%s' % (r.returncode, raw[:400]), file=sys.stderr)
        # 本机实测过的坏法：npm 全局那份 shim 在、包文件缺了。症状是 node 的
        # "Cannot find module .../weflow-cli/cli.cjs" —— 不是 Jev 的问题，是装坏了。
        if 'Cannot find module' in raw and 'weflow-cli' in raw:
            print('  看起来是全局装的 weflow-cli 坏了（缺包文件）。两条路：'
                  '① `npm i -g weflow-cli` 重装；'
                  '② 用 WEFLOW_CLI 指到能跑的那份，例如在仓库里：'
                  'WEFLOW_CLI="npx tsx bin/weflow-cli.ts"', file=sys.stderr)
        return 1
    start = out.find('{')
    try:
        data = json.loads(out[start:]) if start >= 0 else {}
    except Exception as e:
        print('返回不是 JSON（%s）：%s' % (e, out[:300]), file=sys.stderr)
        return 1
    print_answers(data, payload['fields'])
    # 数据最小化：临时请求文件里装着 state（你的资料），用完就删。
    # 只有显式 --out 指定路径时才留着（那是你要的）。
    if not args.out:
        try:
            os.remove(path)
        except OSError:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
