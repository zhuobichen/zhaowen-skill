"""生成 file-list JSON（结果文件列表，格式对齐平台）

用法:
  python gen_filelist.py <结果目录> <task_id> [输出路径]
  默认输出: <结果目录>/China_file-list-<task_id>.json
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import re

# 排除自身和配置文件（JobProfile_*_config.json 通用匹配，不限 ID）
SKIP_PREFIX = ('China_file-list-',)
CONFIG_RE = re.compile(r'^JobProfile_.*_config\.json$')


def main():
    p = argparse.ArgumentParser(description='生成 file-list JSON')
    p.add_argument('dir', help='结果文件目录')
    p.add_argument('task_id', type=int, help='taskId')
    p.add_argument('out', nargs='?', help='输出路径（位置参数，默认 China_file-list-<id>.json）')
    p.add_argument('--out', dest='out_opt', help='输出路径（与位置参数等价，二选一）')
    args = p.parse_args()
    args.out = args.out_opt or args.out

    if not os.path.isdir(args.dir):
        sys.exit(f'错误: 目录不存在 {args.dir}')

    result_files = sorted(
        f for f in os.listdir(args.dir)
        if os.path.isfile(os.path.join(args.dir, f))
        and not f.startswith(SKIP_PREFIX)
        and not CONFIG_RE.match(f)
    )

    fl = {
        'taskId': args.task_id,
        'apiEndpoint': f'/workflow-gateway/api/JobRun/{args.task_id}/Files',
        'retrievedAt': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'),
        'totalFiles': len(result_files),
        'files': result_files,
    }

    out = args.out or os.path.join(args.dir, f'China_file-list-{args.task_id}.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(fl, f, ensure_ascii=False, indent=2)
    print(f'✅ 已生成: {out}（totalFiles={len(result_files)}）')


if __name__ == '__main__':
    main()
