# AE 引言实测语料（Atmospheric Environment，19 篇筛查、9 篇精读）

> 测量日期：2026-10-19
> 方法：从 Zotero 库筛出 `publicationTitle` 含 *Atmospheric Environment* 的条目（19 篇），
> 用 PyMuPDF 按**首行缩进**重建段落（Elsevier 正文首行缩进，比 block 边界可靠），
> 抽 Introduction 正文后人工剔除作者信息块与页眉。
> 统计：9 篇共 **48 个有效段落**。

---

## 一、总表

| # | 论文 | 卷期 | 类型 | 段落 | 词数 |
|:--:|---|---|---|:--:|:--:|
| 1 | Yu et al., 2018 | 179: 49–60 | 方法横向比较（14 方法 / 8 污染物） | **5** | ~515 |
| 2 | Berrocal et al., 2020 | 222: 117130 | 统计 vs 机器学习跨范式比较 | **5** | ~495 |
| 3 | Mousavinezhad et al., 2023 | 300: 119693 | 臭氧趋势 + 健康 | **8** | ~1,500 |
| 4 | Hojeily et al., 2026 | 371: 121805 | 城市尺度融合 | **8–9** | ~1,300 |
| 5 | Di et al., 2024 | 338: 120799 | **八套公开数据集精度评估** | **6–7** | ~1,000 |
| 6 | 汾渭平原 O₃ 控制, 2026 | — | 臭氧控制策略（方法谱系） | **8** | ~1,025 |
| 7 | 北京 O₃ 变化与成因, 2021 | — | 城市尺度臭氧趋势 | **6** | ~945 |
| 8 | CAMS vs CMAQ, 2024 | — | 两产品比较 | **8** | ~790 |
| 9 | 五城市逐日指标融合评估, 2017 | — | 融合产品评估 | **6** | ~603 |
| 10 | WRF-CMAQ 二十年动态评估, 2017 | — | 模型动态评估 | **7** | ~870 |
| 11 | 优化融合改进侧边界, 2018 | — | 融合方法改进 | **6** | ~810 |

> 表内 3–4 为先前实测，1–2、5–11 为本轮补充。合计精读 9 篇（3–4 与 1、2、5、6、7、8、9/10/11 中的代表）。

## 二、段落统计（48 个有效段落）

| 指标 | 值 |
|---|---|
| 段落词数 中位 | **130** |
| 段落词数 均值 | 125 |
| 段落词数 范围 | 27 – 278 |
| 段首用连接/过渡词 | **35%**（其余直接进入事实） |
| 项目符号 | **0** |
| 单篇结果数字 | 0 – 2 |

**结论**：AE 引言 **4–9 段、495–1,500 词、每段中位 130 词**。
越是"数据集/方法比较类"论文（1、2、5、8），引言越短（5–8 段、500–1,000 词）。

**段首词分布（48 段）**

| 词 | 次数 |
|---|:--:|
| The | 4 |
| In | 3 |
| Given | 2 |
| Since | 2 |
| As | 2 |
| To | 2 |
| Another | 2 |
| However / Although / But / While / Yet | 各 1 或 0 |

没有任何一个连接词占主导；**段首多数时候直接是事实或论断**，不靠连接词撑结构。

---

## 三、逐篇要点

### 1. Di et al., 2024 —— 与"数据集选择"类论文同构，**最值得模仿**

**结构（6–7 段，约 1,000 词）**

| 段 | 内容 |
|:--:|---|
| 1 | PM₂.₅ 是什么 + 健康危害（WHO 数据） |
| 2 | 中国应对（法规、监测网建设，5000+ 站点） |
| 3 | 但：起步晚、标准低于 WHO、站点分布不均 → 遥感成为替代 |
| 4 | 多个长期高分辨率数据集被创建（ML + AOD + 地面真值） |
| 5 | 以往研究做了什么（评估再分析、分析时空格局、健康应用） |
| 6 | **核心方法学批评 + 本文目标** |

**最关键的收尾段（写法 A 原型）**

> **Given that** the ground truth used as learning samples during the development of these datasets originated from public national air quality monitoring network consisting of monitoring sites mainly located in urban and densely populated areas, **the assessment of datasets with the same source data is likely to yield overrated results**, as these sample points were presumed to be of the highest level of accuracy. **Consequently**, the assessment of trained ML models with considerable error metrics like **high Cross-Validation R-Squared (CV-R2) was always reported** by dataset creators, **which neglected** the model performance in regions originally without ground-based observation. **Therefore, the goal of this study is to** objectively assess and compare the accuracy of eight freely available PM2.5 concentration datasets with **completely independent observation records** from monitoring sites predominantly located in suburban and sparsely populated areas.

**为什么值得学**：它把"现有评价指标（CV-R²）不可信"直接立成研究动机，
论证链是**机制 → 后果 → 换基准**，没有一句在复述某篇文献的结果。

---

### 2. 汾渭平原 O₃ 控制, 2026 —— 写法 B 原型

**结构（8 段）**：区域背景与 O₃ 恶化 → 输送问题 → 源解析方法及其局限 → 前体物敏感性方法三类及其局限 → 本文思路。

**逐类局限 + Consequently 收尾**

> **Although** photochemical indicators allow for rapid OPS identification, they simplify the nonlinear relationship between O3 and its precursors, thereby amplifying uncertainties (Liu et al., 2022). The EBM approach requires designing numerous emission sensitivity experiments and is constrained by uncertainties in the emission inventory (de Meij et al., 2024). **In contrast**, OBMs are associated by observational data and can better represent the evolving characteristics of the nonlinear relationship ... **However**, since OBMs rely on historical observational data, they cannot predict future changes in OPS and are thus inadequate for supporting practical operational needs. **Consequently, there is an urgent need to develop** rapid and accurate OPS identification methods ...

> 注意：**同一篇论文里出现了两次 "Consequently, ..."**，都是"方法局限 → 所以需要什么"的收尾。

---

### 3. 北京 O₃ 变化与成因, 2021 —— 缺口段写得最细

**结构（6 段，945 词）**

| 段 | 内容 |
|:--:|---|
| 1 | 政策背景 + 全国 O₃ 恶化（2.4 ppb yr⁻¹、90% 站点正趋势） |
| 2 | 机理一：NOx/VOC regime |
| 3 | 机理二：PM₂.₅ 下降削弱气溶胶汇（"However, this issue remains controversial"） |
| 4 | **以往研究都在国家/区域尺度，城市尺度缺** |
| 5 | **但北京缺少综合定量评估；以往只基于单站点或简单指标** |
| 6 | 本文方法 |

**缺口段原文**

> Previous studies ... were **only based on individual sites or applied with simple evaluation metrics** (Cheng et al., 2019b; Chen et al., 2020; Li et al., 2020). **For example**, the records of an urban site in Beijing showed that the annual MDA8-O3 ... increased by 2.30 and 1.91 ppbv year−1 (Chen et al., 2020). **All of the previous studies** showed ozone increases in Beijing, **but they concealed the spatial difference** in ozone concentrations and trends. **None of them have** comprehensively estimated the spatiotemporal variation of ozone in Beijing.

**点名作者的正当用法**：提 Chen et al. (2020) 给出具体数字，
是因为那个数字**恰好证明了"只基于单站点"这个缺陷**。

---

### 4. CAMS vs CMAQ, 2024 —— 写法 C 原型

**结构（8 段，790 词）**：危害（健康 + 经济）→ 不确定性来源 → 应对方法（集合、AnEn、同化、偏差校正）→ 现行业务系统 → **其局限 + 开放问题** → 本文比较设计 → 章节组织。

**开放问题句式**

> **A limitation of** this current NAQFC operational method **is that** it is inherently point-based, with ground truth concentrations known only at AirNow station locations. **An open question is whether** that approach could be improved upon by instead defining a gridded "truth" dataset ... **The first step to answering that question is** to explore what gridded datasets could provide the best gridded analysis ... **and that is the subject of this paper.**

**注意**：这篇有 "The paper is organized as follows..." 段，但 Yu 2018 与 Di 2024 都没有。**组织结构段是可选的**，不是必需。

---

### 5. Yu et al., 2018 —— 最短、最干净

**结构（5 段，515 词）**

| 段 | 内容 | 词数 |
|:--:|---|:--:|
| 1 | 健康危害（一句话带 6 篇引用）+ **收口句** | 87 |
| 2–3 | 历史上三类做法 + hybrid | ~100 |
| 4 | 每一类的优缺点，一段讲完 | 185 |
| 5 | 本文比较四个维度（句内编号） | 143 |

**收口句**（把宽背景收到"浓度场"）

> Such studies use estimates of air pollutant concentration fields in reaching their conclusions.

**动机句**（从"各有优缺点"推到"所以结果会不同"）

> Results and outcomes of exposure estimation and epidemiologic studies will also likely vary depending on the method used (Baxter et al., 2013; Goldman et al., 2010, 2012).

**全篇具体数值：0 个。**

---

### 6. Berrocal et al., 2020 —— 五步缺口结构

> This paper aims to address an important gap in the current literature: **the fact that** ... they are typically only compared to simpler models **within the same modeling paradigms**. **Examples include** comparisons between A (refs); between B (refs); or between C (refs). **There has been very limited cross-paradigm comparisons** (refs), **likely due to** ... **In particular, there is a lack of** ...

五步：**主张 → 三个 examples → 反例 → 原因 → 具体缺口**。

**方法列举（六种方法一句带过）**

> These approaches include ordinary least squares, universal kriging (Cressie, 1993), statistical downscaling (Berrocal et al., 2010), and machine learning methods, including random forest (Hu et al., 2017), support vector machine (Liu et al., 2017), and neural networks (Di et al., 2016).

---

### 7. Mousavinezhad et al., 2023 —— 知识陈述式

前 4 段全部讲臭氧化学（NOx/VOC、滴定、下风向生成），**没有一段是在介绍某篇文献**。
法规阈值这类背景级数字可以直接写：

> Following the lowering of NAAQS for ozone from 120 ppb in 1979 to 84 ppb in 1997 ... the NAAQS level of ozone further declined to 75 ppb in 2008 and then to 70 ppb in 2015 (US EPA, 2015).

缺口用三个转折串起：`Despite …` → `also limited to …` → `Although … typically limited to …`。

---

### 8. Hojeily et al., 2026

**结构（8–9 段）**：健康 → 政策与不达标现状 → 研究区特殊性 → 监测密度不足 → 低成本传感器 → 现有融合技术 → 现有方法的数据需求门槛 → 本文采用 SEDI。

监测不足用**事实类数字**（不是某论文的结果）：

> Regulatory-grade measurements from monitoring sites, however, are insufficient to capture hyperlocal variability; major urban areas may only have a handful of monitors, e.g., **13 O3 regulatory-grade sites in NYC**.

---

### 9. 其余两篇（快速核对）

- **五城市融合评估, 2017**（6 段，603 词）：需求 → 融合产品 → 评价现状 → 缺口 → 本文 → 路线。
- **WRF-CMAQ 动态评估, 2017**（7 段，870 词）：模型用途 → 评估方法演进（operational vs dynamic）→ 以往评估的局限 → 本文设计。

两篇都遵循同一骨架，印证了范式的稳定性。

---

## 四、可提取的稳定规律

1. **引言的主语几乎从不是作者名**。最常见的主语是现象、方法类别、数据产品。
2. **引用以组为单位**；点名单篇只出现在"该文献的数字正好支撑某个判据"时。
3. **具体数值很少**，且多为法规阈值、时间跨度、空间分辨率、站点数这类**事实**，而非**某论文的结果**。
4. **缺口段是全文唯一允许"直接反驳"的地方**，句式高度模板化：
   `Despite / However / Although / There has been very limited / Given that … which neglected …`
5. **方法谱系按"类别"组织**，每类一句话说清做法与局限；不按时间、不按作者。
6. **"Consequently, there is an urgent need to …" 是方法局限段的标准收尾**。
7. **最后一段就是本文路线**，用句内编号列出比较维度或贡献，不换行。
8. **组织结构段（"The paper is organized as follows"）是可选的**，约半数论文没有。

---

## 五、与本项目的对照

本项目论文（多融合数据集的臭氧长期变化评估）与 **Di et al. 2024** 高度同构：

| 维度 | Di 2024 | 本项目 |
|---|---|---|
| 比较对象 | 8 套公开 PM₂.₅ 数据集 | 8 套臭氧融合数据集 |
| 现有评价 | 数据集作者自报 CV-R² | 站点交叉验证指标 |
| 评价缺陷 | 训练与评估站点同源 → 高估 | 点位精度 ≠ 长期趋势判断可靠 |
| 本文解法 | 用**完全独立**的观测记录 | 用**趋势保持 / 解释稳定性**作为评价对象 |

因此 Di 2024 的**写法 A（机制 → 后果 → 换基准）**可直接作为本项目引言的骨架。
