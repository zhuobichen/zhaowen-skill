"""上传文件到 ABaCAS UserUpload（中文文件名必须用 requests，curl 会乱码）

用法:
  python upload_file.py <本地文件路径> [--token BEARER]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, get_token
import requests


def main():
    p = argparse.ArgumentParser(description='上传文件到 ABaCAS UserUpload')
    p.add_argument('file', help='本地文件路径')
    p.add_argument('--token', help='Bearer Token（可选，见 common.get_token）')
    args = p.parse_args()

    token = get_token(args.token)
    fname = os.path.basename(args.file)
    # 按扩展名推断 MIME（中文文件名用 requests 的 UTF-8 编码，curl 会乱码）
    MIME = {
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'csv': 'text/csv',
        'json': 'application/json',
    }
    ext = os.path.splitext(fname)[1].lstrip('.').lower()
    mime = MIME.get(ext, 'application/octet-stream')
    with open(args.file, 'rb') as fh:
        files = {'file': (fname, fh, mime)}
        r = requests.post(f'{BASE}/AppFile/UserUpload',
                          headers={'Authorization': 'Bearer ' + token},
                          files=files, timeout=120)
    print(f'HTTP {r.status_code}: {r.text[:200]}')
    sys.exit(0 if r.status_code in (200, 201) else 1)


if __name__ == '__main__':
    main()
