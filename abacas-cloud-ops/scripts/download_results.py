"""下载 ABaCAS 任务结果文件到本地目录（保留原始字节/BOM）

用法:
  python download_results.py <job_id> <输出目录> [--token BEARER] [--internal]
"""
import argparse
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, BASE_INTERNAL, get_token, headers
import requests


def main():
    p = argparse.ArgumentParser(description='下载任务结果文件')
    p.add_argument('job_id', type=int, help='JobRun ID')
    p.add_argument('out_dir', help='输出目录')
    p.add_argument('--token', help='Bearer Token')
    p.add_argument('--internal', action='store_true', help='用内网地址 <内网IP>')
    args = p.parse_args()

    base = BASE_INTERNAL if args.internal else BASE
    token = get_token(args.token)
    h = headers(token)
    os.makedirs(args.out_dir, exist_ok=True)

    r = requests.get(f'{base}/JobRun/{args.job_id}/Files', headers=h, timeout=30)
    if r.status_code == 401:
        sys.exit('错误: Token 过期(401)，请重新获取 Token')
    if r.status_code != 200:
        sys.exit(f'错误: 获取文件列表失败 HTTP {r.status_code}: {r.text[:200]}')
    files = r.json()
    if not isinstance(files, list):
        sys.exit(f'错误: 文件列表接口返回非列表结构: {type(files).__name__}')
    print(f'共 {len(files)} 个文件，下载到 {args.out_dir}/')
    for f in files:
        url = f'{base}/JobRun/{args.job_id}/Files/{urllib.parse.quote(f)}'
        r = requests.get(url, headers=h, timeout=120)
        if r.status_code != 200:
            print(f'  FAIL {f}: HTTP {r.status_code}')
            continue
        with open(os.path.join(args.out_dir, f), 'wb') as fh:
            fh.write(r.content)
        print(f'  ✓ {f} ({len(r.content)}字节)')


if __name__ == '__main__':
    main()
