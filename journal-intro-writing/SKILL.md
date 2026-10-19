---
name: journal-intro-writing
description: 按 Elsevier 环境类期刊（Atmospheric Environment 实测 19 篇、精读 5 篇）的真实论文范式写 Introduction / 研究背景。核心判据是「引言讲一个领域，不是给文献写摘要」：按知识点分段、引用成组挂句尾、不逐篇复述结果、中心议题与题目主语对齐。当用户要写论文引言/研究背景、抱怨「写得像综述」「像报告」「很怪」「抓不到重点」，或要把文献笔记改写成论文体时使用。
---

# 期刊 Introduction / 研究背景写作范式（AE 实测）

## 核心判据

**引言讲一个领域，不是给文献写摘要。**

一个可操作的检验：

> **把所有作者名和年份删掉，论证还成立吗？**
> 成立 → 你在讲领域，合格。
> 不成立 → 你在写 annotated bibliography，不合格。

第二条判据：

> **引言的中心对象，必须等于题目的主语。**
> 题目讲「X 如何影响 Y」，引言就该围绕 X；如果前三分之一在讲 Y 的一般背景，读者会不知道你要问什么。

## 四种典型病征

| 病征 | 表现 | 为什么致命 |
|---|---|---|
| **按文献分段** | 一段一个作者，一段一项研究 | 段落之间没有论证关系，只有并列关系 |
| **复述单篇结果** | "X 等得到 R²=0.65、RMSE=7.06" | 引言变成结果汇编；读者记不住，也看不出你要做什么 |
| **引用单挂** | 每句末尾一个 [n]，且句子主语是作者名 | 阅读时被迫中断去识别文献，而不是跟着论证走 |
| **中心偏移** | 题目讲 A，背景前 1/3 在讲 B | 最隐蔽，也最致命——整篇读下来"很全"，但不知道在问什么 |

## 实测语料

库内 19 篇 *Atmospheric Environment*，精读 5 篇（详见 `references/ae-corpus-analysis.md`）：

| 论文 | 类型 | 段落数 | 总词数 | 关键特征 |
|---|---|:--:|:--:|---|
| Yu et al. 2018, AE 179:49–60 | 方法横向比较 | 5 | ~515 | **全篇零具体数值** |
| Berrocal et al. 2020, AE 222:117130 | 跨范式比较 | 5 | ~495 | **全篇无"X 等发现"句式** |
| Mousavinezhad et al. 2023, AE 300:119693 | 趋势 + 健康 | 8 | ~1,500 | 前 4 段是化学机理陈述，引用成组 |
| Hojeily et al. 2026, AE 371:121805 | 城市尺度融合 | 8–9 | ~1,300 | 需求→监测不足→再分析→本文 |
| CAMS vs CMAQ 2024 | 产品比较 | 7–8 | ~1,100 | 两产品差异→评价缺口 |

## 硬指标（实测范围 / 建议值）

| 指标 | 实测范围 | 建议 |
|---|---|---|
| 段落数 | 4–8 | **5–7** |
| 总词数 | 450–1,500 | **600–900** |
| 每段词数 | 50–265 | **100–220** |
| 平均句长 | 25–32 词 | **26–30 词** |
| 引用形式 | 成组 `(A; B; C)` 挂句尾 | **成组占 ≥60%** |
| 每段引用 | 1–8 处 | **≥1** |
| 项目符号 | 0 | **0** |
| 单篇结果数字 | 0–2（仅背景级） | **≤2** |

> 「背景级数字」= 法规阈值、量级、年份。如 NAAQS 从 120→84→75→70 ppb。
> 「结果级数字」= 某论文的 R²、RMSE、误差、回归系数。**这类不要进引言。**

## 黄金五段

| 段 | 任务 | 该段结束时读者应该知道 |
|:--:|---|---|
| 1 | 危害 / 需求 → 用一句话收到"本研究依赖的那个对象" | 为什么这件事值得做，以及它依赖什么 |
| 2 | 已有做法，**按类别**推进（不按作者） | 领域里有几类解法，各自能干什么 |
| 3 | **缺口**：主张 → examples → 反例 → 原因 → 具体缺口 | 为什么现有工作还不够 |
| 4 | 本文目标（一句 "Our objective is to …"） | 本文要做什么 |
| 5 | 贡献 / 路线（句内编号） | 本文怎么做、凭什么可信 |

段数按内容伸缩到 7–8 段正常，但**段落始终是"论点的递进"，不是"文献的并列"**。

## 五种可直接套用的句式

### 1. 起手 + 并列引用

> Ambient air pollution is among the leading overall risk factors for global mortality (Cohen et al., 2017; Landrigan et al., 2018; Murray et al., 2020).

主语是**现象**，不是作者。引用三到五篇并列挂在括号里。

### 2. 收口句——把宽背景收到研究对象

Yu 2018 第一段讲完健康危害后，只用一句话把话题收到浓度场上：

> Such studies use estimates of air pollutant concentration fields in reaching their conclusions.

这一句是整篇引言的**枢纽**：它决定了后面所有内容围绕"浓度场"展开。写引言时先找到这一句。

### 3. 缺口句——直接点破

Berrocal 2020：

> This paper aims to address an important gap in the current literature: the fact that, when models to estimate ambient air pollution exposure are being developed, they are typically only compared to simpler models **within the same modeling paradigms**. Examples include comparisons between … (refs); between … (refs); or between … (refs). There has been **very limited cross-paradigm comparisons** (refs), likely due to … In particular, **there is a lack of** …

结构：**主张 → 三个 examples（各带一组引用）→ 反例 → 原因 → 具体缺口**。
五步一句话走完，没有一句是在复述某篇文献的结果。

### 4. 方法列举句——方法名 + 括注一篇代表

> These approaches include ordinary least squares, universal kriging (Cressie, 1993), statistical downscaling (Berrocal et al., 2010), and machine learning methods, including random forest (Hu et al., 2017), support vector machine (Liu et al., 2017), and neural networks (Di et al., 2016).

一个从句带过六种方法。**不解释每种方法怎么做**——那是 Methods 的事。

### 5. 路线句——句内编号

> Comparisons were focused on four aspects: 1) spatial concentration fields; 2) Temporal correlations and statistical performance; 3) Auto-correlations of estimated concentrations and method errors; 4) Interspecies correlations.

注意：**这是句内编号，不是项目符号列表**。AE 允许用 `1) 2) 3)` 串在句子里，不允许换行成 bullet。

## 改写流程（4 步）

### Step 1 定中心

用题目的主语写一句话：

> 本文问的是：__________。

如果这句话读起来像"本文介绍美国臭氧"，说明题目没吃透，先回去看标题。

### Step 2 拆段

把现有草稿的每一段标上"这段的论点是什么"。
- 如果写不出来（只能写出"这段介绍了某某等的研究"）→ 这段该合并或重写。
- 重排成论点递进：需求 → 做法 → 缺口 → 目标 → 路线。

### Step 3 收引用

把 `X 等发现 Y[n]` 改成 `Y 这一现象已被反复报告[1,2,3]`。
- 主语从**作者**换成**现象/方法/结论**。
- 相邻引用合并成一组。

### Step 4 删数字

保留 ≤2 个背景级数字（阈值、量级、年份），其余全部移到 Results / Discussion。
**引言里出现"某文 R²=0.9"，就是写错了地方。**

## 自检清单（10 条，逐条可判定）

- [ ] 1. 每段第一句是一个**论断**，不是"某某研究了"？
- [ ] 2. 删掉所有作者名和年份，论证仍然成立？
- [ ] 3. 没有任何一段以"此外 / 首先 / 其次 / 最后"开头？
- [ ] 4. 每段至少一处引用？
- [ ] 5. 成组引用（≥2 篇并列）占全部引用的 60% 以上？
- [ ] 6. 单篇文献的具体结果数字 ≤2 个？
- [ ] 7. 有一个明确的"缺口段"，且写清了"为什么现有工作不够"？
- [ ] 8. 最后一段给出本文路线，用句内编号而非项目符号？
- [ ] 9. 引言的**中心对象**与题目的**主语**一致？
- [ ] 10. 段落 5–7 段、总词数 600–900？

## 两个常见误判

**「引用要具体」≠「把每篇的 R² 抄进引言」**
具体指的是**论点具体**（"这类方法在留出检验下抓不住空间梯度"），不是**数字多**。

**「不能笼统」≠「必须逐篇复述」**
AE 的做法是把文献归到类别里，用一句话说清这一类的做法与局限，再在括号里给三五个代表。读者要的是"这个领域长什么样"，不是"每篇论文做了什么"。

## 参考

- `references/ae-corpus-analysis.md` —— 5 篇论文的实测数据与原文摘录
- `references/before-after.md` —— 文献摘要式 vs AE 式的逐句对照改造
