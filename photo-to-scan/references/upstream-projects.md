# 上游方案调研（拍照 → 扫描件）

这份笔记记录「手机拍纸 → 扫描件」这件事上现成的开源方案，以及本脚本为什么
只借算法、不直接套用它们。结论先给：

- **手机扫描 App（扫描全能王 / CamScanner）的本质**是四个经典步骤拼起来的：
  找纸角 → 透视校正 → 去光照/去阴影 → 二值化或"彩色增强"，只有**弯曲纸面矫正**
  这一步需要训练模型。前四步用经典算法就能做到接近的效果。
- 所以本技能 = OpenCV 透视 + 投影轮廓纠偏 + 平场去光照 + **Sauvola 二值化**
  与彩色层合成；不引入任何模型权重，纯离线、pip 装完就能跑。

## 1. 端到端 / 整页工具（想直接抄现成的就看这些）

| 项目 | 做什么 | 取舍 |
| --- | --- | --- |
| [ocrmypdf/OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) | 给扫描 PDF 加文字层，自带 `--deskew` `--rotate-pages` `--clean` `--remove-background` | 最权威的"扫描件后处理"流水线，但依赖 Tesseract/unpaper 等外部二进制；Windows 上装一轮不轻，且它是 PDF 进 PDF 出 |
| [unpaper/unpaper](https://github.com/unpaper/unpaper) | 扫描件后处理：去黑边、去噪、纠偏、去装订阴影 | C 程序，参数多；作为独立步骤很棒，但没法在 Python 里细调 |
| [4lex4/scantailor-advanced](https://github.com/4lex4/scantailor-advanced) | 桌面级"扫描件排版"：切页、纠偏、去弯、加边 | GUI 为主，适合人工精修，不适合嵌进 agent 流程 |
| [ColonelParrot/jscanify](https://github.com/ColonelParrot/jscanify) | 浏览器/Node 的"手机扫描"：找纸角 + 透视 + scan 滤镜 | 效果思路和本技能一致（OpenCV.js）；跑在 JS 侧，需要 Node 环境 |
| [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | PP-Structure 的 `doc_preprocessor`：文档方向分类 + UVDoc 弯曲矫正 | 方向分类/去弯最省心的"官方实现"，但要装 paddle 全家桶 + 下模型 |
| [sbrunner/deskew](https://github.com/sbrunner/deskew) | 经典 Hough 纠偏库（`determine_skew`） | 只做纠偏；本技能用等价的自写投影轮廓法，省一个依赖 |

## 2. 弯曲纸面矫正（拍书、皱纸才需要）

| 项目 | 说明 |
| --- | --- |
| [mzucker/page-dewarp](https://github.com/mzucker/page-dewarp) | 老牌 Python/C++ 方案，用柱面模型 + 网格优化把书页摊平；参数需要按图调 |
| [tanguyphilip/UVdoc](https://github.com/tanguyphilip/UVdoc) | UVDoc（CVPR 2023），无监督 3D 网格回归做文档展平，目前这一类里效果最好的之一 |
| [cvlab-stonybrook/DocScanner](https://github.com/cvlab-stonybrook/DocScanner) | 渐进式文档矫正（CVPR 2023），对褶皱/折痕更稳 |
| [ZZZHANG-jx/DocTrPlusPlus](https://github.com/ZZZHANG-jx/DocTrPlusPlus) | DocTr++（TPAMI 2024），配对的"拍照—展平"数据 + 强基线 |
| [DocsaidLab/DocAligner](https://github.com/DocsaidLab/DocAligner) | 只做"文档四角 + 归一化"的回归模型，相机端体验最接近扫描 App 的第一步 |

这些都需要 PyTorch/ONNX 权重（几十到几百 MB），装进通用技能里性价比不高；
需要时按 `SKILL.md` 的「Limits」一节单独接。

## 3. 本脚本实际采用的算法与出处

| 步骤 | 算法 | 出处 |
| --- | --- | --- |
| 透视校正 | 四点透视变换 `getPerspectiveTransform` + `warpPerspective` | OpenCV 标准做法（仅在四角都在画面内时启用，否则宁可不猜） |
| 方向判定（90/270） | OCR 检测框长宽比：横向正文的框宽高比 ≈5，躺着时 ≈0.2 | 本技能实测结论（OCR 会先做行矫正，所以置信度对方向不敏感，框形状敏感） |
| 方向判定（0/180） | 关掉行方向分类器后的 OCR 识别质量；退化时用文本行内墨迹质心偏移 | 同上 + 经验规则（正立字形重心偏上） |
| 纠偏 | 投影轮廓峰值搜索（`sum(row_ink²)/sum(row_ink)²`） | 经典 deskew 判据，与 Hough 等价但更省算力 |
| 去光照/阴影 | 大核高斯估计背景后做除法（flat-field），再按纸张分位数归一 | 手机扫描器通用做法；学术版可换 BEDSR-Net / SD7K |
| 二值化 | Sauvola & Pietikäinen (1997)：`T = m(1 + k(s/R − 1))` | *Pattern Recognition* 30(7)；scikit-image 的 `threshold_sauvola` 同式 |
| 扫描观感 | 彩色层（提亮但保留色相）+ Sauvola 墨迹层合成 | 手机扫描 App 的 "magic color" 思路 |
| 纸张轮廓 | 粗尺度亮度分割 + 凸包填充 | 避免"浓墨手写块被判成背景而洗白"这一类经典翻车 |

## 4. 评测（本次两张实测）

| 页 | 原始 | 判定 | 耗时 |
| --- | --- | --- | --- |
| 4.1–4.3 实践单位考核 | 1706×1279，横躺 90°，约 1.1° 歪 | `orient=90`，confidence high（OCR 质量 374 : 5） | ≈6 s/页 |
| 5–6 校内导师考核 | 1706×1279，横躺 90°，约 0.5° 歪 | `orient=90`，confidence high（OCR 质量 355 : 11） | ≈6 s/页 |

两页都在 20 秒内产出 300 DPI 的 A4 比例扫描图与合并 PDF，红章保留、手写保留。
