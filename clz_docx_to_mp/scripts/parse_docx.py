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
from PIL import Image  # noqa: E402

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
    """返回该段落里的图片信息（保持出现顺序）

    每项：{'rid': rId, 'rot': 度, 'src': srcRect 属性字典}

    ⚠️ 必须连 rot / srcRect 一起取。docx 允许图片带旋转与裁剪：
    Word 里「转正过的竖图」在文件里存的是**躺倒的横图** + 一个 rot 属性，
    只取 r:embed 会把这类图原样导成横躺的，看起来就是「竖图变横图」。
    """
    xml = para._p.xml
    out = []
    for dr in re.findall(r'<w:drawing>.*?</w:drawing>', xml, re.S):
        m = re.search(r'r:embed="(rId\d+)"', dr)
        if not m:
            continue
        rot_m = re.search(r'<a:xfrm[^>]*\brot="(-?\d+)"', dr)
        sr_m = re.search(r'<a:srcRect([^/>]*)/?>', dr)
        src = {}
        if sr_m:
            for k, v in re.findall(r'(\w+)="(-?\d+)"', sr_m.group(1)):
                src[k] = int(v)
        out.append({
            'rid': m.group(1),
            # OOXML 角度单位 1/60000 度，顺时针为正
            'rot': int(rot_m.group(1)) / 60000.0 if rot_m else 0.0,
            'src': src,
        })
    return out


def _apply_transform(im, rot_deg, src):
    """按 docx 的 rot / srcRect 把图片还原成 Word 里看到的样子

    顺序：先按 srcRect 裁剪源图，再旋转（与 OOXML 的语义一致）。
    """
    if src:
        l = src.get('l', 0) / 100000.0     # srcRect 单位是 1/1000 百分号
        r = src.get('r', 0) / 100000.0
        t = src.get('t', 0) / 100000.0
        b = src.get('b', 0) / 100000.0
        w, h = im.size
        box = (int(w * l), int(h * t), int(w * (1 - r)), int(h * (1 - b)))
        if box[2] - box[0] > 1 and box[3] - box[1] > 1:
            im = im.crop(box)
    if rot_deg:
        # OOXML rot 顺时针为正，PIL rotate 逆时针为正 → 取负
        im = im.rotate(-rot_deg, expand=True)
    return im


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

    # ---- 预扫描：按文档顺序抽图片到 images/，并应用 rot / srcRect ----
    ordered = []          # [(rId, media_name, rot, src)]
    for para in doc.paragraphs:
        for info in _paragraph_images(para, doc.part):
            try:
                target = rels[info['rid']].target_ref   # 形如 media/image1.jpeg
            except KeyError:
                continue
            ordered.append((info['rid'], target, info['rot'], info['src']))

    rid_to_extracted = {}
    used_names = set()
    n_transformed = 0
    for idx, (rid, target, rot, src) in enumerate(ordered, 1):
        zip_path = 'word/' + target if not target.startswith('word/') else target
        if zip_path not in media_names:
            continue
        # 抽出的文件名按出现顺序，保留 docx 内原名便于溯源
        base = os.path.basename(target)
        out_name = '%03d_%s' % (idx, base)
        while out_name in used_names:
            out_name = '%03d_b_%s' % (idx, base)
        used_names.add(out_name)
        raw = zf.read(zip_path)
        dest = os.path.join(img_dir, out_name)
        if rot or src:
            # 有旋转/裁剪：解出来处理后另存（保持原扩展名）
            try:
                im = Image.open(io.BytesIO(raw))
                im = _apply_transform(im, rot, src)
                fmt = 'PNG' if out_name.lower().endswith('.png') else 'JPEG'
                im.save(dest, fmt)
                n_transformed += 1
            except Exception as e:
                print('  ⚠️ 变换失败 %s（按原图输出）: %s' % (out_name, e))
                with open(dest, 'wb') as f:
                    f.write(raw)
        else:
            with open(dest, 'wb') as f:
                f.write(raw)
        rid_to_extracted[rid] = out_name

    if n_transformed:
        print('   已按 docx 的旋转/裁剪还原 %d 张图' % n_transformed)

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
            for _info in rid_list:
                rid = _info['rid']
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
