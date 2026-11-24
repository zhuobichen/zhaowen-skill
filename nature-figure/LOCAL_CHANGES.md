# 本地改动说明（相对上游）

- 上游：<https://github.com/Yuan1z0825/nature-skills>（Apache-2.0）→ `skills/nature-figure/`
- 本目录基于上游 **v2.1.0** 快照（上游现已 v2.8.0）
- 许可证：见同目录 `LICENSE`（Apache License 2.0，版权归上游作者）

## 相对上游的差异

1. **删除的文件**（上游有、本地没有）：
   - `assets/chart-atlas/`（10 张图表图集）
   - `assets/gallery/`
   - `assets/figures4papers/` 下的预览图片（`assets/*.png`）与按论文分目录的 `figures/` 图
   - `references/ai-graphical-abstract-workflow.md`
   - `agents/openai.yaml`
2. **修改的文件**：`SKILL.md`、`manifest.yaml`（`version` 2.1.0，缺上游新增的 `graphical_abstract_workflow` 等 route）、
   `README.md` / `README_EN.md`、`evals/evals.json`。
3. **保留的第三方内容**：`assets/figures4papers/` 下的绘图脚本来自 `ChenLiu-1996/figures4papers`，
   **不受本目录 Apache-2.0 覆盖**，其声明见 `assets/figures4papers/THIRD_PARTY_NOTICES.md`（随本次修复恢复）。

## 注意

- 本地 2.1.0 的 `SKILL.md` / `manifest.yaml` 已不引用上述被删文件，单独放回一个文件没有意义。
- 若要与上游对齐，按 `../../SYNC.md` 的「跟版本型」逐处合并，或整体升级到 2.8.0 后重新做本地改动。
- Apache-2.0 要求：保留 `LICENSE`、标注修改（本文件即该标注）、上游无 NOTICE 文件故不涉及。
