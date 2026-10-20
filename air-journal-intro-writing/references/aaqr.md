# AAQR 引言实测（*Aerosol and Air Quality Research*，14 篇 / 93 段）

> 测量日期：2026-10-20
> 语料：用户 Zotero 库内全部 AAQR 论文（14 篇），经本地 API 取 PDF 后用 PyMuPDF
> 按首行缩进重建段落，抽取 Introduction 并剔除页眉/作者信息块。
> 版式：9 篇 Springer 新版（DOI `10.1007/s44408-*`，2025 起）+ 5 篇 aaqr.org 旧版（`10.4209/*`）。

---

## 一、逐篇统计

| 年 | 段 | 词 | 论文 |
|:--:|:--:|:--:|---|
| 2026-08 | 11 | 801 | DeepSIP: Sensor Data Imputation and Time Series Forecasting |
| 2026-06 | 12 | 1,136 | Deep Learning-Based Medium/Long-Term Ozone Forecasting, Shanghai |
| 2026-06 | 4 | 835 | Impacts of Climate-driven Biogenic VOC on Surface Ozone and Health, Guangdong |
| 2026-05 | 5 | 756 | ML Exploring Double High PM2.5 and O3 Pollution, SE China |
| 2026-04 | 7 | 1,389 | China Surface Ozone Remote Sensing Dataset, 1 km |
| 2026-03 | 4 | 792 | Emission Reductions and Sulfate Decrease, Henan |
| 2026-01 | 6 | 743 | GeoAI-Based Ensemble Mixed Spatial Prediction Model (NH₃) |
| 2025-07 | 7 | 991 | Role of HCl and Cl₂ in Tropospheric Ozone Formation, Delhi |
| 2025-04 | 4 | 1,043 | Visibility-Based Historical PM2.5 Estimation, 1981–2022, Thailand |
| 2024 | 8 | 863 | Relationship between Ozone and Temperature, Kuala Lumpur |
| 2023 | 4 | 718 | Future Climate Change and STE-Driven Ozone |
| 2021 | 11 | 1,084 | Hourly Ozone and PM2.5 Prediction Using Meteorological Data |
| 2020 | 5 | 904 | Increase in Surface Ozone over BTH from Satellite Retrievals |
| 2026-07 | 5 | 960 | Emission Control Policies and Environmental Justice, PRD |

**汇总**：段落 **4–12**（中位 6）；词数 **718–1,389**（中位 884）；段落词数中位 **121**。

---

## 二、与 AE 的对照

| 指标 | AAQR（14 篇 / 93 段） | AE（16 篇 / 120 段） |
|---|---:|---:|
| 每篇段落数 中位 | 6（4–12） | 7（4–13） |
| 每篇词数 中位 | 884 | 840 |
| 段落词数 中位 | 121（26–468） | 126（27–513） |
| 平均句长 | 28.7 词 | 26.1 词 |
| 段首为作者名 | 0% | 1% |
| 段首为连接词 | 4% | 8% |
| 有引用的段落 | 67% | 68% |
| **引用组 / 段（均值）** | **2.4** | **1.8** |
| **每百词引用组** | **1.7** | **1.4** |

**结论**：形式指标基本重合。**唯一稳定差异是引用密度——AAQR 每段约多 0.6 组引用。**

---

## 三、AAQR 特有的三点

### 1. 引用更密

同一段里常见连续两组以上引用，且常把方法与结论一起挂在一句之后。
写 AAQR 时，**每段 2–3 组引用**比 AE 的 1–2 组更接近期刊习惯。

### 2. 体裁偏"单区域 / 单时段"

14 篇里：
- 观测/机理分析 5 篇（HCl、硫酸盐、臭氧-温度、卫星反演、BVOC）
- 机器学习预报/估算 5 篇（DL 预报、ML 双高污染、DeepSIP、可见度重建、GeoAI 集成）
- 数据集/产品 1 篇（中国 1 km 臭氧）
- 政策/健康 3 篇（珠三角公平、河南减排、BVOC 健康）

**没有一篇是"多套成品数据集横向比较"。**
所以 AAQR 的引言范式教不会你"怎么把多产品比较讲成一个问题"。

### 3. 缺口段常写成"单一数据源/单一区域不足"

典型结构：
```
现有研究多集中在 A（refs）；然而 B 区域/尺度/物种的研究仍有限（refs）。
本研究因此聚焦 B，采用 … 方法。
```
比 AE 的"方法学缺陷型"缺口弱一档，更接近"填补区域空白"。

---

## 四、写 AAQR 时的调整

| 项 | 调整 |
|---|---|
| 段落数 | 5–6 段（比 AE 少一段） |
| 引用密度 | 每段 2–3 组 |
| 句子 | 可略长（28 词左右） |
| 缺口 | 若论文不是"填补区域空白"，需要用 AE 的写法 A/B 补强 |
| 章节组织段 | 两刊都可选；AAQR 14 篇里约半数有 |

---

## 五、抽取说明

- 3 篇旧版（2021/2023/2024）的章节标题为无编号全大写（"DATA AND METHOD"），需专门规则识别。
- 2020 年那篇（Li et al.）为单栏旧版，标题无编号。
- Springer 版标题含控制字符（`\x07`）与不换行空格，抽取时需清洗。
- 样本为用户自有库，存在选择偏差；14 篇不足以代表 AAQR 全刊。
