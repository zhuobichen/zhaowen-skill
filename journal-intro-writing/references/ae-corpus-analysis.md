# AE 引言全量实测（*Atmospheric Environment*，19 条记录 / 去重 17 篇 / 成功抽取 16 篇）

> 测量日期：2026-10-19
> 方法：Zotero 库按 `publicationTitle` 筛出 19 条 AE 记录（其中 2 条为重复条目），
> 用 PyMuPDF 按**首行缩进**重建段落（Elsevier 正文首行缩进，比 block 边界可靠），
> 抽取 Introduction 后剔除作者信息块、页眉与 DOI 行。

---

## 一、全量表

| # | 论文 | 类型 | 段 | 词 |
|:--:|---|---|:--:|:--:|
| 1 | Guillas et al., 2008 | CTM 统计订正降尺度 | **4** | **347** |
| 2 | Yu et al., 2018 | 方法横向比较（14 方法/8 污染物） | **4** | **468** |
| 3 | 五城市逐日指标融合评估, 2017 | 融合产品健康评估 | 6 | 603 |
| 4 | Berrocal et al., 2020 | 统计 vs 机器学习 | 6 | 644 |
| 5 | Wells et al., 2021 | 气象订正趋势（方法改进） | 6 | 650 |
| 6 | CAMS vs CMAQ, 2024 | 两产品比较 | 7 | 744 |
| 7 | Madden et al., 2026 | 可扩展贝叶斯地统计 | 8 | 805 |
| 8 | 优化融合改进侧边界, 2018 | 融合方法改进 | 6 | 810 |
| 9 | WRF-CMAQ 二十年动态评估, 2017 | 模型评估维度 | 7 | 870 |
| 10 | 北京臭氧时空变化与成因, 2021 | 城市尺度趋势 | 6 | 945 |
| 11 | Di et al., 2024 | **八套公开 PM₂.₅ 数据集评估** | 8 | 1,003 |
| 12 | 汾渭平原臭氧控制, 2026 | 控制策略 | 8 | 1,025 |
| 13 | Alkuwari et al., 2013 | EOF 统计降尺度 | 10 | 1,271 |
| 14 | Tang et al., 2024 | 韩国 ML 融合 | 12 | 1,285 |
| 15 | Mousavinezhad et al., 2023 | 臭氧趋势与死亡 | 9 | 1,641 |
| 16 | Hojeily et al., 2026 | 城市尺度融合 | 13 | 1,925 |

> 未抽出：[CHMU67KM] 2019 PM₂.₅ 达标系统（EPA 作者稿，版式与期刊排版不同，未定位到 Introduction）。

**统计**

| 指标 | 值 |
|---|---|
| 段落数 范围 / 中位 | 4–13 / **6–7** |
| 总词数 范围 / 中位 | 347–1,925 / **~840** |
| 项目符号 | **0** |
| 组织结构段（"The paper is organized as follows"） | 约半数（Tang、CAMS-CMAQ 有；Yu、Di、Madden 无） |

---

## 二、两种风格

### 紧凑论证型（4–8 段，350–1,000 词）——12 篇

Guillas、Yu、五城市、Berrocal、Wells、CAMS-CMAQ、Madden、侧边界、WRF-CMAQ、北京、Di、汾渭平原。

**共同特征**

- 每段一个论点；引用成组。
- 具体结果数字 0–2 个。
- 缺口段短促、明确。

### 综述铺陈型（9–13 段，1,200–1,900 词）——4 篇

Alkuwari、Tang、Mousavinezhad、Hojeily。

**共同特征**

- 会以 "X et al. (year) 做了什么" 铺开一批研究。
- 会带具体指标数字（R²、RMSE）。
- **但最后仍收束到限制清单 + 本文目标。**

> 结论：**风格取决于论文类型，不取决于期刊。**
> 方法/数据集比较类 → 紧凑型；应用类 → 可放宽。

---

## 三、逐篇结构（重点 8 篇）

### 1. Di et al., 2024 —— 与本项目同构，最值得模仿

**结构（8 段 / 1,003 词）**

| 段 | 内容 |
|:--:|---|
| 1 | PM₂.₅ 是什么 + 健康危害（WHO 数据） |
| 2 | 中国应对（法规、5,000+ 站点） |
| 3 | 但：起步晚、标准低于 WHO、站点分布不均 → 遥感成为替代 |
| 4 | 多个长期高分辨率数据集被创建（ML + AOD + 地面真值） |
| 5 | 以往研究做了什么 |
| 6 | 以往研究的共同前提问题 |
| 7 | **核心方法学批评** |
| 8 | 本文目标 |

**收尾段（写法 A 原型）**

> **Given that** the ground truth used as learning samples ... originated from public national air quality monitoring network consisting of monitoring sites mainly located in urban and densely populated areas, **the assessment of datasets with the same source data is likely to yield overrated results**, as these sample points were presumed to be of the highest level of accuracy. **Consequently**, the assessment ... like **high Cross-Validation R-Squared (CV-R2) was always reported** by dataset creators, **which neglected** the model performance in regions originally without ground-based observation. **Therefore, the goal of this study is to** objectively assess and compare the accuracy of eight freely available PM2.5 concentration datasets with **completely independent observation records** ...

---

### 2. WRF-CMAQ 二十年动态评估, 2017 —— 「评价维度不足」原型

**结构（7 段 / 870 词）**：模型用途 → 四类评估框架 → 现有研究只做 operational → **dynamic evaluation 的定义与必要性** → 本文设计。

**关键段**

> There have been many studies focusing on the **operational evaluation** of regional air quality models, but **only few addressed the other three components** of the model evaluation framework recommended by Dennis et al. (2010). ... **Hogrefe et al. (2008) stated that operational model evaluation provides little insight into the reliability of the estimation of relative changes** which pertains to the actual model application in the regulatory setting and argued that more emphasis should be placed on the development and application of dynamic and retrospective model evaluation approaches. **Dynamic evaluation entails the assessment of the model's ability to reproduce the changes** in observed air quality conditions stemming from the changes in emissions and meteorology and is one of the key components for building confidence in a model's use for policy analysis.

> Dynamic model evaluation for a 21-yr timeframe over the contiguous U.S. (CONUS) **has never been performed**.

**要点**

- "operational vs dynamic" 的区分，和"点位精度 vs 长期变化判断"是同一种论证。
- **`has never been performed` 是 AE 合法的强缺口表述**，但范围必须写具体。

---

### 3. Tang et al., 2024 —— 综述型 + 限制清单

**结构（12 段 / 1,285 词）**：健康负担 → 监测网不均 → CTM/卫星各自局限 → 机器学习研究（按地区铺开，点名）→ 韩国具体研究（带 R²/RMSE）→ **限制清单** → 本文 → 章节组织。

**限制清单段**

> **The limitations of previously published studies include: 1) focus on observation dense regions; 2) prediction of single species; and 3) neglect potentially useful CTM model products**, including long-term public reanalysis datasets. **The objective of this study is to** further advance the capabilities to fuse measurement and CTM models to produce high-resolution near-surface estimates of multiple species ...

**点名写法（前一段）**

> Zheng et al. (2020) built a ML model in Beijing and tested the model in Shanghai ... Chen et al. (2021) used RF ML in the Yangtze River Delta ... Wei et al. (2020) found that adding spatiotemporal coordinates as predictors improved ... Di et al. (2016) used a CNN ...

> 这是**综述型**的典型写法，说明"点名作者"在 AE 里完全合法——关键是最后要收束到限制清单。

---

### 4. Madden et al., 2026 —— 「However」双线收束

**结构（8 段 / 805 词）**：健康 → 需要完整覆盖 → 监测稀疏 → 代理变量（CTM / AOD）→ downscaler → **贝叶斯：However 计算昂贵** → **机器学习：However 无不确定性量化** → **Here we introduce**。

> P5: We employ Bayesian inference ... **However, these models can become computationally burdensome** when fitting large numbers of monitors ... covariance inversions that scale cubically ...
>
> P6: Machine learning approaches ... are also effective ... **However, these do not provide straightforward and principled uncertainty quantification**, and do not explicitly model spatial–temporal dependence in the outcome.
>
> P7: **Here we introduce** a Bayesian spatial–temporal downscaler model ... with two extensions that enable the model to scale ...

**要点**：两条技术路线各给一个 "However"，缺口就是"两条各缺一半"。

---

### 5. 汾渭平原臭氧控制, 2026 —— 逐类局限 + Consequently

**结构（8 段 / 1,025 词）**：区域背景 → O₃ 恶化 → 输送 → 源解析方法及局限 → **前体物敏感性三类方法及局限** → 本文思路。

> **Although** photochemical indicators allow for rapid OPS identification, they simplify the nonlinear relationship ..., thereby amplifying uncertainties (Liu et al., 2022). The EBM approach requires ... and is constrained by ... (de Meij et al., 2024). **In contrast**, OBMs are associated by observational data ... **However**, since OBMs rely on historical observational data, they cannot predict future changes in OPS ... **Consequently, there is an urgent need to develop** rapid and accurate OPS identification methods ...

> 同一篇里出现两次 "Consequently, ..."，都是"方法局限 → 所以需要什么"的收尾。

---

### 6. 北京臭氧时空变化与成因, 2021 —— 缺口段最细

**结构（6 段 / 945 词）**：政策背景 + 全国恶化 → 机理一（NOx/VOC）→ 机理二（PM₂.₅ 下降）+ "remains controversial" → 以往都在国家/区域尺度 → **北京缺综合评估；以往只基于单站点或简单指标** → 本文。

> Previous studies ... were **only based on individual sites or applied with simple evaluation metrics** (Cheng et al., 2019b; Chen et al., 2020; Li et al., 2020). **For example**, the records of an urban site in Beijing showed ... (Chen et al., 2020). **All of the previous studies** showed ozone increases in Beijing, **but they concealed the spatial difference** ... **None of them have** comprehensively estimated the spatiotemporal variation of ozone in Beijing.

---

### 7. Yu et al., 2018 —— 最短，零数值

**结构（4 段 / 468 词）**：健康危害（一句话 6 篇引用）+ **收口句** → 三类做法 → 每类优缺点一段讲完 → 本文四个比较维度。

> Such studies use estimates of air pollutant **concentration fields** in reaching their conclusions.
>
> Results and outcomes of exposure estimation and epidemiologic studies **will also likely vary depending on the method used**.
>
> Comparisons were focused on four aspects: 1) spatial concentration fields; 2) Temporal correlations and statistical performance; 3) Auto-correlations ...; 4) Interspecies correlations.

**全篇具体数值：0 个。**

---

### 8. Berrocal et al., 2020 —— 五步缺口

> This paper aims to address an important gap in the current literature: **the fact that** ... they are typically only compared to simpler models **within the same modeling paradigms**. **Examples include** comparisons between A (refs); between B (refs); or between C (refs). **There has been very limited cross-paradigm comparisons** (refs), **likely due to** ... **In particular, there is a lack of** ...

五步：**主张 → 三个 examples → 反例 → 原因 → 具体缺口**。

---

## 四、其余 8 篇（结构速记）

| 论文 | 结构 |
|---|---|
| Guillas 2008（4 段/347） | O₃ 危害 → 统计与 CTM 各有成绩 → 统计可订正系统性缺陷 → **本文把两者结合，且"Previous studies ... have not taken advantage of statistical methods to directly correct the outputs"** |
| 五城市 2017（6 段/603） | 健康关联 → 中心站点代表性不足 → 指标不确定性 → 需要高分辨率场 → 本文应用融合方法 |
| Wells 2021（6 段/650） | O₃ 与气象 → 方法史 → **"However, most ... only a small number of variables / small region / seasonal mean"** → Porter 2015 的改进 → **"Here, the work of Camalier et al. is extended to ..."** → 本文细化清单 |
| CAMS vs CMAQ 2024（7 段/744） | 危害 → 不确定性来源 → 应对方法 → 现行业务系统 → **"A limitation ... is that ... An open question is whether ... that is the subject of this paper."** → 比较设计 |
| 侧边界 2018（6 段/810） | CTM 偏差 → LBC 是主要不确定性 → 两类设 LBC 方法各有限制 → 卫星增强有限 → 融合可解决 → 本文 |
| Alkuwari 2013（10 段/1,271） | O₃ 背景 → 法规 → 统计 vs CTM → 尺度错配 → 降尺度概念 → 已有少量降尺度研究 → 本文 EOF 方法 |
| Mousavinezhad 2023（9 段/1,641） | 4 段化学机理（引用成组）→ 法规演进（120→84→75→70 ppb）→ 气象订正方法史 → **三个转折串缺口（Despite / also limited to / Although … typically limited to）** → 本文 |
| Hojeily 2026（13 段/1,925） | 健康 → 政策与不达标 → 研究区特殊性 → 监测密度不足（13 个 O₃ 站点）→ 低成本传感器 → 融合技术（LUR/卫星/ML）→ 数据需求门槛 → 本文 SEDI |

---

## 五、跨篇规律与对旧版规则的修正

### 确认成立的

1. **引言的主语极少是作者名**（综述型除外）。
2. **方法谱系按"类别"组织**，每类一句话说清做法与局限。
3. **缺口必须可判定**——能说出"缺的具体是哪一环"，不能停在"需要进一步研究"。
4. **项目符号为 0**；句内 `1) 2) 3)` 可以。
5. **最后一段给本文路线**，常与章节组织段合并。

### 需要修正的（旧版写错了）

| 旧规则 | 实际情况 |
|---|---|
| "段落 5–7 段、600–900 词" | 实为 **4–13 段、347–1,925 词**，分两种风格 |
| "作者名开头的句子必须为 0" | Tang 2024、Hojeily 2026 大量点名；**点名合法，但必须服务判据** |
| "单篇结果数字 ≤2" | Tang 2024 有十余个；**判据是"数字是否支撑论点"，不是数量** |
| "必须有一个缺口段" | 仍然成立，但**四种写法**任选，不限于一种 |

---

## 六、结尾段的四种写法（16 篇逐篇核对）

| 写法 | 论文 | 结尾原文要点 |
|---|---|---|
| **目标句** | Di 2024 | "Therefore, the goal of this study is to objectively assess and compare…" |
| | 北京 2021 | "As a means of comprehensively and accurately evaluating…, this study analyzed the parametric or nonparametric linear trends of 12 ozone metrics…" |
| | 五城市 2017 | "In this paper, we apply the data fusion approach to a multicity time-series study…" |
| | Hojeily 2026 | "In this paper, we adopted the SEDI algorithm described in Lee et al. (2024)…" |
| **研究问题清单** | Mousavinezhad 2023 | "…we intend to provide answers to the following questions …: (1) What are the trends…? (2) How does meteorology impact these trends…? (3) What are the key meteorological variables…? (4) How have emission control policies impacted respiratory-related premature mortality…?" |
| **贡献 + 验证** | Madden 2026 | "**Here we introduce** a Bayesian spatial–temporal downscaler model … We demonstrate model utility and performance on two case studies … Finally, we detail new functionality…" |
| | Alkuwari 2013 | "To our knowledge, there is no application of PFCs as a downscaling method in the literature. **We present here the first of such application**…" |
| **增量改进清单** | Wells 2021 | "In this work, the authors explore potential refinements to the existing method … which are listed below. 1. …" |
| **章节组织**（常与其他并用） | Tang 2024 / CAMS 2024 / Alkuwari 2013 / WRF-CMAQ 2017 / Hojeily 2026 | "The paper is organized as follows. Section 2 … Section 3 …" |

> **观察**：章节组织段是**可选的**。Yu 2018、Berrocal 2020、Di 2024、Madden 2026、北京 2021 都没有。

---

## 七、四重转折型缺口（Mousavinezhad 2023）

> **Despite** the relative strengths of these approaches, many studies have used them to focus only on the relationship between ozone and a small set of meteorological variables, which limits their application. Studies have **also** limited their investigations to a specific city/region. **Although** several studies have examined large geographical regions such as the CONUS (Porter et al., 2015) and China (Mousavinezhad et al., 2021), **they are typically limited to** a relatively short period. **Additionally**, some studies tend to focus on seasonal average ozone levels, which fails to identify meteorological variables that influence the occurrence of episodes of ozone (Wells et al., 2021).

四刀砍完：变量太少 → 地域太窄 → 时期太短 → 只看季节均值。
剩下的位置恰好就是"多尺度 × 多变量 × 多年代 × 峰值浓度"。

---

## 八、抽取局限说明

| 论文 | 情况 |
|---|---|
| [CHMU67KM] 2019 PM₂.₅ 达标系统 | EPA 作者稿单栏版式，未定位到 Introduction，未纳入统计 |
| [HT5JHLST] / [W93WTUGW] | 与 [P33ZR5UN] / [JJGSN2TB] 为同一文献的重复条目，跳过 |
| 汾渭平原 2026 P6–P7 | PDF 文本层两栏交织，抽取时部分句子顺序错乱；结构与关键句已人工核对 |

---

## 九、与本项目的对照

本项目（多融合数据集的臭氧长期变化评估）同时对应三种现成范式：

| 现成范式 | 对应关系 |
|---|---|
| **Di 2024** | 8 套数据集互比；现有评价（CV）与实际关心的问题脱节 → 换独立基准 |
| **WRF-CMAQ 2017** | operational（点位拟合）vs dynamic（能否复现变化）→ 正是"CV vs 长期趋势判断" |
| **Tang 2024** | 直接可用 `limitations include: 1) … 2) … 3)` 的收束式 |

**推荐路线**：写法 B（评价维度不足）为主，写法 D（限制清单）为辅，
最后用 Di 2024 的 "Therefore, the goal of this study is to …" 收口。
