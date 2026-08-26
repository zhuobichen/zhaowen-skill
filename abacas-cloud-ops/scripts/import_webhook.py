"""通过 webhook 导入结果文件到任务（不重跑工作流，让平台展示）

用法:
  python import_webhook.py <job_id> <callback_token> <结果zip>
  可选: --workflow-key cost-effectiveness-integrated-evaluation
        --internal  用内网地址
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, BASE_INTERNAL
import requests


def main():
    p = argparse.ArgumentParser(description='webhook 导入结果')
    p.add_argument('job_id', type=int)
    p.add_argument('callback_token', help='任务专属 token（从 n8n 获取，见 SKILL §6）')
    p.add_argument('result_zip', help='结果文件 zip（含重命名后文件）')
    p.add_argument('--workflow-key', default='cost-effectiveness-integrated-evaluation')
    p.add_argument('--internal', action='store_true', help='用内网地址')
    args = p.parse_args()

    base = BASE_INTERNAL if args.internal else BASE
    url = (f'{base}/webhook/{args.workflow_key}'
           f'?job_run_id={args.job_id}&callback_token={args.callback_token}')
    print('webhook URL:', url)

    if not os.path.exists(args.result_zip):
        sys.exit(f'错误: zip 不存在 {args.result_zip}')

    # 必须用 files 参数生成 multipart（手动 Content-Type 会报 415/boundary 错）
    with open(args.result_zip, 'rb') as fh:
        r = requests.post(url, files={
            'job_status': (None, 'completed'),
            'result_data': ('results.zip', fh, 'application/zip'),
        }, timeout=120)

    print(f'HTTP {r.status_code}: {r.text[:200]}')
    # 204/200 成功；401 缺 token；404 任务不存在
    sys.exit(0 if r.status_code in (200, 201, 202, 204) else 1)


if __name__ == '__main__':
    main()
