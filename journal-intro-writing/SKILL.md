---
name: journal-intro-writing
description: AE 范式（Atmospheric Environment 实测 19 篇、精读 9 篇、48 段统计）的期刊 Introduction / 研究背景写作法。核心是「引言讲一个领域，不是给文献写摘要」：按知识点分段、引用成组挂句尾、单篇结果数字 ≤2、缺口须写成可判定的方法学缺陷（Given that → Consequently → Therefore）、中心议题与题目主语对齐。当用户要写论文引言/研究背景、抱怨「写得像综述」「像报告」「很怪」「抓不到重点」，或要把文献笔记改写成论文体时使用。
---

# AE 范式：期刊 Introduction / 研究背景写作法

> **语料边界**：本 skill 的范式来自本机 Zotero 库内 **19 篇 *Atmospheric Environment* 论文**
> （精读 9 篇、48 个段落统计）。它是对 AE 实际稿件的归纳，**不是 Elsevier 官方写作规范**；
> 样本为用户自有库，存在选择偏差。跨期刊使用时，建议先核对目标刊的 Guide for Authors。

## 两条核心判据

**判据一：删掉所有作者名和年份，论证还成立吗？**

- 成立 → 你在讲一个领域，合格。
- 不成立 → 你在写 annotated bibliography，不合格。

**判据二：引言的「中心对象」等于题目的「主语」吗？**

- 相等 → 读者从第一段就知道你要问什么。
- 不等 → 整篇读下来"很全"，但不知道在问什么。这是最隐蔽、也最致命的病。

> 例：题目是「**数据集选择**如何改变对长期变化的解释」，
> 引言前三分之一却在校述臭氧健康与法规史 → 判据二不通过。

## 实测基线（9 篇 AE）

| 指标 | 实测 | 建议 |
|---|---|---|
| 段落数 | **4–9**（中位 6） | 5–7 |
| 总词数 | **495–1,500**（中位 ~870） | 600–1,000 |
| 每段词数 | 中位 **130**，范围 27–278 | 80–200 |
| 段首用连接/过渡词 | **35%**（其余直接进入事实） | 1/3 左右 |
| 平均句长 | 25–32 词 | 26–30 |
| 成组引用占比 | 高 | ≥60% |
| 单篇结果数字 | **0–2** | ≤2 |
| 项目符号 | **0** | 0 |

> 「背景级数字」= 法规阈值、量级、年份、百分比变化。
> 「结果级数字」= 某论文的 R²、RMSE、回归系数。**这类不进引言。**

## 三种缺口写法（引言的胜负手）

### 写法 A：方法学缺陷型 —— 最有力量

**适用**：现有评价体系存在结构性偏差，本文换一种评价方式。

三步：**机制 → 后果 → 本文目标**

原文（Di et al., 2024, *AE* 338:120799）：

> **Given that** the ground truth used as learning samples during the development of these datasets originated from public national air quality monitoring network consisting of monitoring sites mainly located in urban and densely populated areas, **the assessment of datasets with the same source data is likely to yield overrated results**, as these sample points were presumed to be of the highest level of accuracy. **Consequently**, the assessment of trained ML models with considerable error metrics like high Cross-Validation R-Squared (CV-R2) **was always reported** by dataset creators, **which neglected** the model performance in regions originally without ground-based observation. **Therefore, the goal of this study is to** objectively assess and compare the accuracy of eight freely available PM2.5 concentration datasets with **completely independent observation records** from monitoring sites predominantly located in suburban and sparsely populated areas.

**可复制的骨架**

```
Given that [现有做法的前提], the [常规评估/建模] is likely to [系统性偏差],
because [为什么].
Consequently, [现有研究报告的指标] was always [被当作结论],
which neglected [真正关心的东西].
Therefore, the goal of this study is to [换一个评价对象/基准].
```

这是"CV 高 ≠ 可信"这类论点的标准写法。**如果你要论证现有评价指标不足以支撑你的结论，用这个骨架。**

### 写法 B：逐类局限型

**适用**：方法谱系宽，需要说明每类都缺一块。

每介绍一类，紧跟它的局限，段落用 **Consequently** 收尾。

原文（汾渭平原, 2026, *AE*）:

> **Although** photochemical indicators allow for rapid OPS identification, they simplify the nonlinear relationship between O3 and its precursors, thereby amplifying uncertainties (Liu et al., 2022). The EBM approach requires designing numerous emission sensitivity experiments and is constrained by uncertainties in the emission inventory (de Meij et al., 2024). In contrast, OBMs are associated by observational data and can better represent the evolving characteristics ... **However**, since OBMs rely on historical observational data, they cannot predict future changes in OPS and are thus inadequate for supporting practical operational needs. **Consequently, there is an urgent need to develop** rapid and accurate OPS identification methods ...

**骨架**

```
Although [方法 A] allows ..., it [局限 A] (refs).
[方法 B] requires ..., and is constrained by [局限 B] (refs).
In contrast, [方法 C] can ..., However, since [原因], it cannot ... (refs).
Consequently, there is an urgent need to [本文要提供的东西].
```

### 写法 C：开放问题型

**适用**：现有系统能跑，但有一个关键问题没回答。

原文（CAMS vs CMAQ, 2024, *AE*）:

> **A limitation of** this current NAQFC operational method **is that** it is inherently point-based, with ground truth concentrations known only at AirNow station locations. **An open question is whether** that approach could be improved upon by instead defining a gridded "truth" dataset ... **The first step to answering that question is** to explore what gridded datasets could provide the best gridded analysis ... **and that is the subject of this paper.**

**骨架**

```
A limitation of [现有做法] is that [局限].
An open question is whether [可改进方向].
The first step to answering that question is [本文做的那一步],
and that is the subject of this paper.
```

## 关于「点名作者」——不是禁止，而是必须有判据

AE **允许**写 "Ali et al. (2022) obtained ..."，但只在一种情况下：**这个作者名承担了一个判据**。

北京臭氧那篇（2021, *AE*）的用法：

> Previous studies ... were only based on individual sites or applied with simple evaluation metrics (Cheng et al., 2019b; Chen et al., 2020; Li et al., 2020). **For example**, the records of an urban site in Beijing showed that the annual MDA8-O3 ... increased by 2.30 and 1.91 ppbv year−1 (Chen et al., 2020). **All of the previous studies** showed ozone increases in Beijing, **but they concealed the spatial difference** ... **None of them have** comprehensively estimated the spatiotemporal variation.

点名 Chen et al. 不是因为他重要，而是因为**他的数字恰好证明了"只基于单站点"这个缺陷**。

**判据**：删掉作者名，这个论点还成立吗？

- 成立 → 不必点名，改成成组引用。
- 不成立 → 可以点名，但必须写出"它证明了什么"。

## 黄金六段

| 段 | 任务 | 结束时读者应知道 |
|:--:|---|---|
| 1 | 现象的重要性 + 现状数字（背景级） | 为什么值得做 |
| 2 | 机理 / 为什么难 | 问题的性质 |
| 3 | 已有做法，**按类别**推进 | 领域里有几类解法 |
| 4 | 每一类的局限 → Consequently | 为什么还不够 |
| 5 | 缺口（写法 A/B/C 之一） | 缺的到底是哪一个具体环节 |
| 6 | 本文目标 + 路线 | 本文做什么、分几步 |

段数 4–9 都正常；**但每一段必须是论点的递进，不是文献的并列**。

## 八句可复制句式

1. **起手**（主语是现象，引用成组）
   > Ambient air pollution is among the leading overall risk factors for global mortality (Cohen et al., 2017; Landrigan et al., 2018; Murray et al., 2020).

2. **收口句**——把宽背景收到研究对象
   > Such studies use estimates of air pollutant concentration fields in reaching their conclusions.
   *（Yu et al., 2018）*

3. **方法列举**——方法名 + 括注一篇代表
   > These approaches include ordinary least squares, universal kriging (Cressie, 1993), statistical downscaling (Berrocal et al., 2010), and machine learning methods, including random forest (Hu et al., 2017) ...
   *（Berrocal et al., 2020）*

4. **缺口开场**
   > This paper aims to address an important gap in the current literature: the fact that ...

5. **机制 → 后果 → 本文**（写法 A）
   > Given that ..., the assessment ... is likely to ... Consequently, ... was always reported ..., which neglected ... Therefore, the goal of this study is to ...

6. **逐类局限收尾**（写法 B）
   > Consequently, there is an urgent need to develop ...

7. **开放问题**（写法 C）
   > An open question is whether ... The first step to answering that question is ... and that is the subject of this paper.

8. **路线**（句内编号，不换行）
   > Comparisons were focused on four aspects: 1) spatial concentration fields; 2) Temporal correlations and statistical performance; 3) Auto-correlations ...; 4) Interspecies correlations.

## 改写流程（4 步）

### Step 1 定中心
用题目的主语写一句：**本文问的是 ______。**
写不出来 → 题目没吃透，先回去看标题。

### Step 2 拆段
给每段标一个"论点"。
- 写不出论点（只能写"这段介绍了某某等"）→ 合并或重写。
- 重排成：重要性 → 机理 → 做法 → 局限 → 缺口 → 本文。

### Step 3 收引用
`X 等发现 Y[n]` → `Y 这一现象已被反复报告[1,2,3]`。
主语从**作者**换成**现象 / 方法 / 结论**。

### Step 4 删数字
只留 ≤2 个背景级数字，其余移到 Results / Discussion。

## 自检清单（12 条，逐条可判定）

- [ ] 1. 每段第一句是一个**论断**，不是"某某研究了"？
- [ ] 2. 删掉所有作者名和年份，论证仍然成立？
- [ ] 3. 引言的**中心对象** = 题目的**主语**？
- [ ] 4. 没有任何一段以"此外 / 首先 / 其次 / 最后"开头？
- [ ] 5. 每段至少一处引用？
- [ ] 6. 成组引用（≥2 篇并列）占全部引用的 60% 以上？
- [ ] 7. 单篇文献的具体结果数字 ≤2 个？
- [ ] 8. **有一个明确写出的缺口句**，且用的是 A/B/C 三种骨架之一？
- [ ] 9. 缺口句之前，是否有"每类方法的局限"作为铺垫？
- [ ] 10. 最后一段给出本文路线，用句内编号而非项目符号？
- [ ] 11. 段落 5–7 段、总词数 600–1,000？
- [ ] 12. 每段 80–200 词，没有超过 280 词的巨段？

## 两个常见误判

**「引用要具体」≠「把每篇的 R² 抄进引言」**
具体指的是**论点具体**（"这类方法在留出检验下抓不住空间梯度"），不是数字多。

**「不能笼统」≠「必须逐篇复述」**
AE 的做法是把文献归到类别里，一句话说清这一类的做法与局限，括号里给三五个代表。

## 参考

- `references/ae-corpus-analysis.md` —— 9 篇论文的实测数据与原文摘录
- `references/before-after.md` —— 四组逐句改造对照
