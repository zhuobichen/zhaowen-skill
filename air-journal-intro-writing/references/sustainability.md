# Sustainability 引言实测（MDPI，15 篇 / 93 段）

> 测量日期：2026-10-20
> 语料：用户 Zotero 库内 15 篇 *Sustainability*（ISSN 2071-1050）论文，
> 经 Zotero 本地 API 取 PDF，用 PyMuPDF 按首行缩进重建段落后抽取 Introduction。

---

## 一、逐篇统计

| 年 | 段 | 词 | 项目符号 | 论文 |
|:--:|:--:|:--:|:--:|---|
| 2026-07 | 5 | 791 | — | 近地面臭氧时空特征与演化驱动 |
| 2026-02 | 12 | 1,523 | — | Multi-Input Spatiotemporal RF–XGBoost Hybrid |
| 2026-01 | 8 | 892 | — | Interpretable Data-Driven Ozone Prediction (XGBoost/SHAP) |
| 2025-12 | 7 | 651 | — | Climate-Driven Changes in Air Quality: Trends |
| 2025-11 | 5 | 474 | — | **Intercomparison of Data Products（Guha & Henneman）** |
| 2024-12 | 7 | 753 | — | Estimation of Air Pollution Models with ML |
| 2024-08 | 7 | 923 | — | Evaluation of ML Models, Macau |
| 2024-01 | 8 | 963 | — | Supervised ML for Key Pollutants |
| 2022-08 | 5 | 764 | **有** | Research Trends of Ozone Pollution（综述） |
| 2022-08 | 4 | 532 | — | Environmental Justice: PM/O3/Hg, PRD |
| 2022-05 | 5 | 632 | — | Prediction of Ozone Hourly Concentrations |
| 2022-02 | 4 | 719 | — | Surface Ozone Pollution: Trends, Portugal |
| 2021-01 | 6 | 1,040 | — | Ensemble of Dynamic Transfer Models |
| 2020-07 | 6 | 780 | — | Effect of Emission Inventory on Exposure Metrics |
| 2018-08 | 4 | 765 | — | Daily PM2.5 Exposure, Beijing Kriging |

**汇总**：段落 **4–12**（中位 6）；词数 **474–1,523**（中位 765）；段落词数中位 **112**。

---

## 二、与 AE / AAQR 的对照

| 指标 | Sustainability（15 篇 / 93 段） | AE（16 / 120） | AAQR（14 / 93） |
|---|---:|---:|---:|
| 每篇段落数 中位 | **6**（4–12） | 7（4–13） | 6（4–12） |
| 每篇词数 中位 | **765**（474–1,523） | 840 | 884 |
| 段落词数 中位 | **112**（29–357） | 126 | 121 |
| 引用组 / 段 | **2.5** | 1.8 | 2.4 |
| 每百词引用组 | **1.9** | 1.4 | 1.7 |
| 有引用的段落 | 70% | 68% | 67% |
| 项目符号贡献列表 | **1/15（7%）** | 0 | 0 |
| **引用格式** | **数字 `[1–3]`** | 作者-年份 | 作者-年份 |

---

## 三、三条 Sustinability 特有规则

### 1. 引用必须是数字编号

MDPI 用 `[1]`、`[1–3]`、`[6,12,13]`，**不是作者-年份**。
这与中文 GB/T 7714 的顺序编码制天然一致，中文稿可直接沿用 `[n]`。

### 2. 篇幅更短，引用更密

中位 765 词、每段 112 词、每段 2.5 组引用。
比 AE 短约 10%，但引用密度高约 40%。

### 3. 项目符号不是主流

15 篇里只有 1 篇（综述类）用项目符号列贡献。
**正文请用连续散文，不要默认照搬 MDPI 部分论文的 `(1)(2)(3)` 贡献列表。**

---

## 四、体裁范例：Guha & Henneman (2025)

`10.3390/su172210059` —— **多套数据产品趋势互比**，与本类论文同构。

**结构（5 段 / 474 词）**

| 段 | 词 | 任务 |
|:--:|:--:|---|
| 1 | 81 | PM₂.₅/O₃ 健康危害 + 需要研究趋势 |
| 2 | 32 | 需要可靠数据产品；来源多样（卫星、CTM、地面） |
| 3 | 72 | 中国背景 + 数据产品发展 + 监测网/卫星部署 |
| 4 | 113 | 研究者如何组合多源数据 → 产品差异（输入、方法、尺度）→ **难以判断哪个产品更适合特定用途** |
| 5 | 176 | 本文做什么 + **缺口** + 动态评估 + 目的 |

**缺口句原文**

> While each dataset has previously been evaluated independently by its respective developers, **to our knowledge, no evaluation has been conducted under a consistent framework**. A prior study [17] evaluated the TAP and CHAP products for PM2.5; **however, our analysis spans a longer time period and incorporates dynamic evaluation** (i.e., the ability of the products to assess concentration changes across years).

**可直接复用的骨架**

```
各产品此前都由各自开发者独立评估过，
但据我们所知，尚无研究在统一框架下进行比较。
已有研究 [x] 比较过其中若干产品；但本文覆盖更长时间、并纳入 [更严格的评价维度]。
```

这是三类期刊里，**唯一与"多产品互比"完全同体裁的先例**。

---

## 五、写 Sustainability 时的调整

| 项 | 调整 |
|---|---|
| 段落数 | 6 段（4–8 亦可） |
| 词数 | 约 750 词（中文约 1,100–1,300 字） |
| 引用密度 | 每段 2–3 组，全文 30–40 条 |
| 引用格式 | **数字 `[n]`** |
| 项目符号 | 不用 |
| 缺口 | 优先用 Guha 的"独立评估过 / 未统一比较"骨架 |
| 体裁 | 该刊确有"多产品互比"先例（Guha 2025），可直接对标 |

---

## 六、抽取说明

- MDPI 为单栏排版，首行缩进检测有效。
- 页眉 "Sustainability 202X, XX, XXXXX" 与页码需剔除。
- 引用为数字格式，统计引用密度时须用 `\[\d+([,–-]\d+)*\]` 模式，
  用作者-年份正则会得到 0（本项目第一次统计就踩了这个坑）。
