---
name: ylx_ppt_assembler
description: GPT-5.5 组装 PPTX——读 PPT 制作指南 → 发 GPT-5.5 生成 python-pptx 代码 → 出 .pptx。默认不启用，仅当用户明确说"启用组装工作台"、"GPT 组装"、"让 GPT 做 PPT"时才触发。
enabled: false
---

# PPT 组装工作台

调用 GPT-5.5 读取 `*_PPT制作指南.md`，生成 python-pptx 脚本并执行出 `.pptx`。

## 启动方式

```bash
cd ppt制作/PPT组装工作台
python assemble.py ../京津冀平台ppt/<页面文件夹>/
```

## 流程

1. 读指南 → 构建 prompt
2. 发 GPT-5.5 API → 展示返回的代码
3. 用户确认 `[Y/n]` → 保存 `build.py` → 执行 → 出 `.pptx`
4. 如果 GPT 代码有小 bug，自动保留 `build.py` 供手动改

## 适用

- 任何有一份 `*_PPT制作指南.md` 的页面文件夹
- 页面可以带图（`component-*.png`）也可以纯文字

## 注意

- 默认不启用，仅当用户说"启用组装工作台" 或 "让 GPT 组装 PPT" 时才加载
- GPT 生成的代码有时需要手动修 1-2 行（如 RGBColor 参数拆分）
