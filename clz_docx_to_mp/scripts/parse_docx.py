# -*- coding: utf-8 -*-
"""
docx → 结构化 JSON（公众号排版流水线的第一步）

职责：只做「忠实还原」，不做任何排版决策。
按文档原始顺序输出 blocks，图片抽到独立目录，题注按原样归属。

用法：
    python parse_docx.py <input.docx> <output_dir>

产出：
    <output_dir>/content.json     结构化内容
    <output_dir>/images/          抽出的图片（按文档出现顺序重命名）

设计原则（用户要求「内容不变」）：
    - 段落数与顺序与原文严格一致，不合并、不重排、不删改
    - 题注归属：题注段落紧跟在图片段落后 → 归于该图；图片段落内自带题注 → 用自带的
    - 两张图共用一条题注时，题注归最后一张（渲染出来与 docx 观感一致），前面的图无题注
"""
import sys
import os
import io
import json
import zipfile
import re
import shutil

# Windows 控制台中文输出（仅直接运行时包装；被 import 时不碰）
if sys.platform == 'win32' and __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from docx import Document  # noqa: E402

# 见过的样式名（不写死，仅作默认值；可用 --map 覆盖）
DEFAULT_STYLES = {
    'title': ['title'],
    'heading': ['heading 1', 'heading 2', 'heading 3'],
    'caption': ['我的题注', 'caption', '题注'],
    'image': ['我的图片'],
}

PLACEHOLDER_IMG = 'w:drawing'  # 图片在段落 XML 里的标志


def _style_kind(style_name, style_map):
    """样式名 → 语义类型"""
    s = (style_name or '').strip().lower()
    for kind, names in style_map.items():
        for n in names:
            if n.lower() == s:
                return kind
    return 'body'


def _paragraph_images(para, doc_part):
    """返回该段落里的图片关系 id 列表（保持出现顺序）"""
    xml = para._p.xml
    return re.findall(r'r:embed="(rId\d+)"', xml)


def _is_placeholder_only(text):
    """仅由【】包起来的题注"""
    t = text.strip()
    return bool(t) and t.startswith('【') and t.endswith('】')


def parse(docx_path, out_dir, style_map=None):
    style_map = style_map or DEFAULT_STYLES
    os.makedirs(out_dir, exist_ok=True)
    img_dir = os.path.join(out_dir, 'images')
    os.makedirs(img_dir, exist_ok=True)

    doc = Document(docx_path)
    rels = doc.part.rels

    zf = zipfile.ZipFile(docx_path)
    media_names = [n for n in zf.namelist() if n.startswith('word/media/')]

    # ---- 预扫描：按文档顺序建立「关系id → 媒体文件」映射，并把图片抽到 images/ ----
    ordered = []          # [(rId, media_name)]
    for para in doc.paragraphs:
        for rid in _paragraph_images(para, doc.part):
            try:
                target = rels[rid].target_ref          # 形如 media/image1.jpeg
            except KeyError:
                continue
            ordered.append((rid, target))

    rid_to_extracted = {}
    used_names = set()
    for idx, (rid, target) in enumerate(ordered, 1):
        zip_path = 'word/' + target if not target.startswith('word/') else target
        if zip_path not in media_names:
            continue
        ext = os.path.splitext(target)[1] or '.png'
        # 抽出的文件名按出现顺序，保留 docx 内原名便于溯源
        base = os.path.basename(target)
        out_name = '%03d_%s' % (idx, base)
        while out_name in used_names:
            out_name = '%03d_b_%s' % (idx, base)
        used_names.add(out_name)
        with open(os.path.join(img_dir, out_name), 'wb') as f:
            f.write(zf.read(zip_path))
        rid_to_extracted[rid] = out_name

    # ---- 主扫描：按顺序产 blocks ----
    blocks = []
    pending_images = []   # 已产出、尚未配到题注的 image block
    title = None

    for para in doc.paragraphs:
        text = para.text.strip()
        rid_list = _paragraph_images(para, doc.part)
        kind = _style_kind(para.style.name if para.style else '', style_map)

        # 图片段落
        if rid_list:
            for rid in rid_list:
                if rid not in rid_to_extracted:
                    continue
                blk = {
                    'type': 'image',
                    'file': rid_to_extracted[rid],
                    'caption': None,
                    'style': para.style.name if para.style else '',
                }
                blocks.append(blk)
                pending_images.append(blk)
            # 图片段落里自带文字 → 当作该图的题注（如 [我的题注][IMG]【xx致辞】）
            if text:
                if kind == 'title' and title is None:
                    title = text
                else:
                    pending_images[-1]['caption'] = text
                    pending_images = []
            continue

        if not text:
            continue  # 空段落跳过

        # 题注段落：配给紧邻的前一张图
        if kind == 'caption' and pending_images:
            pending_images[-1]['caption'] = text
            pending_images = []
            continue

        # 标题
        if kind == 'title':
            if title is None:
                title = text
            blocks.append({'type': 'title', 'text': text})
            pending_images = []
            continue

        if kind == 'heading':
            lvl = 1
            m = re.search(r'(\d+)', (para.style.name or ''))
            if m:
                lvl = int(m.group(1))
            blocks.append({'type': 'heading', 'text': text, 'level': lvl})
            pending_images = []
            continue

        # 普通正文
        blocks.append({'type': 'para', 'text': text})
        pending_images = []

    result = {
        'source': os.path.abspath(docx_path),
        'title': title,
        'blocks': blocks,
        'images_dir': 'images',
        'stats': {
            'blocks': len(blocks),
            'images': sum(1 for b in blocks if b['type'] == 'image'),
            'paras': sum(1 for b in blocks if b['type'] == 'para'),
            'headings': sum(1 for b in blocks if b['type'] == 'heading'),
            'captioned': sum(1 for b in blocks if b['type'] == 'image' and b.get('caption')),
        },
    }

    with open(os.path.join(out_dir, 'content.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    docx_path = sys.argv[1]
    out_dir = sys.argv[2]
    r = parse(docx_path, out_dir)
    print('✅ 解析完成')
    print('   标题:', r['title'])
    print('   统计:', json.dumps(r['stats'], ensure_ascii=False))
    print('   输出:', os.path.join(out_dir, 'content.json'))
    # 无题注的图片列出来供人工确认（不臆造题注）
    missing = [b['file'] for b in r['blocks'] if b['type'] == 'image' and not b.get('caption')]
    if missing:
        print('   ⚠️ %d 张图无题注（原样保留，不补）:' % len(missing))
        for m in missing:
            print('      ', m)
    return 0


if __name__ == '__main__':
    sys.exit(main())
