# AE 引言实测语料（Atmospheric Environment，19 篇筛查、5 篇精读）

> 测量日期：2026-10-19
> 方法：从 Zotero 库筛出 `publicationTitle` 含 *Atmospheric Environment* 的条目（19 篇），
> 用 PyMuPDF 抽取 Introduction 正文，人工校正段落边界后统计。
> **注意**：双栏 PDF 的段落边界可能被页眉/页码打断，段落数为校正后的值。

---

## 一、总表

| 论文 | 卷期 | 类型 | 段落 | 总词数 | 平均句长 |
|---|---|---|:--:|:--:|:--:|
| Yu et al., 2018 | 179: 49–60 | 方法横向比较（14 方法 / 8 污染物） | **5** | ~515 | 27.1 |
| Berrocal et al., 2020 | 222: 117130 | 统计 vs 机器学习跨范式比较 | **5** | ~495 | ~29 |
| Mousavinezhad et al., 2023 | 300: 119693 | 臭氧趋势 + 健康 | **8** | ~1,500 | ~29 |
| Hojeily et al., 2026 | 371: 121805 | 城市尺度数据融合 | **8–9** | ~1,300 | ~27 |
| CAMS vs CMAQ, 2024 | — | 两产品差异 + 评价缺口 | **7–8** | ~1,100 | ~30 |

**结论**：AE 引言普遍 **5–8 段、450–1,500 词**，平均句长 **27–32 词**。
越是"方法比较类"论文（与本项目最像），引言越短。

---

## 二、逐篇要点

### 1. Yu et al., 2018 —— 最短、最干净，最适合做模板

**结构（5 段）**

| 段 | 内容 | 词数 |
|:--:|---|:--:|
| P1 | 空气污染的健康危害（一句话带 6 篇引用）+ **收口句** | 87 |
| P2–P3 | 历史上三类做法 + hybrid | ~100 |
| P4 | 每一类的优缺点，一段讲完 | 185 |
| P5 | 本文比较四个维度（句内编号） | 143 |

**关键原文**

起手（主语是现象，引用成组）：
> Exposure to ambient air pollution is associated with a range of adverse health outcomes, from minor respiratory tract irritation to increased premature mortality (Bernstein et al., 2004; Kampa and Castanas, 2008; Kaufman et al., 2016; Kim, 2004; Pope and Dockery, 2006; Rohr and Wyzga, 2012).

**收口句**（把宽背景收到"浓度场"）：
> Such studies use estimates of air pollutant concentration fields in reaching their conclusions.

方法谱系（只列类别，一句话带过）：
> In the past, a variety of approaches have been used to assign pollution concentration levels to both individuals and populations, including simple measurement-based methods (Jerrett et al., 2005), empirical modeling (Zou et al., 2009) and air quality modeling techniques (Özkaynak et al., 2013a). More recently, hybrid methods, combining multiple approaches have been developed (Beckerman et al., 2013; Hu et al., 2014; Ivey et al., 2015, 2016; Ozkaynak et al., 2013).

优缺点（**一段讲完所有类别，不分类分段**）：
> Simpler methods are typically easier to implement as they require minimal inputs and little complex mathematical modeling. However, the results may also be limited … Emission-based air quality models can require extensive amounts of input data, computational effort, and expertise … but can account for more factors … Air quality models can also suffer from biases and errors … Satellite retrieval based methods can capture spatial pollutant variations, but … Overall, each method has its own strengths and weaknesses.

动机句（从"各有优缺点"直接推到"所以结果会不同"）：
> Results and outcomes of exposure estimation and epidemiologic studies will also likely vary depending on the method used (Baxter et al., 2013; Goldman et al., 2010, 2012).

路线（句内编号）：
> Comparisons were focused on four aspects: 1) spatial concentration fields; 2) Temporal correlations and statistical performance; 3) Auto-correlations of estimated concentrations and method errors; 4) Interspecies correlations.

**全篇具体数值：0 个。**

---

### 2. Berrocal et al., 2020 —— 缺口段写得最好

**结构（5 段）**

| 段 | 内容 |
|:--:|---|
| P1 | 需要高分辨率全覆浓度场 + 方法激增 |
| P2 | **缺口**：现有比较都是"同范式内比较" |
| P3 | Our objective + 方法列举 |
| P4 | 与其他领域对比（缺少公开数据集） |
| P5 | another contribution：公开数据与代码 |

**缺口段原文（五步结构）**

> This paper aims to address an important gap in the current literature: **the fact that**, when models to estimate ambient air pollution exposure are being developed, they are typically only compared to simpler models **within the same modeling paradigms**. **Examples include** comparisons between regression models with different predictors, especially in land use regression models (Tang et al., 2013; Wang et al., 2016); between geostatistical models with different spatial dependence structures (Reich et al., 2011); or between different machine learning algorithms (Singh et al., 2013; Reid et al., 2015). **There has been very limited cross-paradigm comparisons** (Adam-Poupart et al., 2014; Yu et al., 2018), **likely due to** the analytic effort and expertise required to carry out the different approaches. **In particular, there is a lack of** comparison between machine learning and advanced geostatistical approaches.

拆解：

1. **主张**：This paper aims to address an important gap … the fact that …
2. **三个 examples**：Examples include … between A (refs); between B (refs); or between C (refs)
3. **反例**：There has been very limited cross-paradigm comparisons (refs)
4. **原因**：likely due to …
5. **具体缺口**：In particular, there is a lack of …

**方法列举原文（六种方法一句带过）**

> These approaches include ordinary least squares, universal kriging (Cressie, 1993), statistical downscaling (Berrocal et al., 2010), and machine learning methods, including random forest (Hu et al., 2017), support vector machine (Liu et al., 2017), and neural networks (Di et al., 2016).

**全篇"X 等发现 Y"句式：0 个。**

---

### 3. Mousavinezhad et al., 2023 —— 知识陈述式写法

**特点**：前 4 段全部在讲臭氧化学（NOx/VOC、滴定、下风向生成），**没有一段是在介绍某篇文献**。

段 1（危害，引用成组）：
> Ground-level ozone at high levels adversely impacts ecosystems and human health (Fleming et al., 2018; Malley et al., 2017; Mills et al., 2018; Monks et al., 2015).

段 3（化学机理，引用成组挂在句尾）：
> Among the main ozone precursors are NOx (NO + NO2) and volatile organic compounds (VOCs), which are released into the atmosphere by anthropogenic and natural emission sources (Lops et al., 2022; Pan et al., 2015; Sadeghi et al., 2022b).

法规演进（**背景级数字可以直接写**）：
> Following the lowering of NAAQS for ozone from 120 parts per billion (ppb) in 1979 to 84 ppb in 1997, ozone levels have decreased throughout the eastern US and parts of California (Cooper et al., 2012; Simon et al., 2015). … the NAAQS level of ozone further declined to 75 ppb in 2008 and then to 70 ppb in 2015 (US EPA, 2015).

缺口段的写法（**归纳差异，不逐篇复述**）：
> **Some of the most common techniques are** statistical methods of linear and nonlinear regression (Cox and Chu, 1993), more sophisticated approaches such as Bayesian methods (Huang and Smith, 1999), Kolmogorov-Zurbenko (KZ) filters (Wise and Comrie, 2005), principal component analysis (Kovač-Andrić et al., 2009), machine learning methods (Grange et al., 2018), and generalized linear models (Wells et al., 2021). **Despite the relative strengths of these approaches, many studies have used them to focus only on** the relationship between ozone and a small set of meteorological variables, which limits their application. **Studies have also limited their investigations to** a specific city/region. **Although several studies have examined** large geographical regions such as the CONUS (Porter et al., 2015) and China (Mousavinezhad et al., 2021), **they are typically limited to** a relatively short period.

三个转折串起缺口：`Despite …` → `also limited to …` → `Although … typically limited to …`。

---

### 4. Hojeily et al., 2026

**结构（8–9 段）**：健康 → 政策与不达标现状 → 研究区特殊性 → 监测密度不足 → 低成本传感器 → 现有融合技术（LUR / 卫星 / ML）→ 现有方法的数据需求门槛 → 本文采用 SEDI。

**特点**：每一段都在回答"为什么还需要本文这套做法"，而不是"谁做过什么"。

监测不足的写法（**给具体数字，但那是事实而非某论文的结果**）：
> Regulatory-grade measurements from monitoring sites, however, are insufficient to capture hyperlocal variability; major urban areas may only have a handful of monitors, e.g., 13 O3 regulatory-grade sites in NYC.

---

### 5. CAMS vs CMAQ, 2024

**结构（7–8 段）**：两产品定位 → 各自方法差异 → 已有比较的局限 → 本文比较设计 → 预期用途。

---

## 三、可提取的稳定规律

1. **引言的主语几乎从不是作者名**。出现频率最高的主语是现象、方法类别、数据产品。
2. **引用以组为单位**，单篇引用通常只出现在"本文直接沿用某方法"的位置。
3. **具体数值很少**，且多为法规阈值、时间跨度、空间分辨率这类背景常量。
4. **缺口段是全文唯一允许"直接反驳"的地方**，句式高度模板化（Despite / However / Although / There has been very limited …）。
5. **方法谱系按"类别"组织**，每类一句话说清做法与局限；不按时间、不按作者。
6. **最后一段就是本文路线**，用句内编号列出比较维度或贡献，不换行。
