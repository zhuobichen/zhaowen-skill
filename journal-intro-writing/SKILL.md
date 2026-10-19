---
name: journal-intro-writing
description: AE 范式（Atmospheric Environment 库里 19 条、去重 17 篇、精读 16 篇）的期刊 Introduction / 研究背景写作法。核心是「引言讲一个领域，不是给文献写摘要」：按知识点分段、引用成组挂句尾、缺口须写成可判定的方法学缺陷、中心议题与题目主语对齐。区分紧凑论证型（4–8 段）与综述铺陈型（9–13 段）两种风格。当用户要写论文引言/研究背景、抱怨「写得像综述」「像报告」「很怪」「抓不到重点」，或要把文献笔记改写成论文体时使用。
---

# AE 范式：期刊 Introduction / 研究背景写作法

> **语料边界**：来自本机 Zotero 库内 **19 条 *Atmospheric Environment* 记录**（去重后 17 篇，
> 其中 16 篇成功抽取引言）。是对 AE 实际稿件的归纳，**不是 Elsevier 官方写作规范**；
> 样本为用户自有库，存在选择偏差。

## 两条核心判据

**判据一：删掉所有作者名和年份，论证还成立吗？**

- 成立 → 你在讲一个领域，合格。
- 不成立 → 你在写 annotated bibliography。

**判据二：引言的「中心对象」等于题目的「主语」吗？**

题目讲「X 如何影响 Y」，引言就该围绕 X。前三分之一在讲 Y 的一般背景 → 判据二不通过。

> 这是最隐蔽的病：整篇读下来"很全"，但读者不知道你在问什么。

## 实测基线（16 篇）

| 指标 | 实测 |
|---|---|
| 段落数 | **4–13，中位 6–7** |
| 总词数 | **347–1,925，中位 ~840** |
| 每段词数 | 中位 ~110，短的可到 27 词，长的可到 518 词 |
| 段首用连接/过渡词 | 约 35%，其余直接进入事实 |
| 项目符号 | **0**（句内 `1) 2) 3)` 可以） |
| 组织结构段 | 约半数有，可选 |

原始数据见 `references/ae-corpus-analysis.md`。

## 两种风格（都合法，按论文类型选）

### 紧凑论证型 —— 4–8 段，350–1,000 词

**代表**：Guillas 2008（4 段/347）、Yu 2018（4 段/468）、Berrocal 2020（6 段/644）、
五城市 2017（6 段/603）、Wells 2021（6 段/650）、CAMS vs CMAQ 2024（7 段/744）、
Madden 2026（8 段/805）、侧边界 2018（6 段/810）、WRF-CMAQ 2017（7 段/870）、
北京 2021（6 段/945）、Di 2024（8 段/1,003）、汾渭平原 2026（8 段/1,025）

**特征**：每段一个论点；引用成组；具体结果数字 0–2 个。
**适用**：方法比较、数据集比较、评价体系改进。

### 综述铺陈型 —— 9–13 段，1,200–1,900 词

**代表**：Alkuwari 2013（10 段/1,271）、Tang 2024（12 段/1,285）、
Mousavinezhad 2023（9 段/1,641）、Hojeily 2026（13 段/1,925）

**特征**：会用 "X et al. (year) 做了什么" 的形式铺开一批研究，会带具体指标数字。
但**最后仍会收束到一段限制清单 + 本文目标**。
**适用**：应用型论文、需要交代领域全貌的场合。

> **两条路都通向同一个终点**：在引言末尾用一个明确的方法学缺口把本文接上。
> 区别只在于铺垫的厚度。

## 四种缺口写法

### A. 方法学缺陷型 —— 最有力量

**三步：机制 → 后果 → 换基准**

原型（Di et al., 2024, *AE* 338:120799）：

> **Given that** the ground truth used as learning samples ... originated from public national air quality monitoring network consisting of monitoring sites mainly located in urban and densely populated areas, **the assessment of datasets with the same source data is likely to yield overrated results**, as these sample points were presumed to be of the highest level of accuracy. **Consequently**, the assessment ... like **high Cross-Validation R-Squared (CV-R2) was always reported** by dataset creators, **which neglected** the model performance in regions originally without ground-based observation. **Therefore, the goal of this study is to** objectively assess ... with **completely independent observation records** ...

骨架：

```
Given that [现有做法的前提], the [常规评估/建模] is likely to [系统性偏差], because [为什么].
Consequently, [现有研究报告的指标] was always [被当作结论], which neglected [真正关心的东西].
Therefore, the goal of this study is to [换一个评价对象/基准].
```

### B. 评价维度不足型 —— 与本项目最相关

三篇 AE 论文用了同一招：**指出"现有评价维度"与"真正要回答的问题"不是一回事**。

WRF-CMAQ 动态评估（2017, *AE*）：

> There have been many studies focusing on the **operational evaluation** of regional air quality models, but **only few addressed the other three components** ... Recent studies ... **Hogrefe et al. (2008) stated that operational model evaluation provides little insight into the reliability of the estimation of relative changes** ... **Dynamic evaluation entails the assessment of the model's ability to reproduce the changes** in observed air quality conditions ... **Dynamic model evaluation for a 21-yr timeframe over CONUS has never been performed.**

Di 2024（见写法 A）说的是同一件事：**CV-R² 评的是逐点拟合，不是区域可迁移性**。

**骨架**

```
现有研究几乎都在 [维度 A] 上比较（refs），但 [维度 A] 提供不了关于 [真正问题] 的信息 (refs)。
[维度 B] 才是评估 [真正问题] 的方式，而 [维度 B] 在 [范围/尺度] 上尚未做过。
```

> **"has never been performed" 是 AE 里合法的强缺口表述**，前提是范围写得具体
> （"for a 21-yr timeframe over CONUS"），不能只写"尚无人研究"。

### C. 逐类局限型

每介绍一类方法，紧跟它的局限，段末用 **Consequently** 收尾。

原型（汾渭平原, 2026, *AE*）：

> **Although** photochemical indicators allow for rapid OPS identification, they simplify the nonlinear relationship ..., thereby amplifying uncertainties (Liu et al., 2022). The EBM approach requires ... and is constrained by ... (de Meij et al., 2024). **In contrast**, OBMs are associated by observational data ... **However**, since OBMs rely on historical observational data, they cannot predict future changes ... **Consequently, there is an urgent need to develop** rapid and accurate OPS identification methods ...

侧边界 2018 连用三次 "However" 做同一件事：

> ... CTM-derived LBCs are typically used ... **However**, they might contain large biases ... (P2)
> ... utilized satellite retrievals to enhance ... **However**, most satellite retrievals did not fulfill ... (P3)
> ... Bayesian modeling ... **However**, this approach requires a large number of observations ... (P4)

### D. 限制清单型 —— 最省力

在句内用 `1) 2) 3)` 列出现有研究的限制，然后接本文。

原型（Tang et al., 2024, *AE*）：

> **The limitations of previously published studies include: 1) focus on observation dense regions; 2) prediction of single species; and 3) neglect potentially useful CTM model products**, including long-term public reanalysis datasets. **The objective of this study is to** further advance the capabilities to fuse measurement and CTM models ... and test ML model dependency on observation density ...

骨架：

```
The limitations of previously published studies include: 1) …; 2) …; 3) ….
The objective of this study is to ….
```

## 关于「点名作者」——不是禁止，而是必须有判据

**实测**：紧凑型引言里几乎不点名；综述型引言里大量点名。

Tang 2024 的写法：

> Zheng et al. (2020) built a ML model in Beijing and tested the model in Shanghai, using a CNN and a RF ... Chen et al. (2021) used RF ML in the Yangtze River Delta ... Wei et al. (2020) found that adding spatiotemporal coordinates as predictors improved ... Di et al. (2016) used a CNN ...

北京 2021 的写法（点名 + 判据）：

> ... were only based on individual sites or applied with simple evaluation metrics (Cheng et al., 2019b; Chen et al., 2020; Li et al., 2020). **For example**, the records of an urban site in Beijing showed ... (Chen et al., 2020). **All of the previous studies** showed ozone increases in Beijing, **but they concealed the spatial difference** ... **None of them have** comprehensively estimated ...

**判据**：删掉这个作者名，这个论点还成立吗？

- 成立 → 改成成组引用。
- 不成立 → 可以点名，但必须写出"它证明了什么"。

## 关于数字

**实测**：紧凑型引言 0–2 个结果级数字；综述型可以有十几个。

**判据不是"数量"，而是"服务对象"**：

- 数字**支撑一个论点** → 可以留（"CAMS overestimated in urban areas" 这类对比）。
- 数字只是**罗列**（"A 报告 R²=0.85，B 报告 0.88，C 报告 0.90"）→ 删掉，改成"普遍报告较高"。

**背景级数字永远可以留**：法规阈值、年份、站点数、空间分辨率。

## 黄金结构

### 紧凑型（6 段）

| 段 | 任务 |
|:--:|---|
| 1 | 现象的重要性 + 一个关键现状事实 |
| 2 | 为什么难（机理 / 数据限制） |
| 3 | 已有做法，按类别推进 |
| 4 | 每类的局限 → Consequently |
| 5 | 缺口（A/B/C/D 之一） |
| 6 | 本文目标 + 路线（句内编号） |

### 综述型（9–13 段）

重要性 → 数据/方法背景 → 逐个方向铺开已有研究 → 限制清单 → 本文目标 → 章节组织。

## 八句可复制句式

1. **起手**（主语是现象，引用成组）
   > Ambient air pollution is among the leading overall risk factors for global mortality (Cohen et al., 2017; ...).

2. **收口句**——把宽背景收到研究对象
   > Such studies use estimates of air pollutant concentration fields in reaching their conclusions. *(Yu 2018)*

3. **方法列举**——方法名 + 括注一篇代表
   > These approaches include ordinary least squares, universal kriging (Cressie, 1993), statistical downscaling (Berrocal et al., 2010), and machine learning methods, including random forest (Hu et al., 2017) ... *(Berrocal 2020)*

4. **机制 → 后果 → 本文**（写法 A）
   > Given that ..., the assessment ... is likely to ... Consequently, ... was always reported ..., which neglected ... Therefore, the goal of this study is to ...

5. **维度不足**（写法 B）
   > ... operational model evaluation provides little insight into the reliability of the estimation of relative changes ... Dynamic evaluation ... has never been performed. *(WRF-CMAQ 2017)*

6. **逐类局限收尾**（写法 C）
   > Consequently, there is an urgent need to develop ... *(汾渭平原 2026)*

7. **限制清单**（写法 D）
   > The limitations of previously published studies include: 1) ...; 2) ...; 3) ....

8. **贡献开场**
   > Here we introduce ... *(Madden 2026)* ／ In this work, we investigate if ... *(Guillas 2008)*

## 改写流程（4 步）

1. **定中心**：用题目主语写一句「本文问的是 ______」。
2. **拆段**：给每段标一个"论点"；写不出论点的段落合并或重写。
3. **收引用**：`X 等发现 Y[n]` → `Y 已被反复报告[1,2,3]`；主语从作者换成现象。
4. **补缺口**：用 A/B/C/D 之一写出缺口，并检查它是否**可判定**（能说出"缺的具体是哪一环"）。

## 自检清单（12 条）

- [ ] 1. 每段第一句是**论断**，不是"某某研究了"？
- [ ] 2. 删掉所有作者名和年份，论证仍成立？
- [ ] 3. 引言的**中心对象** = 题目的**主语**？
- [ ] 4. 没有任何一段以"此外/首先/其次/最后"开头？
- [ ] 5. 每段至少一处引用？
- [ ] 6. 成组引用占 60% 以上（紧凑型要求；综述型放宽）？
- [ ] 7. 每个结果级数字都能说出"它在支撑哪个论点"？
- [ ] 8. 有一个明确写出的缺口句，用的是 A/B/C/D 之一？
- [ ] 9. 缺口之前有"每类方法的局限"作为铺垫？
- [ ] 10. 最后一段给出本文路线，用句内编号而非项目符号？
- [ ] 11. 段落数落在所选风格的区间（紧凑 4–8 / 综述 9–13）？
- [ ] 12. 没有超过 280 词的巨段（除非是综述型的背景段）？

## 两个常见误判

**「引用要具体」≠「把每篇的 R² 抄进引言」**
具体指的是**论点具体**，不是数字多。

**「不能笼统」≠「必须逐篇复述」**
紧凑型的做法是把文献归到类别里，一句话说清这一类的做法与局限。

## 参考

- `references/ae-corpus-analysis.md` —— 16 篇的实测数据、逐篇结构与原文摘录
- `references/before-after.md` —— 五组逐句改造对照
