---
name: ylx_research_evidence_synthesis
description: >-
  通用科研文献证据工程与Related Work写作工作流。适用于自然科学、工程、医学、计算机、管理学、社会科学等领域。
  当任务涉及研究问题拆解、系统检索、文献筛选、证据矩阵、反证与边界条件、研究缺口识别、文献综述/Related Work写作、引用核验时使用。
  核心原则是Claim-first而不是Paper-first：先定义论文需要证明的Claim，再检索、核验、映射证据，最后写作。
  默认正式交付仅保留两份文件：文献证据矩阵.xlsx 与 相关工作（文献综述）.md；其余均作为内部过程状态或合并进入这两份文件。
version: 2.1.0
---

# Research Related Work Evidence Synthesis Skill

## 1. Skill目标

把“查文献并写综述”转换为一个可复核、可迁移、可持续迭代的科研证据工程流程：

**研究问题 → Claim Inventory → 检索问题 → 候选文献 → 原始证据 → Claim–Evidence映射 → 证据缺口审计 → 定向补检 → 逻辑树 → Related Work写作 → 引用核验 → 两份正式交付物**

最终目的不是积累尽可能多的论文，而是确保论文中的重要判断都有明确证据、清晰边界和恰当表述强度，并让Research Gap从证据结构中自然产生。

## 1.1 默认交付契约（Delivery Contract）

除非用户明确要求额外过程文件，Skill完整执行后**只正式交付两份文件**：

1. `文献证据矩阵.xlsx`
   - 作为可追溯证据底座；
   - 保存文献书目信息、研究对象、Claim映射、原始证据、证据位置、证据类型、支持边界、反证/边界条件、核验状态与Coverage状态；
   - Claim Inventory、Search Log、Coverage Audit、Research Context等过程信息，优先作为该工作簿中的工作表保存，而不是额外生成独立文件。

2. `相关工作（文献综述）.md`
   - 作为正式写作产物；
   - 文件顶部必须包含最终逻辑树；
   - 逻辑树之后写正式Related Work / Literature Review正文；
   - Research Gap必须由证据矩阵中的真实覆盖缺口推出；
   - 引用核验在交付前内部完成，不默认另交付`citation_audit.md`。

过程文件默认属于**internal working state**，不是正式交付物。只有在用户明确要求审计轨迹、复现实验检索过程或团队协作时，才单独导出。

---

## 2. 适用范围

适用于：

- SCI/SSCI/EI论文的Introduction、Related Work、Literature Review、Discussion；
- 学位论文的文献综述与理论基础；
- 项目申请书、研究计划、开题报告中的国内外研究现状；
- 新研究方向的文献地图与证据矩阵；
- 方法比较、机制研究、系统综述前期探索；
- 判断某篇论文能否支持某个具体论断；
- 查找正效应、负效应、零效应、边界条件与失败模式；
- 对已有综述进行引用审计与Research Gap审计。

不适用于只要求生成参考文献格式、纯语言润色、或完全不要求证据支撑的写作。

---

## 3. 领域配置层

启动Skill时，先建立 `research_context.yaml` 或同等配置。至少填写：

```yaml
research_domain: "研究领域"
research_topic: "具体研究主题"
research_question: "核心研究问题"
study_object: "研究对象/数据/人群/系统"
key_factors:
  - "因素A"
  - "因素B"
methodology: "实验/调查/案例/建模/混合方法等"
target_sections:
  - "Introduction"
  - "Related Work"
preferred_literature_window: "例如 2019-2026"
preferred_source_types:
  - "peer-reviewed article"
  - "conference paper"
allowed_preprints: true
citation_style: "APA/IEEE/Vancouver/Elsevier等"
```

若用户未给出全部字段，可以从现有论文、研究计划或上传材料中提取；无法确定的字段标记 `unknown`，不得自行补造。

---

## 4. 核心术语

**Claim = 论文中需要由文献、数据或实验结果支撑的具体陈述。**

**Direct evidence = 文献直接研究当前Claim所对应对象、机制、变量关系或研究场景。**

**Indirect evidence = 文献未直接研究当前关系，但研究了高度相邻机制；可用于解释，不能冒充直接证据。**

**Conceptual evidence = 用于概念定义、理论框架、研究背景或术语边界的证据。**

**Methodological evidence = 用于支撑实验设计、统计方法、评价指标、测量工具或分析协议的证据。**

**Counterevidence = 与单向正面叙述不一致的证据，包括无效、负效应、条件性效果、失败模式和边界条件。**

**Tier 1 = 主论证链中的核心文献，正式写作前原则上必须回查全文。**

---

## 5. 总体执行原则

### Rule 1｜先Claim，后Paper

禁止把“某领域有哪些论文”作为最终综述结构。先定义本论文需要证明什么，再决定搜什么。

### Rule 2｜每篇核心文献必须记录支持边界

Tier 1文献至少记录：

- Can support current claim；
- Cannot support current claim；
- Evidence location；
- Abstract only / Full text checked；
- Verification status。

### Rule 3｜相关 ≠ 支持

主题相关、关键词相似、使用同一方法，不代表能支持当前句子。必须检查原文是否真正蕴含该Claim。

### Rule 4｜组合性能 ≠ 机制识别

如果论文比较多个配置、模块或策略，不能仅凭联合配置表现最好，就写成“存在协同机制”“因素A促进因素B”。

必须区分：

- configuration comparison；
- component contribution；
- mediation/moderation；
- formal interaction；
- causal mechanism。

### Rule 5｜主动寻找反证与边界

每个High-priority Claim至少主动检索一次：positive / null / negative / task-dependent / failure mode / boundary condition。

### Rule 6｜摘要用于筛选，核心结论优先全文核验

涉及精确数字、方法细节、因果解释、边界条件和作者结论时，应定位全文具体位置。

### Rule 7｜“没搜到”不等于“不存在”

Research Gap优先写成：

“在本研究检索范围内，现有工作主要集中于……，而对……的直接证据/系统比较/机制识别仍有限。”

避免无充分检索依据的“尚无研究”“首次提出”。

---

# 6. 标准工作流

## Stage 0｜冻结当前研究口径

建立 `current_research_facts.md`，至少回答：

1. 当前研究问题是什么；
2. 研究对象与场景是什么；
3. 核心变量/方法/机制是什么；
4. 当前结果或假设允许说什么；
5. 当前结果或假设不能说什么；
6. 每个目标章节承担什么论证功能。

研究问题或方法发生变化时，先更新这一层，再继续检索。

**内部状态：** 保存为工作记忆，或写入最终 `文献证据矩阵.xlsx` 的 `Research_Context` 工作表。默认不单独交付。

---

## Stage 1｜建立 Claim Inventory

将论文论证拆成约15–35个可管理Claim，每个Claim赋唯一编号。

建议字段：

| 字段 | 含义 |
|---|---|
| claim_id | C1、C2、M1、G1等 |
| module | 背景/机制/方法/评价/局限/Gap |
| claim_text | 需要证据支持的具体陈述 |
| manuscript_section | Introduction / Related Work / Methods / Discussion |
| importance | High / Medium / Low |
| evidence_needed | Direct / Methodological / Counterevidence等 |
| current_status | Adequate / P2 / P1 / P0 |

**质量门槛：** Claim必须具体到可以判断“支持 / 部分支持 / 不支持”。

**内部状态：** Claim Inventory优先写入最终 `文献证据矩阵.xlsx` 的 `Claim_Inventory` 工作表，不默认单独输出文件。

---

## Stage 2｜构建 Related Work 逻辑树 v0

逻辑树不是文献列表，而是论文论证路径。

通用主链：

```text
研究领域已有进展
    ↓
现有方法/理论解决了什么
    ↓
关键局限或未解决问题
    ↓
出现新的方法/机制/研究方向
    ↓
其边界条件与仍存不足
    ↓
现有联合/扩展研究做到什么程度
    ↓
尚未被直接识别的问题
    ↓
本文研究问题与设计
```

每节内部优先采用：

**已有进展 → 关键局限 → 边界/机制 → 引向下一节。**

**内部状态：** v0逻辑树用于指导检索和写作；最终版本必须嵌入 `相关工作（文献综述）.md` 顶部，不默认单独输出 `related_work_logic_tree.md`。

---

## Stage 3｜为每个Claim设计检索式

每个High-priority Claim至少设计以下查询中的3类：

### 3.1 Precision query

直接命中对象 + 机制 + 关系。

模板：

`[研究对象] + [方法/变量] + [目标关系] + [场景]`

### 3.2 Recall query

仅保留1–3个高辨识度术语，提高召回。

模板：

`[核心方法] + [failure / effect / review]`

### 3.3 Counterevidence query

模板：

`[方法] + negative effect / null effect / failure / limitation / boundary condition`

### 3.4 Neighbor-mechanism query

当直接文献较少时检索相邻机制；进入矩阵后必须标记为Indirect。

### 3.5 Methodology query

统计、实验设计、量表、评价协议单独检索，不用应用论文替代方法学依据。

### 3.6 Foundational query

用于查找概念起源、经典理论、方法首篇或权威定义。

**推荐顺序：** Direct → Same mechanism → Neighbor domain → Review/Methods → Preprint for emerging topics。

---

## Stage 4｜候选文献筛选与书目信息核验

每篇候选文献回答：

1. Research Task是什么？
2. Research Object与当前研究是否一致？
3. 它研究的是同一机制、相邻机制还是仅主题相关？
4. 能映射哪些Claim？
5. 是否值得进入Tier 1？

核验：Title、Authors、Year、Venue、DOI/URL、出版状态、同行评议状态。

未核验时：`verification_status = pending`。

检索记录可暂存于内部Search Log；若需要保留复现轨迹，最终写入 `文献证据矩阵.xlsx` 的 `Search_Log` 工作表。

---

## Stage 5｜提取Claim级证据

最小证据单元：

```text
claim_id
paper_id
paper_title
evidence_text
evidence_location
evidence_type = Direct | Indirect | Conceptual | Methodological | Contradictory
confidence = High | Medium | Low
mapping_reason
abstract_only = Yes | No
```

`evidence_text`优先记录作者实际报告的结果或结论，避免改写成对自己论文更有利的版本。

`evidence_location`尽量具体到：Abstract / Section / Table / Figure / Page。

---

## Stage 6｜建立正式交付物①：文献证据矩阵.xlsx

推荐字段：

### A. Bibliographic

`Paper_ID, Title, Authors, Year, Journal/Venue, DOI/URL, publication_status, verification_status`

### B. Research characterization

`Research_domain, Research_object, Research_task, Theory/Method, Data, Sample, Evaluation, Main_result`

### C. Evidence characterization

`Mapped_claims, Evidence_type, Evidence_strength, Counterevidence, Boundary_condition, Task_dependency`

### D. Mechanism / design audit

按研究类型选择字段，例如：

`Causal_identification, Formal_interaction_test, Mediation_test, Moderation_test, Factorial_design, Ablation, Longitudinal_design, Control_group`

### E. Current-paper mapping

`Current_Tier, Primary_role, Secondary_roles, High_priority_claims, Current_use_note`

### F. Overclaim guardrail

`Can_support_current_claim, Cannot_support_current_claim, Needs_fulltext_check`

**硬规则：** Tier 1的 `Cannot_support_current_claim` 不得为空。

### 6.1 工作簿组织

默认至少包含以下工作表：

- `Literature_Evidence`：核心文献—Claim—证据映射主表；
- `Claim_Inventory`：论文需要证明的Claim及其优先级；
- `Claim_Coverage`：每个Claim的Direct/Indirect证据数量、反证与Adequate/P2/P1/P0状态；
- `Search_Log`：检索数据库/平台、检索式、日期、筛选结果与补检原因；
- `Research_Context`：研究问题、研究对象、方法、当前口径与不能过度声称的内容。

允许根据项目复杂度合并工作表，但不能丢失可追溯信息。

### 6.2 主表最低字段

`Paper_ID, Title, Authors, Year, Journal/Venue, DOI/URL, Research_task, Research_object, Method, Main_result, Mapped_claims, Evidence_text, Evidence_location, Evidence_type, Evidence_strength, Counterevidence, Boundary_condition, Can_support_current_claim, Cannot_support_current_claim, Verification_status, Current_Tier, Current_use_note`

`文献证据矩阵.xlsx`不是简单参考文献清单，而是后续写作和引用审计的唯一证据底座。

---

## Stage 7｜执行 Claim Coverage Audit

对每个Claim统计：

- mapped papers；
- Direct / Indirect / Methodological数量；
- 是否有高置信证据；
- 是否存在反证或边界；
- 是否仍为abstract-only；
- 当前Evidence Status。

建议状态：

- `Adequate`：足够支撑正式写作；
- `P2`：可补强但不影响主线；
- `P1`：证据偏弱，需要定向补检；
- `P0`：核心证据缺口，优先处理。

下一轮检索只围绕P0/P1，避免无限扩大文献池。

Audit结果回写 `文献证据矩阵.xlsx` 的 `Claim_Coverage` 工作表，不默认额外生成Coverage文件。

---

## Stage 8｜建立 Counterevidence / Boundary 视图

单独整理：

- 正向结果；
- 零效应；
- 负效应；
- 条件性结果；
- 不同任务/样本/场景下的异质性；
- 失败模式；
- 作者明确提出的限制。

用途不是“强行平衡”，而是帮助解释为什么研究结果可能随任务、样本、方法配置或边界条件变化。

该视图可作为 `Literature_Evidence` 的字段/筛选视图或独立工作表保存，但仍属于同一个 `文献证据矩阵.xlsx`。

---

## Stage 9｜根据证据更新逻辑树 vFinal，并嵌入正式综述文件

每个叶节点都应对应：

`Claim → 1–3篇核心证据 → 该节点要推出的下一步`

若节点无合格证据：

- 删除；
- 降低表述强度；
- 改写为待验证问题；
- 或进入Research Gap。

不得依赖常识强行补齐论证链。

vFinal逻辑树必须成为 `相关工作（文献综述）.md` 的第一部分。

---

## Stage 10｜建立正式交付物②：相关工作（文献综述）.md

### 10.0 文件结构

默认结构：

```text
# 相关工作（文献综述）

## 逻辑树
[基于最终证据形成的vFinal逻辑树]

## 2.1 / 第一主题模块
[正式正文]

## 2.2 / 第二主题模块
[正式正文]
...

## Research Gap / 研究缺口
[由证据覆盖缺口自然推出研究问题、研究设计或研究贡献]
```

章节编号、语言和标题随用户论文结构调整，但“逻辑树 + 正式正文”必须在同一份Markdown中完成。

### 10.1 以Claim为段落单位，不以Paper为段落单位

避免“作者A做了……作者B做了……作者C做了……”。

优先写成：

“现有研究表明X。A从……提供直接证据，B进一步显示……。然而，在Y条件下该作用并不稳定，C观察到……。因此，现有研究已经解决……，但仍未解释/识别……。”

### 10.2 每段四步

```text
本段主判断
    ↓
代表性直接证据
    ↓
边界/反证/机制限制
    ↓
引向下一段、下一节或Research Gap
```

### 10.3 每节只完成一个推进

每一节结束必须回答：

“为什么下一节有必要存在？”

### 10.4 Research Gap写法

优先采用：

**已有进展 → 明确让步 → 尚未识别的关系/机制/边界 → 本文研究设计。**

不得通过贬低已有研究来制造创新性。

---

# 7. 引用核验协议

对每个含引用的核心句子检查：

1. **Entailment**：原文是否真正支持该句；
2. **Scope**：是否扩大了研究对象、场景或人群；
3. **Causality**：相关性是否被写成因果；
4. **Strength**：suggest/associate是否被升级成prove/demonstrate；
5. **Method**：配置比较是否被写成机制识别；
6. **Numerical detail**：数字是否来自正确版本；
7. **Citation role**：Direct还是Indirect；
8. **Full text**：Tier 1是否全文核验。

失败时执行：降低表述强度 / 替换文献 / 删除Claim。

Citation Audit默认是交付前的内部质检步骤；发现问题后直接修正两份正式产物，不默认生成第三份审计文件。

---

# 8. 搜索停止条件

当前检索轮次可以结束，当且仅当：

- 所有High-priority Claim不再处于P0；
- 每个核心段落至少有1篇Direct/Tier 1锚点；
- 关键机制至少存在1条边界或反证；
- Tier 1中的精确实证判断已完成全文核验；
- Research Gap有检索记录支持，而非凭印象；
- 正文不存在明显超出 `Can_support_current_claim` 的陈述；
- 逻辑树能自然推出本文研究问题与设计。

停止依据是**证据覆盖度**，不是固定论文篇数。

---

# 9. 正式交付规范

完整执行后的默认交付只有两项：

| 正式产物 | 作用 | 必须包含 |
|---|---|---|
| `文献证据矩阵.xlsx` | 可追溯证据底座 | 文献元数据、Claim映射、原始证据、证据位置、支持/不支持边界、反证/边界条件、核验状态、Coverage状态 |
| `相关工作（文献综述）.md` | 可直接进入论文的写作成果 | vFinal逻辑树、按Claim组织的正式正文、由证据缺口推出的Research Gap |

### 9.1 过程信息如何处理

以下内容默认**不作为第三、第四个独立文件交付**：

- current research facts；
- Claim Inventory；
- literature search log；
- Claim Coverage Audit；
- Counterevidence view；
- citation audit。

其中可结构化保存的信息优先进入 `文献证据矩阵.xlsx` 的不同工作表；纯质检信息在内部执行后直接反映到最终两份文件。

### 9.2 只有三种情况允许额外交付过程文件

1. 用户明确要求保留检索/审计轨迹；
2. 团队协作需要人工复核或继续接力；
3. 系统/系统综述要求可复现检索协议。

否则不得用大量中间文件增加交付负担。

### 9.3 最终一致性要求

两份产物必须一一对应：

`综述中的关键Claim → 文献证据矩阵中的Mapped_claims → Evidence_text / Evidence_location → Can_support / Cannot_support`

若正文出现无法在矩阵中追溯的核心Claim，应补证据、降低表述强度或删除该Claim后再交付。

---

# 10. 失败模式与修复

### Failure A｜搜了很多论文但写不出来

根因：Paper-first。

修复：回到Claim Inventory，只保留能映射到当前Claim的论文。

### Failure B｜引用很多，但一句话没有直接证据

根因：把主题相关当成句子支持。

修复：建立Claim–Evidence映射，强制填写evidence_text与evidence_location。

### Failure C｜为了强调创新而弱化已有研究

根因：把“不是完全相同的方法”写成“没人研究过”。

修复：区分Direct precedent、Neighbor mechanism、Configuration comparison、Formal mechanism identification。

### Failure D｜只找支持自己的论文

根因：确认偏误。

修复：每个High-priority Claim强制执行Counterevidence query。

### Failure E｜摘要直接承担精确结论

根因：证据层级失控。

修复：Tier 1全文核验；未核验时降低陈述强度。

### Failure F｜综述变成百科或作者名单

根因：章节没有论证推进功能。

修复：每段围绕一个Claim，每节最后推出下一节。

### Failure G｜Research Gap先写好，再反向找文献

根因：创新叙述驱动证据选择。

修复：先做Claim Coverage Audit，再根据真实缺口生成Gap。

---

# 11. 最终自检

提交前回答：

- 我是在围绕Claim写，还是围绕作者名单写？
- 每个High-priority Claim有哪些Direct证据？
- 是否记录了每篇核心文献“不能支持什么”？
- 是否主动保留了零效应、负效应和边界条件？
- 是否把相关性、配置优势或消融结果误写成因果机制？
- 是否存在只看摘要却写了精确数字或强因果结论？
- Research Gap是否来自证据矩阵，而不是主观判断？
- 各节是否形成连续推进？
- 最后一节是否自然推出本文研究问题与研究设计？
- 最终是否只需要交付 `文献证据矩阵.xlsx` 和 `相关工作（文献综述）.md`？
- 正文每个核心Claim能否回溯到证据矩阵中的具体证据位置与支持边界？

全部通过后，Skill终止并交付两份正式产物。
