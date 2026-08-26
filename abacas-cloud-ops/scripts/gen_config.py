"""从平台 JobProfile 生成交付用配置文件（可改 id/任务名/情景列/时间，并精简 erq 只留 presetFileName）

用法:
  python gen_config.py <profile_id> [--token BEARER] [--new-id 255] [--name 新任务名]
                       [--s1 强化治理情景] [--s2 常规情景] [--time 2026-08-12T01:00:00.000Z]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, get_token, headers
import requests


def main():
    p = argparse.ArgumentParser(description='生成精简配置文件')
    p.add_argument('profile_id', type=int, help='源 JobProfile ID')
    p.add_argument('--token', help='Bearer Token')
    p.add_argument('--new-id', type=int, help='新的 id（如 255）')
    p.add_argument('--name', help='新任务名')
    p.add_argument('--s1', default='强化治理情景', help='情景1 新名')
    p.add_argument('--s2', default='常规情景', help='情景2 新名')
    p.add_argument('--time', help='createdAt/updatedAt（如 2026-08-12T01:00:00.000Z）')
    p.add_argument('--out', help='输出路径（默认 JobProfile_<new_id>_config.json）')
    args = p.parse_args()

    token = get_token(args.token)
    resp = requests.get(f'{BASE}/JobProfile/{args.profile_id}', headers=headers(token), timeout=60)
    if resp.status_code != 200:
        sys.exit(f'错误: 获取 JobProfile/{args.profile_id} 失败 HTTP {resp.status_code}'
                 f'（401=Token过期；404=ID不存在）')
    try:
        d = resp.json()
    except ValueError:
        sys.exit(f'错误: JobProfile/{args.profile_id} 响应非 JSON（HTTP {resp.status_code}），可能是网关错误。')
    if 'config' not in d or not isinstance(d.get('config'), dict):
        sys.exit(f'错误: JobProfile {args.profile_id} 响应无 config 字段，无法生成配置文件。')

    new_id = args.new_id if args.new_id is not None else d.get('id')
    if args.new_id is not None:
        d['id'] = args.new_id
    if args.name:
        d['name'] = args.name
        for loc in ('config_json', 'project_json'):
            if 'projectTaskName' in d.get('config', {}).get(loc, {}):
                d['config'][loc]['projectTaskName'] = args.name
    # 情景列（config_json + project_json 两处；少于 2 情景则跳过，避免 IndexError）
    for loc in ('config_json', 'project_json'):
        erq = d.get('config', {}).get(loc, {}).get('emissionReductionQuantOptions')
        sc = erq.get('scenarioColumns') if erq else None
        if isinstance(sc, list) and len(sc) >= 2:
            sc[0]['label'] = args.s1
            sc[1]['label'] = args.s2
    # 精简 erq：只留 presetFileName
    for loc in ('config_json', 'project_json'):
        erq = d.get('config', {}).get(loc, {}).get('emissionReductionQuantOptions')
        if erq:
            preset = erq.get('presetFileName')
            d['config'][loc]['emissionReductionQuantOptions'] = {'presetFileName': preset}
    if args.time:
        d['createdAt'] = args.time
        d['updatedAt'] = args.time

    out = args.out or f'JobProfile_{new_id}_config.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print(f'✅ 已生成: {out}（id={new_id}, name={d.get("name")}, '
          f'erq 精简为 presetFileName）')


if __name__ == '__main__':
    main()
