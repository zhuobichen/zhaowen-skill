"""重命名结果文件的情景名（保留 UTF-8 BOM），支持目录或 zip 输入

用法:
  python rename_scenarios.py <src目录|src.zip> <输出目录> [--s1 强化治理情景] [--s2 常规情景]
"""
import argparse
import os
import shutil
import sys
import zipfile


def process_text(content: bytes, s1: str, s2: str) -> bytes:
    """替换文本内容（utf-8-sig 解码去 BOM，替换后 utf-8-sig 编码保留 BOM）"""
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        return content  # 二进制保留
    text = text.replace('情景1', s1).replace('情景2', s2)
    return text.encode('utf-8-sig')


def rename_file(fname: str, s1: str, s2: str) -> str:
    return fname.replace('情景1', s1).replace('情景2', s2)


def main():
    p = argparse.ArgumentParser(description='重命名结果文件情景名')
    p.add_argument('src', help='源目录或 zip 文件')
    p.add_argument('out', help='输出目录')
    p.add_argument('--s1', default='强化治理情景', help='情景1 新名')
    p.add_argument('--s2', default='常规情景', help='情景2 新名')
    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)
    count = 0

    if not (zipfile.is_zipfile(args.src) or os.path.isdir(args.src)):
        sys.exit(f'错误: 源 {args.src} 不是 zip 也不是存在的目录')

    if zipfile.is_zipfile(args.src):
        with zipfile.ZipFile(args.src) as zf:
            for name in zf.namelist():
                data = zf.read(name)
                new_name = rename_file(os.path.basename(name), args.s1, args.s2)
                data = process_text(data, args.s1, args.s2)
                with open(os.path.join(args.out, new_name), 'wb') as f:
                    f.write(data)
                count += 1
    else:
        for f in os.listdir(args.src):
            pth = os.path.join(args.src, f)
            if os.path.isfile(pth):
                with open(pth, 'rb') as fh:
                    data = process_text(fh.read(), args.s1, args.s2)
                new_name = rename_file(f, args.s1, args.s2)
                with open(os.path.join(args.out, new_name), 'wb') as fh:
                    fh.write(data)
                count += 1

    print(f'✅ 处理 {count} 个文件 -> {args.out}/（{args.s1} / {args.s2}）')


if __name__ == '__main__':
    main()
