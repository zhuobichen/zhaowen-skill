"""计算费效比 B/C = PM25_BenMAP PointEstimate 汇总 / Control Case_Reduction_Cost 的 Control_Cost 汇总

支持两种输入：
  1. 本地目录：python calc_bc.py --dir <结果目录>
  2. 平台任务：python calc_bc.py <job_id> [--token]
"""
import argparse
import csv
import io
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, get_token, headers
import requests


def readcsv(text):
    return list(csv.DictReader(io.StringIO(text.lstrip('﻿'))))


def calc_from_dir(d):
    if not os.path.isdir(d):
        sys.exit(f'错误: 目录不存在 {d}')
    required = ['PM25_BenMAP_apvrx.csv']
    miss = [f for f in required if not os.path.exists(os.path.join(d, f))]
    if miss:
        sys.exit(f'错误: 目录 {d} 缺少 {miss}')
    def ben():
        agg = {}
        for r in readcsv(open(os.path.join(d, 'PM25_BenMAP_apvrx.csv'), encoding='utf-8-sig').read()):
            c = r.get('Case_Name', '').strip()
            try:
                v = float(r.get('PointEstimate', 0) or 0)
            except (ValueError, TypeError):
                continue
            agg[c] = agg.get(c, 0) + v
        return agg

    def cost(fname):
        return sum(float(r.get('Control_Cost(RMB)', 0) or 0)
                   for r in readcsv(open(os.path.join(d, fname), encoding='utf-8-sig').read()))

    b = ben()
    result = {}
    for case in sorted(b):
        # 情景文件命名：Case #<情景名> Control Case_Reduction_Cost.csv
        cf = f'Case #{case} Control Case_Reduction_Cost.csv'
        if os.path.exists(os.path.join(d, cf)):
            c = cost(cf)
            result[case] = b[case] / c
    return result


def calc_from_remote(job_id, token):
    base = BASE
    h = headers(token)

    def dl(fname):
        return requests.get(f'{base}/JobRun/{job_id}/Files/{urllib.parse.quote(fname)}',
                            headers=h, timeout=120).content.decode('utf-8')

    b = {}
    for r in readcsv(dl('PM25_BenMAP_apvrx.csv')):
        c = r.get('Case_Name', '').strip()
        try:
            v = float(r.get('PointEstimate', 0) or 0)
        except (ValueError, TypeError):
            continue
        b[c] = b.get(c, 0) + v

    result = {}
    for case in sorted(b):
        cf = f'Case #{case} Control Case_Reduction_Cost.csv'
        try:
            c = sum(float(x.get('Control_Cost(RMB)', 0) or 0) for x in readcsv(dl(cf)))
            result[case] = b[case] / c
        except Exception as e:
            print(f'  ⚠ 跳过 {case}: 成本文件缺失或解析失败 ({e})')
    return result


def main():
    p = argparse.ArgumentParser(description='计算费效比 B/C')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--dir', help='本地结果目录')
    g.add_argument('job_id', nargs='?', type=int, help='平台 JobRun ID')
    p.add_argument('--token', help='Bearer Token（远程模式）')
    args = p.parse_args()

    if args.dir:
        result = calc_from_dir(args.dir)
    else:
        result = calc_from_remote(args.job_id, get_token(args.token))

    print('=== 费效比 B/C ===')
    for case, bc in result.items():
        print(f'  [{case}] B/C={bc:.4f}')
    if not result:
        sys.exit('未找到可计算的费效比数据')


if __name__ == '__main__':
    main()
