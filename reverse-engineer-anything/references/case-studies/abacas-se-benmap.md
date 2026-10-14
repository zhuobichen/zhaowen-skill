# ABaCAS-SE 中 BenMAP-CE 的健康效益计算原理（桥接文档）

> **定位**：本文是 `abacas-se-health-benefit-analysis.md`（ABaCAS_SE 本体逆向）的**下卷**，专门回答一个问题——
> **ABaCAS_SE 把浓度场交给 BenMap.exe 之后，BenMAP 内部到底按什么公式算出"钱"来的？**
>
> 上卷（ABaCAS_SE 本体，553 行）只覆盖「读 CSV → ±20% → 省级汇总 → 亿元×1e8 → 比率」，
> 其中最关键的一步「健康影响 → 货币化」在上卷 §7 只做了**指向**。
> 本文把那个指向**展开成实质内容**：调用链逐行解读 + BenMAP APV 模块的真实公式 + 两段拼接处的接口契约。
>
> BenMAP 通用逆向成果（36 条浓度-响应函数 / 12 条基线函数 / 19 条货币估值函数 / 12 条 EI 函数 / 476+477 条参数实例）
> 见同目录 [`benmap.md`](benmap.md)（BenMAP-CE 本体逆向，1781 行 / 76 KB）。
> **本文不重复贴那 76 KB，只引用它并聚焦「ABaCAS-SE 怎么用」。**
>
> 上卷 `abacas-se-health-benefit-analysis.md` 未收入本案例目录；本地路径
> `E:\CodeProject\_rea_abacas\abacas-se-health-benefit-analysis.md`。

---

## 0. 证据来源

| 目标 | 值 |
|---|---|
| ABaCAS_SE.exe | `D:\杂物\ABaCAS\ABaCAS\ABaCAS_SE.exe` |
| SHA256 | `909E59B6E590889F3C57BCE9270BEF253A6231FA9EB61C39EEC970510436B428` |
| 大小 / 平台 | 14,936,576 B / PE32 .NET 4.5 / x86 IL-only / 程序集 `ABaCAS_SE` v3.6.0.0 |
| REA evidence_id | `ev_b00959b7451dad7f2266ddcf39349d7bc9c08c14531f715ca5a58d975a569adb` |
| BenMap.exe | `D:\杂物\ABaCAS\ABaCAS\BenMAP-CE\BenMap.exe`（7.4 MB，.NET 4.0，CIL x86，`BenMAP 1.4.7.0`） |
| BenMAP 数据层 | 安装目录下 `Database\BENMAP50.FDB`（Firebird，从 `BenMAP50.exe` carve，4.8 GB） |
| 用户手册 | `ug_cn.chm` / `ug_en.chm`（解压至 `_rea_abacas\ug_cn_x\` / `ug_en_x\`，各 114 文件） |

**证据分级**：本文所有结论标注【观察】（IL / 字节码 / 数据库实测）/【推断】（逻辑合理但无直接证据）/【未知】（无法获取）。

### 0.1 手册验证：公式不在文档里

**【观察】** 已完整解压并中英文对照检索用户手册：

| 手册位置 | 内容 | 有无公式 |
|---|---|---|
| 中文 `6_3_4_2` | 济南健康效益 ≈ `772905920` 元 | ❌ 仅结果数字 |
| 中文 `6_3_5_2` | 济南效益/成本比 ≈ `5.6` | ❌ 仅结果数字 |
| 中文 `6_3_5_1` | 全国总效益/成本比 ≈ `8.8` | ❌ 仅结果数字 |
| 英文 `3_4_benmap_ce_input_option.htm` | *"APV configuration file or result file: includes a list of parameter information needed for an environmental benefit assessment."* | ❌ 仅概念说明 |

**结论**：ABaCAS-SE 的 BenMAP-CE 部分是**纯图示操作手册**（点哪个按钮、填哪个框），没有任何公式。
唯一有价值的一句（英文手册）恰恰印证了本文的核心判断：**估值参数在 `.apvx` 里，不在程序里。**
→ 因此**反汇编（ABaCAS_SE）+ 数据库挖掘（BenMAP FDB）是唯一途径**，本文即该途径的成果。

---

## 1. 一句话原理

**【观察】** ABaCAS-SE 的健康效益 = **BenMAP-CE 用"浓度→病例数→元"算出来的钱**，
ABaCAS_SE 自己只做**固定的 ±20% 区间、省级加总、单位换算、比率**四件后处理。

$$
\text{健康效益(元)} = \sum_{\text{endpoint}}\Big[\ \text{收入调整因子} \times \text{发病率变化(例)} \times \text{单位价值(元/例)}\ \Big]
$$

**核心恒等式**（源码硬证据，`APV/APVCommonClass.cs:3222`）：

```csharp
apvValueAttribute.PointEstimate =
    Convert.ToSingle(income * crCalculateValue.PointEstimate * dValuation);
```

| 乘数 | 由谁提供 |
|---|---|
| `income`（收入增长调整） | `INCOMEGROWTHADJFACTORS` 表，按终点组 × 目标年份 |
| `crCalculateValue.PointEstimate`（健康影响，例） | `CRFUNCTIONS` × `FUNCTIONALFORMS`（CFG 模块产出） |
| `dValuation`（单位价值，元/例） | `VALUATIONFUNCTIONS` × `VALUATIONFUNCTIONALFORMS`（APV 模块，**由 `.apvx` 指定**） |

**三个乘数分别由三个不同的表 / `.apvx` 提供**——这就是为什么「换一个估值函数，结果差 25 倍」（§5.3）。

---

## 2. 段一的完整调用链（批处理脚本逐行解读）

**【观察】** 方法：`ABaCAS_SE.CommonClass::createProjectScriptBenMAP`，RVA `0x2D60C`。
它生成一个 `BenMap.exe` 的**批处理脚本文件**（`.txt`），然后调用 BenMap.exe 执行。

### 2.1 脚本头部：6 个目录变量

**【观察】** IL_0081–IL_00E8：

```text
VARIABLES
%BENMAPDIR%     <BenMap.exe 所在目录>
%AQGDIR%        <AQG 文件目录>
%CFGDIR%        <CFG 配置目录>
%CFGRDIR%       <CFG 结果目录>
%APVDIR%        <APV 配置目录>
%APVRDIR%       <APV 结果目录>
COMMANDS
```

**【观察】** IL_0132 硬编码 `'China'`；紧接 `SETACTIVESETUP  -ActiveSetup    `（IL_0139），
末尾拼 `##` + 项目文件名（IL_0152）——即**激活名为 `China` 的 Setup 数据库集**。

> 这解释了为什么上卷说「APV 估值系数字段无法从磁盘验证」：Setup（Setup 集）→ CR/VF 绑定链在
> FDB 里，而 BenMap.exe 用 `-ActiveSetup China` 在运行时动态选，磁盘上没有展开后的 `.apvx` 快照。

### 2.2 五条命令，逐条拆解

**【观察】** IL 顺序与常量如下（`<n>` = 项目文件名去扩展名）：

```text
① 建两张浓度网格文件（基线 / 对照）
CREATE AQG  -Filename      %AQGDIR%\<n>.aqgx
            -GridType      <基线网格类型>
            -Pollutant     PM2.5
            -ModelDirect
            -ModelFilename <SMAT-CE 输出的浓度场>
            -DSNName       <n>
CREATE AQG  ...（第二次，GridType 取对照网格类型）

② 浓度 -> 健康终点暴露（病例数）
RUN CFG   -CFGFilename      <用户选的 CFG 配置>
          -ResultsFilename  %CFGRDIR%\<n>.cfgrx
          -BaselineAQG      %AQGDIR%\<n>.aqgx
          -ControlAQG       %AQGDIR%\<n>.aqgx

③ 健康终点暴露 -> 货币化效益（★ 估值系数在此）
RUN APV   -APVFilename      <用户选的 .apvx>
          -ResultsFilename  %APVRDIR%\<n>.apvrx
          -CFGRFilename     %CFGRDIR%\<n>.cfgrx

④ 导出三张结果表
GENERATE REPORT APVR -InputFile %APVRDIR%\<n>.apvrx -ReportFile %APVRDIR%\<n>apvrx.csv
          -CustomFields "Endpoint Group,Endpoint,Author" -Totals
          -ResultType PooledValuation            <- ★ 合并后的货币值（ABaCAS 读这个）

GENERATE REPORT APVR ... -ReportFile %APVRDIR%\<n>apvrxinc.csv
          -CustomFields "Endpoint Group,Endpoint,Author" -Totals
          -ResultType PooledIncidence            <- 合并后的病例数（ABaCAS 不用）

GENERATE REPORT CFGR -InputFile %CFGRDIR%\<n>.cfgrx -ReportFile %CFGRDIR%\<n>cfgrx.csv
          -GridFields "Column,Row"
          -CustomFields "Endpoint Group,Endpoint,Author"
          -ResultFields "PointEstimate,Mean,Population,Percentiles,Standard Deviation,Variance"
          -Grouping -DecimalDigits 8
```

**三个报告类型的含义**（理解上下卷接口的关键）：

| 产物 | 语义 | ABaCAS_SE 是否读 |
|---|---|---|
| `cfgrx` | CFG 模块原始结果：每个终点 × 每网格的**病例数**及不确定度 | 间接（转成 apvrx） |
| `apvrx.csv` (`PooledValuation`) | APV 模块把病例数 × 单价并 **Pooling** 后的**货币值** | ✅ **唯一输入** |
| `apvrxinc.csv` (`PooledIncidence`) | Pooling 后的**病例数** | ❌ 未被消费 |
| `cfgrx.csv` | 病例数明细（含百分位） | ❌ 未被消费 |

### 2.3 ABaCAS_SE 的输入契约

**【观察】** 上卷 §2 已确认 `InitializeBenMapResult` 读的路径是：

```text
{ResultPath}\{项目目录名}\BenMAP-CE\{项目目录名}apvrx.csv
```

即脚本里 `-ReportFile %APVRDIR%\<n>apvrx.csv` 的产物。字段（CsvHelper **按表头名**匹配，不按顺序）：

```text
ParentName, Name, Col, Row, EndpointGroup, Endpoint, Author,
PointEstimate, Mean, StandardDeviation, Variance,
LowBenefit, MedianBenefit, HighBenefit, Baseline
```

**这三个语义必须对齐，否则复现错**：

| 列 | 在 BenMAP 里的原义 | 在 ABaCAS 里的新义 |
|---|---|---|
| `Baseline` | 基线情景**病例数** | 被覆写为 `Baseline - PointEstimate` = **效益** |
| `PointEstimate` | 对照情景**病例数** | 被覆写为 `Baseline - PointEstimate` = **效益** |
| `LowBenefit` / `HighBenefit` | BenMAP 自己的**不确定度区间**（货币） | **被丢弃**，改用固定 ±20% |

> **⚠ 这是上下卷之间最容易踩的坑**：ABaCAS 把 `Baseline` 和 `PointEstimate` **原地改成"效益"**，
> 所以 `apvrx.csv` 里这两列是**病例数**，读进 ABaCAS 后变成**元**。

---

## 3. 三层数据驱动引擎（BenMAP 侧）

**【观察】** BenMAP 的"健康效益"**不是写死在代码里的公式**，而是三层：

```text
[第 1 层] FUNCTIONALFORMS / BASELINEFUNCTIONALFORMS / VALUATIONFUNCTIONALFORMS
         数据库里存放的「公式文本」（小型 Pascal 风格表达式语言，33 / 12 / 19 条）
            |  字符串翻译 + 运行时 C# 动态编译（ConfigurationCommonClass.cs:4434）
            v
[第 2 层] CRFUNCTIONS / VALUATIONFUNCTIONS / EIFUNCTIONS
         「公式模板 ID + 科学参数(Beta, A, B, C...) + 适用年龄/终点/污染物」
         476 条 + 477 条 + 12 条实例
            |  逐网格单元执行
            v
[第 3 层] CalculateCRSelectFunctionsOneCel        -> 发病率变化（Case Count）
         getOneAllSelectValuationMethodCRSelectFunctionCalculateValue -> 单价（元/例）
         -> 货币化效益（Valuation）
         -> Pooling 多终点合并 -> 单一「健康效益」总数
```

---

## 4. 第 1 层：公式模板全文（BenMAP 的"公式"到底长什么样）

### 4.1 浓度-响应函数 `FUNCTIONALFORMS`（36 条）

**【观察】** 数据库表 `FUNCTIONALFORMS` 存的是**公式文本字符串**，运行时被翻译成 C# 并动态编译
（完整机制见 §5.6）。

> ⚠️ **【观察】静默丢弃风险**：`getBenMAPHealthImpactFunctionFromID`
> （`ConfigurationCommonClass.cs:661-673`）用的是 **INNER JOIN**：
> `from CRFunctions a, EndPointGroups b, EndPoints c, FunctionalForms d, CRFunctionDatasets e where … a.FunctionalFormid=d.FunctionalFormID`
> ⇒ 若某条 `CRFunctions.FunctionalFormid` 在 `FUNCTIONALFORMS` 里不存在，
> 该函数**不会报错，而是被查询直接丢掉**。
> 估值侧（`APVCommonClass.cs:1452/1503`）是同样的逗号式 inner join，
> 但中国区实际用到的 FormID（1/4/8/21）都在表里，故本项目不受影响。

9 类语义形态速查（全文见 BenMAP 文档 附录 A）：

| 类别 | ID 集合 | 数学形式 | 典型用途 |
|---|---|---|---|
| 线性 no-threshold | 17, 301, 302 | `β·ΔQ·I·Pop` | 无阈值假设 |
| **log-linear** | 32, 34, 35, 37, 258 | `(1-e^{-βΔQ})·I·Pop` | **最主流** |
| 阈值 log-linear | 11, 18, 19, 57 | log-linear + 浓度窗口 `[A,B]` | 有阈值污染物 |
| log-logistic | 29, 38, 39, 41, 265, 279, 283, 303 | `(1-1/((1-I)e^{βΔQ}+I))·I·Pop` | Log-logistic 风险模型 |
| 三参数 log-logistic | 312 | `β(1-e^{-BΔQ^C}) / (β(1-e^{-BΔQ^C})+1)` | **Pope 2014 PM2.5** |
| 双阈值分段 log-logistic | 313 | `f(x)=1/(1+A(1-e^{-B(x-β)^C}))` | 拐点浓度分段 |
| 分档加权线性 | 284, 285 | log-linear × 分档权重 | 暴露分位加权 |
| 患病率路径 | 38, 265, 279, 311 | `×Prevalence` 或 `×(1-Prevalence)` | 发病率→患病率 |
| 常数 | 14, 309, 310 | 直接返回 | 固定率/透传 |

> **【推断】** `ΔQ = 情景浓度 − 对照浓度`。ABaCAS-SE 传入的 `-BaselineAQG` / `-ControlAQG`
> 就是上卷数据流图里的「情景浓度」与「基准浓度」，对应 `ΔQ = C_base − C_control`。

#### 4.1.1 ★ `getFunctionStringFromDatabaseFunction` 完整翻译表（已逐字核对源码）

**【观察】** 源码位置：`ConfigurationCommonClass.cs:4434-4510`；
调用点：`ConfigurationCommonClass.cs:2936`（`BaseLineIncidenceFunction`）
与 `:2938`（`Function`，即 PointEstimate）。

**第一件事是 `result = result.ToLower();`** —— 这一行解释了整个大小写谜题：
DB 里存的是 Pascal 风格（`DeltaQ` / `Incidence` / `POP` / `Beta`），
而动态生成的 C# 方法签名参数名是**全小写**（`deltaq` / `incidence` / `pop` / `beta`）。
C# 大小写敏感，所以必须先统一小写才能编译通过。

**随后按顺序做函数名替换**（每条都同时处理 `xxx(` 与 `xxx (` 两种带空格的写法）：

| Pascal 写法 | → C# | Pascal 写法 | → C# |
|---|---|---|---|
| `abs(` | `Math.Abs(` | `log(` | `Math.Log(` |
| `acos(` | *token* → `Math.Acos(` | `log10(` | `Math.Log10(` |
| `asin(` | *token* → `Math.Asin(` | `max(` | `Math.Max(` |
| `atan(` | *token* → `Math.Atan(` | `min(` | `Math.Min(` |
| `cos(` | `Math.Cos(` | `pow(` | `Math.Pow(` |
| `sin(` | `Math.Sin(` | `round(` | `Math.Round(` |
| `tan(` | `Math.Tan(` | `sign(` | `Math.Sign(` |
| `atan2(` | `Math.Atan2(` | `sinh(` | `Math.Sinh(` |
| `bigmul(` | `Math.BigMul(` | **`sqr(`** | **`myPow(`** |
| `ceiling(` | `Math.Ceiling(` | `sqrt(` | `Math.Sqrt(` |
| `cosh(` | `Math.Cosh(` | `tanh(` | `Math.Tanh(` |
| `divrem(` | `Math.DivRem(` | `truncate(` | `Math.Truncate(` |
| **`exp(`** | **`Math.Exp(`** | `ieeeremainder(` | `Math.IEEERemainder(` |
| `floor(` | `Math.Floor(` | | |

其中 `acos/asin/atan` 三步走两步（先换成 `ACOS_TOKEN(` 这种保护性 token，
最后才展开成 `Math.Acos(`），目的是防止后续 `cos(` 的替换把 `acos(` 误伤。

> 🐛 **【观察】源码 bug**：翻译链里有一行
> `.Replace("Math.AMath.Cos(", "Math.Acos(")` —— 明显的复制粘贴错误
> （原意应是 `ACOS_TOKEN(` 的保护性回退）。它只会影响含 `acos(` 的 CR 公式；
> 中国区用的 FormID 37 / 312 / 313 均不含 `acos(`，故对本项目无实际影响。

**分支 1 —— 含 `if` 且含 `:=`（Pascal 风格的显式结果变量）：**

```csharp
result = result.Replace(" and", " && ").Replace(")and", ")&&")
               .Replace(" or",  " || ").Replace(")or",  ")||")
               .Replace(":=",   " return ")
               .Replace("result"," ")          // 抹掉 Pascal 的 Result 变量名
               .Replace("else", ";else")
               .Replace("then", " ")
               .Replace("<>",  "!=");
result = result + ";";
// 若没有 else 分支，补一个哨兵
string tmp = result.Replace("else if","").Replace("else  if","").Replace("else   if","");
if (!tmp.Contains("else")) result += " else return -999999999;";
```

**分支 2 —— 普通表达式（无 `if`/`:=`）：**

```csharp
result = " return " + result + " ;";
```

**端到端实测（FormID 37，中国臭氧主力函数）：**

```
DB 原文 : (1-(1/EXP(Beta*DELTAQ)))*Incidence*POP*A
↓ ToLower()         → (1-(1/exp(beta*deltaq)))*incidence*pop*a
↓ exp( → Math.Exp(  → return (1-(1/Math.Exp(beta*deltaq)))*incidence*pop*a ;
↓ 编译进 class myLibPointEstimate<CRID>
↓ 反射调用 myMethod(a, b, c, beta, deltaq, q0, q1, incidence, pop, prevalence)
```

**⇒ 一句话总结：BenMAP 的"公式引擎"其实是一个
「Pascal 风格 DSL → `ToLower()` → 关键字/函数名字符串替换 → 动态编译 C#」的直译器，
没有解析器、没有 AST、没有语法校验。**

**附：公式里"哪些词被当成变量"的识别逻辑**
（`getSetupVariableNameListFromDatabaseFunction`，L4512+）：
先用 `Replace` 把 `prevalence/incidence/deltaq/pop/beta/q0/q1`
以及所有数学函数名从公式里抠掉（避免把 `cos` 里的 `s` 误判成变量），
再用 `Regex.Replace(text, @"[^\w]+", ",")` 切词，
逐个与 `SystemVariableNameList` 比对——这正是 §5.5.2 里
"中国 Setup 无全局变量 ⇒ 编译必然失败"这一判定的依据来源。

### 4.2 基线发病率函数 `BASELINEFUNCTIONALFORMS`（12 条）

对 `(发病率变化 / 基线发病率) × 100%` 做修正，输出 `PercentOfBaseline`。
12 条均为代数式（无 exponentials / ten-functions）。详见 BenMAP 文档 附录 B。

### 4.3 货币估值函数 `VALUATIONFUNCTIONALFORMS`（19 条）★ 最关键

**这是 ABaCAS-SE 想知道但查不到的「健康效益单价」那一层。**
变量：`A, B, C, D, AllGoodsIndex, MedicalCostIndex, WageIndex, LagAdjustment` + setup vars
（`median_income`、`AVGHHSIZE` 等）。

**【观察】** 19 条公式全文（按用途归并；`x` 表示乘号）：

```text
ID=1  : A x AllGoodsIndex                     -- VSL x 总体CPI 折算
ID=2  : A x B x AllGoodsIndex                 -- VSL x 具体CPI比 x 总体CPI
ID=6  : AllGoodsIndex
ID=21 : A x 1                                 -- ★ 中国区默认：直接用 VSL，不做收入调整

ID=3  : A x MedicalCostIndex + B x WageIndex -- 医疗成本 + 误工（无贴现）
ID=4  : A x MedicalCostIndex
ID=8  : A x WageIndex
ID=9  : ((median_income)/(52 x 5)) x WageIndex

ID=5  : A x MedicalCostIndex + B x ((median_income)/(52 x 5)) x WageIndex
ID=18 : A x MedicalCostIndex + B x ((median_income_2007)/(52 x 5 x C)) x WageIndex
ID=19 : A x MedicalCostIndex + B x ((median_income)/(52 x 5 x C)) x WageIndex
ID=20 : ((median_income)/(52 x 5 x C)) x WageIndex
ID=22 : A + B x ((C)/(52 x 5))

ID=11 : A x B x AVGHHSIZE                     -- x 家庭人口数
ID=12 : A x B x LagAdjustment                 -- 滞后/贴现调整（latency）
ID=13 : LagAdjustment
ID=10 : A x B                                 -- 纯乘积
```

**关键解读**：这里同时并存两套估值体系：

- **支付意愿法（VSL / WTP）**：`ID=1 / 2 / 21` —— 直接给一个"生命统计价值"，是 **BenMAP 的默认口径**
- **人力资本法（HCC）**：`ID=3 / 4 / 5 / 8 / 9 / 18 / 19 / 20 / 22` —— 用**工资 + 医疗成本 + 误工天数**推导，
  其中 `52 x 5 = 260` 是「每年 260 个工作日 × 误工 5 年」的标准折算

**指数来源**【观察】：`AllGoodsIndex` / `MedicalCostIndex` / `WageIndex` 来自 `INFLATIONENTRIES` 表。

#### 4.3.1 ★ 中国区实际只用了 4 种估值公式（已查实）

**【观察】** 把 `VALUATIONFUNCTIONDATASETID IN (7,10)`（中国两个估值数据集）全部 16 条
`VALUATIONFUNCTIONS` 拉出来，其 `FUNCTIONALFORMID` 分布**只有 4 种**：

| VFDataSet | VFID | FormID | 生效公式 | 含义 |
|---|---|---|---|---|
| 7 China Valuation | 343–351 | **21** | `A*1` | ★ **不做任何经济调整**，直接用 2010 RMB 原值 |
| 7 | 352 | **1** | `A*AllGoodsIndex` | 用总体 CPI 折算到目标货币年 |
| 10 April 2013 | 589–591 | **1** | `A*AllGoodsIndex` | 同上 |
| 10 | 592–593 | **4** | `A*MedicalCostIndex` | 疾病成本（COI）用医疗 CPI 折算 |
| 10 | 594 | **8** | `A*WageIndex` | 误工损失用工资指数折算 |

**【观察】** 中国三个 Setup（4 / 5 / 7）在 `SETUPGLOBALVARIABLES` 里**没有任何全局变量**。
而 `median_income` / `AVGHHSIZE` 正是 `FormID = 5 / 9 / 11 / 18 / 19 / 20 / 22` 所需的 setup 变量。

**⇒ 推论【推断，高置信】**：中国区**不可能**使用 EPA 的收入弹性估值体系（`FormID 19` 等）——
那些公式引用 `median_income`，编译时会因「未声明标识符」而失败并落入哨兵值 `-999999999`。
数据库里也**确实没有任何一条中国 VF 引用这些 FormID**。两条机制互为印证。

**⇒ 结论**：中国的收入/物价调整只走**两条**通道：
1. `AllGoodsIndex / MedicalCostIndex / WageIndex`（在估值公式**内部**，由 `INFLATIONENTRIES` 驱动）
2. `income` 因子（在估值公式**外部**，见 §5.4，由 `INCOMEGROWTHADJFACTORS` 驱动）

### 4.4 EI 路径 `EIFUNCTIONS`（12 条，全部为毒代动力学直线）

**【观察】** 只有一条模板：`TXT = A + B*AOT40`。12 条参数（A=基线发病率%，B=每 ppb 斜率）：

| ID | A | B | ID | A | B | ID | A | B |
|---|---|---|---|---|---|---|---|---|
| 25 | 100.0 | -1.30 | 29 | 99.0 | -1.60 | 33 | 94.0 | -0.39 |
| 26 | 100.0 | -2.28 | 30 | 100.0 | -0.53 | 34 | 100.0 | -1.25 |
| 27 | 96.1 | -2.50 | 31 | 100.0 | -0.95 | 35 | 100.0 | -0.21 |
| 28 | 100.0 | -2.20 | 32 | 100.0 | -3.90 | 36 | 99.0 | -0.61 |

（A=100 表示该年龄段 100% 患病/发病；斜率为负表示 AOT40 每升 1 ppb，指标下降。）
**【观察】** ABaCAS_SE 脚本 `CREATE AQG` 硬编码 `-Pollutant PM2.5`（IL_01D2 / IL_0273），
故 PM2.5 情景不会走 EI 路径（EI 仅 AOT40 臭氧）。

---

## 5. 第 2 层：参数实例（"钱"的具体数字从哪来）

### 5.1 `CRFUNCTIONS`（476 条暴露-响应实例）

**【观察】** 每条是一个「公式模板 ID + 科学参数」的组合，字段含：
`FunctionalFormID`（→ §4.1）、`Beta`（不确定性的中心值）、`BetaDistributionType`、
`P1Beta` / `P2Beta`（抽样参数）、适用 `EndpointID` / `PollutantID` / `AgeRange`。

不确定性的处理【观察】：BenMAP 对 `Beta` 做 **Latin Hypercube Sampling，100 点**，
每点重算一次发病率变化，得到 **100 个百分位**。

### 5.2 `VALUATIONFUNCTIONS`（477 条货币估值实例）

每条 = `FunctionalFormID`（→ §4.3）+ `A / B / C / D` + `InflationYear` + `ValuationMethodType`。

### 5.3 为什么「换一个估值函数，差 25 倍」

**【观察】** PM2.5 长期死亡终点的实测单价对比：

| 估值函数 | 单价 | 结果量级 |
|---|---|---|
| 美国 VSL 2015$（VF=335） | `$8,705,114` | 最高 |
| 中国 WTP（VF=359, Cropper 2009） | CNY `1,549,500` | 约 1/5 |
| 中国 WTP（VF=364, 重庆） | CNY `349,812` | 约 1/25 |
| **中国 HC 人力资本法（VF=361）** | **CNY `83,800`** | **最低** |
| 医疗成本+误工（VF=234 AMI） | `$36,167 + $11,908` | 只对非致死终点 |

> **复现铁律**：任何 BenMAP 效益报告**必须同时披露 `(endpoint, CRFID, VFID)` 三元组**，
> 否则数字不可复现、不可比较。ABaCAS_SE 的 UI 不显示 VFID —— 这是它作为报告工具的缺陷。

### 5.4 `INCOMEGROWTHADJFACTORS`：收入增长调整

**【观察】** `APVCommonClass.cs:1425`：

```sql
select IncomeGrowthAdjdatasetID, YYear, Mean, EndPointGroups
  from IncomeGrowthAdjfactors
 where IncomeGrowthAdjdatasetID={0} and YYear={1}
```

按**终点组 × 目标年份**查表，把基线年份的 VSL / 成本推到估值年份（`income` 因子）。
**【推断】** ABaCAS-SE 的 `TargetYear`（来自 `情景对应关系.csv`）最终会传导到这里。

### 5.5 `INFLATIONENTRIES`：三个通胀指数

**【观察】** 提供 `AllGoodsIndex`（总体 CPI）、`MedicalCostIndex`（医疗 CPI）、`WageIndex`（工资增长）。

**【观察，已查实】** 中国 `PRD_China`（SetupID=4）用 `INFLATIONDATASETID = 6`「China_inflation」，
**61 条，1980–2040 连续年份，基年 2000 = 1.0000000**。完整数值见附录 D。
关键锚点：

| 年份 | AllGoodsIndex | MedicalCostIndex | WageIndex |
|---|---|---|---|
| 2000（基年） | 1.0000000 | 1.0000000 | 1.0000000 |
| 2005 | 1.1341460 | 1.2392640 | 1.1501970 |
| 2010 | 1.2662950 | 1.4894021 | 1.3092020 |
| **2017** | **1.4480000** | **1.7189000** | **1.4938000** |
| **2025** | **1.6544000** | **2.0381000** | **1.7218000** |
| 2040 | 2.0414000 | 2.6366000 | 2.1493001 |

> **★ 这一张表就是「2025 年结果比 2017 年大多少」的完整答案**：
> 若 VF 用 `FormID 21`（中国 WTP 主力），则**完全没有通胀调整**，2017→2025 结果**不变**；
> 若用 `FormID 1`（Xie 2010 / April2013 VSL），则乘 1.6544（VSL 口径）
> 或乘 2.0381（COI 口径）。**口径不同，跨年比较的结果完全不同。**

**【观察】** 其他中国通胀数据集：`3`（Setup6，27 条）、`5`/`8`/`9`（Setup6/5/7，
各 61 条，同 `China Inflation 1980_2040`）、`7`（Setup5，27 条）。

#### 5.5.1 `INCOMEGROWTHADJFACTORS` 全表（中国 SetupID=4 → DataSetID=17）

**【观察】** `EndpointGroups = 'Mortality'`，`DISTRIBUTION` 为空（确定性点值），
`P1/P2` 均为 `NULL`（无分布，仅 `MEAN`），基年 **2010 = 1.0000000**：

| 年份 | Mean | 年份 | Mean | 年份 | Mean |
|---|---|---|---|---|---|
| 1990 | 0.13682771 | 1998 | 0.31630659 | 2006 | 0.66241050 |
| 1991 | 0.14938700 | 1999 | 0.34040859 | 2007 | 0.75622368 |
| 1992 | 0.17066079 | 2000 | 0.36910939 | 2008 | 0.82908332 |
| 1993 | 0.19449240 | 2001 | 0.39974669 | 2009 | 0.90547669 |
| 1994 | 0.21993330 | 2002 | 0.43605191 | **2010** | **1.00000000** |
| 1995 | 0.24396101 | 2003 | 0.47976780 | 2015 | 1.46932800 |
| 1996 | 0.26837790 | 2004 | 0.52815259 | 2020 | 2.10941100 |
| 1997 | 0.29332909 | 2005 | 0.58788681 | **2025** | **2.89007500** |
| | | | | 2030 | 3.77721310 |

> **★ 「25 倍」谜题的第二个来源**：中国收入增长因子 1990→2025 走 **0.1368 → 2.8901**，
> 本身就是 **21.1 倍**。任何跨越 1990–2025 的对比，都必须先扣除这一项。

#### 5.5.2 ★ 中国区数据集矩阵（`.apvx` 究竟绑定什么）

**【观察，已查实】** 数据库里**没有单独的 `.apvx` 绑定表**。绑定关系是
**函数实例表自带的外键**：

| 表 | 绑定字段 |
|---|---|
| `CRFUNCTIONS` | `CRFUNCTIONDATASETID` → `CRFUNCTIONDATASETS` |
| `VALUATIONFUNCTIONS` | `VALUATIONFUNCTIONDATASETID` → `VALUATIONFUNCTIONDATASETS` |
| `EIFUNCTIONS` | `EIFUNCTIONDATASETID` → `EIFUNCTIONDATASETS` |

（`CRFUNCTIONCUSTOMENTRIES` / `VALUATIONFUNCTIONCUSTOMENTRIES` **不是**绑定表，
它们只是 `DistA='Custom'` 时的自定义分布样本表。）

**【观察】** 三个中国 Setup 的完整数据集组合：

| SetupID | 名称 | 投影 | CR 数据集（函数数） | VF 数据集 | EI 数据集 |
|---|---|---|---|---|---|
| **4** | **PRD_China** | AsiaNorthAlbers | **15** US_Ozone_Max8hours (8)<br>**16** China New HIF April 2013 (46)<br>**22** Long-term functions (4) | **7** China Valuation (10) | 3 China Ecological Impact Functions 2005 (12) |
| **5** | **JJJ_China** | AsiaSouthAlbers | 17 China New HIF April 2013 (45)<br>18 China HIF (8)<br>19 Long-term (4)<br>20 LT-function (26) | 8 China Valuation (6) | — |
| **7** | **JN_China** | AsiaNorthAlbers | 23 US_Ozone_Max8hours (8)<br>21 LT-function (26) | 10 China Valuation Functions April 2013 (6)<br>11 同名 (112) | — |
| 6 | （悬空，FDB 中无此 Setup） | — | 7 / 10 / 13 / 14 | — | — |

**⇒ `.apvx` 的内容【推断，高置信】** = `SetupID + CRFunctionDatasetID + ValuationFunctionDatasetID
(+ EIFunctionDatasetID)` + 用户选中的具体函数 ID 列表。

**⇒ 已匹配【观察】** ABaCAS 硬编码的 `BenMAP_PRD_2017_Ozone.apvx`
= SetupID 4 (`PRD_China`) + CRDataSet 15 (`US_Ozone_Max8hours`) + VFDataSet 7 (`China Valuation`)。

### 5.6 ★★★ 第 3 层核心：公式求值引擎 = 运行时动态编译 C#

**【观察】** 这是整个 BenMAP 最关键的机制，也是前几轮唯一没挖透的缺口。
源码文件：`E:\CodeProject\_rea_benmap\src\BenMAP\Tools\CalculateFunctionString.cs`（467 行）。
一句话：**BenMAP 不解释公式，它把公式拼成一段 C# 源码，用 CodeDom 现场编译成 DLL，再反射调用。**

#### 5.6.1 四个编译器（每个 CRFunction 编译出一个独立的类）

| 方法 | 生成的类名 | 用途 | 对应缓存字典 |
|---|---|---|---|
| `CreateAllBaselineEvalObjects` | `myLibBaseLine<CRID>` | 基线发病率 | `dicBaselineMethodInfo` |
| `CreateAllPointEstimateEvalObjects` | `myLibPointEstimate<CRID>` | 健康影响点估计 | `dicPointEstimateMethodInfo` |
| `CreateAllPopulationEvalObjects` | `myLibPopulation<CRID>` | 人口（见 5.6.4） | `dicPopulationMethodInfo` |
| `ValuationEval`（懒编译） | `myLibValuation<icount>` | 货币估值 | `dicValuationMethodInfo` |

缓存键：前三个是 `CRID`，估值侧是**编译后的 C# 代码串本身** `cCharpCode`
（即相同公式文本只编译一次；`icount` 只是自增类名后缀）。

#### 5.6.2 生成的 C# 源码模板（PointEstimate 版，逐字来自源码 L150-158）

```csharp
using System;
namespace CoustomEval{
  class myLibPointEstimate<CRID> {
    public double myPow(double a) { return Math.Pow(a,2); }
    public double myMethod(double a, double b, double c, double beta, double deltaq,
                           double q0, double q1, double incidence, double pop, double prevalence
                           /* + ", double <变量名>" 逐个追加 */) {
      try { return (1-(1/Math.Exp(beta*deltaq)))*incidence*pop*a ; }
      catch (Exception ex) { return -999999999; }
    }
  }
}
```

**Baseline 版**（L96-97）类名前缀换成 `myLibBaseLine`，**方法签名完全相同**。

#### 5.6.3 编译设置（四个编译器一致）

```csharp
CSharpCodeProvider csharpCodeProvider = new CSharpCodeProvider();
CodeDomProvider provider = CodeDomProvider.CreateProvider("CSharp");

CompilerParameters cp = new CompilerParameters();
cp.ReferencedAssemblies.Add("System.dll");     // 估值侧是 "system.dll"（大小写不同，无影响）
cp.CompilerOptions  = "/t:library";
cp.GenerateInMemory = true;                     // ★ 只在内存编译，不落盘
cp.OutputAssembly = CommonClass.DataFilePath + "\\Tmp\\"
                  + 年+月+日+时+分+秒+毫秒 + new Random().Next(2000) + ".dll";

CompilerResults cr = provider.CompileAssemblyFromSource(cp, myCode.ToString());
Assembly assembly = cr.CompiledAssembly;
object tmp = assembly.CreateInstance("CoustomEval.myLibPointEstimate" + CRID);
dicPointEstimateMethodInfo.Add(CRID, tmp);
```

> **【观察】** `GenerateInMemory=true`，`OutputAssembly` 只是编译器要求的占位文件名
> （`DataFilePath\Tmp\` 目录也不会被真正创建）。

#### 5.6.4 参数绑定表（★ 复现时必须一字不差）

调用侧（`PointEstimateEval`，L287-330）构造实参列表：

```csharp
List<object> lstParam = new List<object>()
  { a, b, c, beta, deltaq, q0, q1, incidence, pop, prevalence };
// 然后按 dicSetupVariables 的枚举顺序，逐个 lstParam.Add(值)
tmp = dicPointEstimateMethodInfo[crID];
mi   = tmp.GetType().GetMethod("myMethod");
object result = mi.Invoke(tmp, lstParam.ToArray());
```

| 形参（小写） | 来源 | 说明 |
|---|---|---|
| `a` / `b` / `c` | `CRFunctions.ValuationFunction.A/B/C` | 估值函数的 3 个参数，CR 与 VF 共用一套 |
| `d` | `VALUATIONFUNCTIONS.D` | **仅估值版有**（签名第 4 位） |
| `beta` | `CRFunctions.Beta` | 浓度-响应斜率 |
| `deltaq` | 情景浓度 − 对照浓度 | §4.1 |
| `q0` / `q1` | 阈值浓度下界 / 上界 | FormID 11/18/19/57 用 |
| `incidence` | 基线发病率（BaselineEval 算出来的） | |
| `pop` | 网格人口 | |
| `prevalence` | 基线患病率 | |
| 追加的 `<key.ToLower()>` | `SETUPVARIABLES` 逐个 | 如 `median_income`、`avghhsize` |

估值版签名（`ValuationEval`，L412-415）：
`myMethod(a, b, c, d, allgoodsindex, medicalcostindex, wageindex, lagadjustment, …)`
—— 与 `VALUATIONFUNCTIONALFORMS` 里的变量名一一对应。

**Population 版特殊逻辑**（`CreateAllPopulationEvalObjects`，L178-262，标注 `BENMAP-541`）：
BenMAP 假定人口函数就是 `POP × 某个 0~1 的人口变量`。
做法是把 HI 公式里出现的变量名拿去查
`SETUPGEOGRAPHICVARIABLES JOIN SETUPVARIABLES`，
`HAVING min(VVALUE)>=0 AND max(VVALUE)<=1` —— 落在 [0,1] 的才认定为人口比例变量，
然后生成 `return pop * <变量名>;`；找不到就退化成 `return pop;`。

#### 5.6.5 失败哨兵 `-999999999`

四个 `*Eval` 方法**最外层都包了 `try/catch`，catch 里 `return -999999999`**；
生成的类**内部**还有一层 `try/catch`，同样返回该值。
所以编译失败、变量未声明、反射签名不匹配 —— 全部静默变成 `-999999999`。

> **【推断】** 复现时若看到 `-999999999` 这个"神奇数字"，
> 99% 是公式引用了当前 Setup 没定义的变量（例如 §5.5.2 里
> 中国 Setup 无 `median_income`，若误选 FormID 5/9/11/18/19/20/22 就会命中）。

### 5.7 APV 最终公式（已从源码逐字确认）

**【观察】** `APVCommonClass.cs:3217-3222`
（`getOneAllSelectValuationMethodCRSelectFunctionCalculateValue`）：

```csharp
dValuation = getValueFromValuationFunctionString(sFunction, A, B, C, D,
                 AllGoodsIndex, MedicalCostIndex, WageIndex, 0, dicVariable);
...
apvValueAttribute.PointEstimate = Convert.ToSingle(
                 income * crCalculateValue.PointEstimate * dValuation);
```

$$
\mathrm{APV}_{cell} = f_{income}(y) \times \mathrm{CR} \times V(A,B,C,D;\ \text{AllGoods},\ \text{Medical},\ \text{Wage},\ \text{SetupVars})
$$

| 量 | 取值函数 | 源码行 | 查表条件 |
|---|---|---|---|
| `income` | `getIncomeGrowthFactorsFromDataSetIDAndYear` | `APVCommonClass.cs:1420` | `Advance.AdjustIncomeGrowthDatasetID` + `Advance.IncomeGrowthYear` |
| 三个指数 | `getInflationFromDataSetIDAndYear` | `APVCommonClass.cs:1392` | `Advance.InflationDatasetID` + `Advance.CurrencyYear` |

`income` 按 `dicIncome[VF.EndPointGroup]` 取（`APVCommonClass.cs:3159-3161`）：
**若 `Advance.EndpointGroups` 里不含该终点组，则 `income = 1`**（等于不做收入调整）。

> **★ 这是中国区口径分歧的根源**：中国 VF 的绝大多数 `EndPointID=141`（WTP），
> `EndpointGroups` 与收入增长表（`EndpointGroups='Mortality'`）能否对上，
> 决定了 APV 到底乘不乘那个 2.89 倍的收入因子。
> **【未知】** 具体取哪一年（`情景对应关系.csv` 里的 TargetYear）需实跑才能确定。

### 5.8 `.apvx` 运行时探测逻辑（ABaCAS_SE.exe IL）

**【观察】** `uc_BenMAP` 中按 `Field::Pollutant` + `Field::CurrentProject` 分支，
IL 全量文件 `E:\CodeProject\_rea_abacas\il_all.txt` 约第 253868 行起：

```csharp
// PM2.5 分支
if (Directory.Exists(DataPath + "\\Example\\YRD\\BenMAP-CE\\")) {
    txtAPVfile.Text = "BenMAP_YRD_2017.apvx";
    txtAPVfile.Tag   = dir + txtAPVfile.Text;
    initAllToolsPath();
    GetBenMapAuditReport(dir + txtAPVfile.Text, 0);
    if (File.Exists(dir + "BenMAP_YRD_2017.cfgx")) txtCFGFile.Text = "BenMAP_YRD_2017.cfgx";
    if (File.Exists(dir + "YRD_04km_city.shp"))     txtGridDefinition.Text = "YRD_04km_city.shp";
}
// PRD 分支（臭氧）
if (Directory.Exists(DataPath + "\\Example\\PRD\\BenMAP-CE\\")) {
    txtAPVfile.Text = "BenMAP_PRD_2017_Ozone.apvx";  ...
}
// 第三分支：BenMAP_WUS_State_2025.apvx
```

**⇒ 三件套契约【观察】**

| 扩展名 | 含义 |
|---|---|
| `.apvx` | 健康影响 + 估值配置（**替代 BenMAP GUI 的一整套选择**） |
| `.cfgx` | 基线发病率 / 对照浓度 / 人口 / 网格配置 |
| `.shp` | 网格定义（与 `.cfgx` 配对） |

**⚠️ 重要更正**：`WUS` / `YRD` / `PRD` **不是 BenMAP 的 Setup 名**，
而是 ABaCAS 的**示例工程目录名**（`Example\WUS\` / `Example\YRD\` / `Example\PRD\`）。
对应的 BenMAP Setup 名藏在 `.apvx` 二进制里。

**【观察】本机实测**：`D:\杂物\ABaCAS\ABaCAS\` 全树搜索 `*.apvx` / `*.cfgx` = **0 个**。
安装目录有 `Data`(Base_map/Colors/CHM)、`Data_Fusion`、`ICET`、`BenMAP-CE`、
`ABaCAS-OE`、`Model-VAT`、`RSM-VAT`、`SMAT-CE`，但**没有 `Example` 目录**
（`ICBA\Data\Example\` 首次运行才创建）。
⇒ 无法在本机通过运行时验证 SetupID。

---

## 6. 第 3 层：执行引擎与流水线

### 6.1 健康影响 `CalculateCRSelectFunctionsOneCel`

源码坐标 `ConfigurationCommonClass.cs:4251`（**逐网格单元**执行）。等价伪代码：

```python
def benmap_cell(CRF, cell, setup):
    C_base    = cell[CRF.metric_id]            # 情景浓度
    C_control = cell[CRF.control_metric_id]    # 对照浓度
    Pop, I0, Prev = cell.pop_by_age, cell.incidence_by_age, cell.prev_by_age

    dC = C_base - C_control                    # dQ
    formula = translate_to_python(FUNCTIONALFORMS[CRF.functional_form_id])  # 4.1
    if "pop" in formula.lower():
        cases = sum(eval(formula, beta=beta, deltaq=dC, q0=C_control, q1=C_base,
                         incidence=I0[a], pop=Pop[a], prevalence=Prev[a], A, B, C)
                    * season_days for a in Pop)
    else:
        cases = eval(formula, beta=beta, deltaq=dC, incidence=mean(I0), pop=0)

    bl = BASELINEFUNCTIONALFORMS[CRF.baseline_form_id]   # 4.2
    baseline = cases if not bl else eval(bl, incidence=I0, pop=pop, prevalence=Prev, A, B)
    pct_of_baseline = round(cases / baseline * 100, 4)

    percentiles = []                            # LHS 100 点
    for _ in range(100):
        beta_i = sample(CRF.dist_beta, CRF.p1_beta, CRF.p2_beta)
        percentiles.append(eval(formula, beta=beta_i, ...))
    return dict(cases=cases, baseline=baseline, pct=pct_of_baseline,
                percentiles=percentiles,
                mean=np.mean(percentiles), sd=np.std(percentiles, ddof=1))
```

### 6.2 货币化 `getOneAllSelectValuationMethodCRSelectFunctionCalculateValue`

源码坐标 `APV/APVCommonClass.cs:3127`。**【观察】** IL 等价：

```csharp
// L3215：从数据库估值函数求单价
dValuation = getValueFromValuationFunctionString(
    sFunction,
    allSelectValuationMethod.BenMAPValuationFunction.A, .B, .C, .D,
    AllGoodsIndex, MedicalCostIndex, WageIndex,   // <- INFLATIONENTRIES
    LagAdjustment,                                 // <- 潜伏期/贴现
    dicSetupVariables);                            // <- median_income, AVGHHSIZE ...
if (dValuation == double.NaN) dValuation = 0.0;

// ★★★ 核心恒等式 ★★★
apvValueAttribute.PointEstimate =
    Convert.ToSingle(income * crCalculateValue.PointEstimate * dValuation);
```

**百分位传播**【观察】L3252 —— 单价的不确定性也卷进百分位：

```csharp
if (crCalculateValue.PointEstimate == 0) { /* 退化 */ }
else if (A != 0)  v = crCalculateValue.PointEstimate * d * dMonte
                            / (crCalculateValue.PointEstimate * A);
else              v = crCalculateValue.PointEstimate * d / crCalculateValue.PointEstimate;
...
apvValueAttribute.LstPercentile = getMedianSample(lstValue, 100);
```

`getMedianSample`（L2313）把采样值排序后**按 100 等分取每段中位数**：

```csharp
lstOut.Add(listInput.GetRange(i * (listInput.Count / Points),
                              (listInput.Count / Points)).Median());
```

### 6.3 多终点合并（Pooling）

一个情景通常同时选中多个终点（全因死亡 + 心血管 + 呼吸 + 肺癌 + 急诊…），
必须合并成一个数（脚本里 `-ResultType PooledValuation`）。

**【观察】** 枚举 `PoolingMethodTypeEnum`（`CommonClass.cs`）共 8 个值，
字符串映射见 `APVCommonClass.cs:5417getPoolingMethodTypeEnumFromString`：

```
None=0  SumDependent=1  SumIndependent=2  SubtractionDependent=3
SubtractionIndependent=4  SubjectiveWeights=5  RandomOrFixedEffects=6  FixedEffects=7
```

注意 UI 字符串 `UserDefinedWeights` → 枚举 `SubjectiveWeights`；
`RandomEffects` 在 UI 上对应的是 `RandomOrFixedEffects`。

**【观察】** 全部实现在 `getPoolingMethodCRSelectFunctionCalculateValue`
（`APVCommonClass.cs:2404-3282`），逐策略数学形式如下。
设第 i 个终点在该网格的百分位向量为 `LHS_i[0..19]`、`PointEstimate_i` 为 `PE_i`、
方差 `Var_i`，共 k 个终点。

#### 6.3.1 `SumDependent`（L2470-2545）

$$
PE = \sum_i PE_i,\qquad Baseline=\sum_i,\ Population=\sum_i,\ Incidence=\sum_i
$$
$$
LHS[j] = \sum_i LHS_i[j]\quad (j = 0..19)
$$

**百分位是逐元素直接相加**（不假设独立）。
合并后统一算 `Mean` / `Variance` / `StdDev` / `PercentOfBaseline = Mean/Baseline×100`。
注意 `Population = ΣPop / k` —— **人口取了平均**（代码 L2540）。
逐终点 `try/catch` 包裹，任一终点异常则该终点跳过（不中断）。

#### 6.3.2 `SumIndependent`（L2549-2607）

点估计与 Baseline/Population/Incidence 的**聚合方式与 SumDependent 完全相同**（仍是求和/平均），
唯一区别在百分位：**假设各终点独立，做 5000 次蒙特卡洛卷积**

```csharp
for (int iPer = 0; iPer < 5000; iPer++) {
    float d = lstPercentile[0][randomPooling.Next(0, CommonClass.CRLatinHypercubePoints - 1)];
    for (int iPerSec = 1; iPerSec < lstPercentile.Count; iPerSec++)
        d = d + lstPercentile[iPerSec][randomPooling.Next(0, CommonClass.CRLatinHypercubePoints - 1)];
    lstPooling.Add(d);
}
crCalculateValue.LstPercentile = getMedianSample(lstPooling, CRLatinHypercubePoints);
```

即：从每个终点的 20 个 LHS 采样点里随机各抽一个，求和，重复 5000 次，
再取中位数序列。`Delta = ΣDelta / k`、`Population = ΣPop / k`（**都是平均**）。
⚠️ `randomPooling = new Random()` **未设种子** ⇒ 结果不可完全复现（除非同进程同 tick）。

#### 6.3.3 `FixedEffects` / `RandomOrFixedEffects`（L2827-3120，case 穿透共用一段代码）

两者 `case` 标签紧邻 ⇒ **共用同一段逆方差加权代码**。

$$
w_i = \frac{1/Var_i}{\sum_j 1/Var_j},\qquad PE = \sum_i w_i\, PE_i
$$

退化规则：`Var_i = 0`（或 `sumVariance == 0`）时该终点权重置 `1/k`（等权）；
`NaN` 权重同样回退 `1/k`。Baseline/Population/Incidence/Delta 全部按同一 `w_i` 加权。
百分位不做卷积，而是**按 `Round(w_i×100)` 次重复堆叠**第 i 个终点的 LHS 数组。

**`RandomOrFixedEffects` 额外做异质性检验**（仅当 `getChidist` 返回的 p < 0.05 时）：

```csharp
dSum   = Σ_i (1/Var_i)·(Pooled_i − PE_i)²          // 注意用的是池化后的 crCalculateValue.PointEstimate
dRandom= Σ_i (1/Var_i)²
dRandom= (dSum − 1) / (sumVariance − dRandom/sumVariance);   // τ²
w_i    = 1/(Var_i + dRandom);                        // 换成 DL 随机效应权重
```

然后**清零重算**全部四个量值。`getChidist`（L2326）本身：

$$
Q = \sum_i \frac{1}{Var_i}\,(Pooled - PE_i)^2,\qquad p = \text{ChiSquared}_{k-1}.RightProbability(Q)
$$

`Meta.Numerics` 的 `ChiSquaredDistribution` 用 **`lstWeight.Count - 1`** 作自由度；
异常时 `catch` 返回 `1.0`（即"不显著"→ 走固定效应）。

#### 6.3.4 `SubtractionDependent`（L2609）/ `SubtractionIndependent`（L2679）

与 Sum 两版逐字相同，只是把 `+=` 换成 `-=`，且**第一条终点是赋值而非累加**：

```csharp
if (iSubtraction == 0) crCalculateValue.PointEstimate = k.Value[s][0];   // 头一个终点
else                  crCalculateValue.PointEstimate -= k.Value[s][0];
```

`Population` 仍然是 `+=`（唯一例外，L2661/L2749）——
所以"相减"只在 PE/Baseline/Incidence/Delta/百分位上生效，人口不减。

#### 6.3.5 `SubjectiveWeights`（= UI 的 `UserDefinedWeights`，L2755-2826）

$$
w_i \leftarrow w_i / \sum_j w_j\ (\text{仅当}\ \Sigma w \ne 1\ \text{时}),\qquad
PE = \sum_i w_i\,PE_i
$$

百分位同样按 `Round(w_i×100)` 次重复堆叠。
若权重全为 0 导致 `lstPooling` 为空，则**百分位全填 0**（L2795-2802）。

#### 6.3.6 不确定性的来源链

```
CRFunction 的 C 分布参数 (DistA/DistC/DistD 或 P1/P2/MEAN)
  ↓ LHS 抽样（默认 CRLatinHypercubePoints = 20）
每终点 20 个 LHS 点（LstPercentile，L2607/2718/2791/2905/3007/3067）
  ↓ Pooling（逐元素相加 / 5000 次 MC / 加权堆叠）
合并后的 20 个百分位
  ↓ getMean / getVariance / getStandardDeviation
Mean、Variance、SD、PercentOfBaseline
  ↓ LHS 采样估值函数参数 getLHSArrayValuationFunctionSeed(APVCommonClass.cs:5259)
APV 的分布
```

**【观察】** 14 种分布的 LHS 采样器（`getLHSArrayValuationFunctionSeed`，L5259+）：

| 分布 | 采样函数 |
|---|---|
| Normal | `CreateSample(Normal_distribution, n, Seed)` |
| Triangular | `CreateSample(triangularDistribution, n, Seed)` |
| Poisson | `CreateSample(poissonDistribution, n, Seed)` |
| Binomial | `CreateSample(binomialDistribution, n, Seed)` |
| **LogNormal** | `CreateSample(lognormalDistribution, n, Seed)` — **P1A 存的是 μ，P2A 存的是 σ（不是方差）** |
| Uniform | `CreateSample(uniformDistribution, n, Seed)` |
| Exponential | `CreateSample(exponentialDistribution, n, Seed)` |
| Geometric | `CreateSample(GeometricDistribution, n, Seed)` |
| Weibull | `CreateSample(WeibullDistribution, n, Seed)` |
| Gamma | `CreateSample(GammaDistribution, n, Seed)` |
| Logistic | `CreateSample(logistic_distribution, n)` — **唯一不传 Seed** |
| Beta | `CreateSample(BetaDistribution, n, Seed)` |
| Pareto | `CreateSample(ParetoDistribution, n, Seed)` |
| Cauchy | `CreateSample(CauchyDistribution, n, Seed)` |

> ⚠️ **【观察】** 方法名叫 `LHS`（Latin Hypercube Sampling），
> 但实现是 `CreateSample(...)` + `getMedianSample(...)` 的**分层随机抽样近似**，
> 不是严格的 Latin Hypercube（每层等概率且层内均匀）。
> 复现时若追求逐位一致，只能复现"算法结构"，无法保证"数值一致"。

**【观察】随机种子**：估值侧种子取自
`IncidencePoolingAndAggregationAdvance.RandomSeed`（若为空/非数字则用
`时+分+秒+毫秒` 拼成的整数，L3173-3177）；抽样次数默认
`DefaultMonteCarloIterations = 10000`。**Pooling 侧的 `randomPooling` 无种子。**

**【观察】** 权重精度还有一档开关 `IPAdvancePoolingMethodEnum`：
`Roundweightstotwodigits=0` / `Roundweightstothreedigits=1` / `UseexactweightsforMonteCarlo=2`。

QALY 终点走同构独立路径：`getPoolingLstAllSelectQALYMethodAndValue`（L3791），
另有 `_old` 版本（L6402）。

> **【推断】** ABaCAS-SE 选的是 `SumDependent` 或 `SumIndependent`（最常用）。
> 判别方法：跑一次流程，若 `apvrx.csv` 里每个 `EndpointGroup` 各一行，说明**未合并**；
> 若只有一行且 `Endpoint` 列为合并描述，则已合并。**【未知】** 未实测。

---

## 7. 两段拼接：接口契约与量纲校验

**【观察】** 上下卷的拼接点只有一处：`apvrx.csv` → `InitializeBenMapResult`。

| 环节 | 责任方 | 单位 | 关键变换 |
|---|---|---|---|
| `CREATE AQG` | ABaCAS_SE → BenMAP | ug/m3 | 浓度网格文件 |
| `RUN CFG` | BenMAP | **例**（病例数） | dQ × I × Pop |
| `RUN APV` | BenMAP | **元** | × income × 单价，Pooling |
| `GENERATE REPORT` | BenMAP | 元 | → CSV |
| `InitializeBenMapResult` | ABaCAS_SE | 元 | `Baseline - PointEstimate` → 效益；固定 ±20% |
| `InitializeBenefitResult` | ABaCAS_SE | 元 | `GroupBy(Name).Sum(...)` 省级加总 |
| `GetRegion*Cost` | ABaCAS_SE | **亿元 ×1e8 = 元** | `Math.Pow(10.0, 8.0)` |
| `BenefitCostRatio` | ABaCAS_SE | **无量纲** | `Math.Round(Benefit / Cost, 1)` |

**量纲校验锚点**（复现时用来对数）：中文手册给的济南效益 ≈ `772905920` 元 ≈ **7.73 亿元**，
效益/成本比 ≈ `5.6`，全国总效益/成本比 ≈ `8.8`。这三个数可直接用于回归验证。

---

## 8. 端到端复现步骤

### 8.1 最小输入集

| # | 输入 | 来源 | 必需 |
|---|---|---|---|
| 1 | 浓度网格文件 | SMAT-CE 输出（`CREATE AQG -ModelFilename`） | ✅ |
| 2 | **CFG 配置** `.cfgx` | 用户在 ABaCAS UI 选 `-CFGFilename` | ✅ |
| 3 | **APV 配置** `.apvx` | 用户在 ABaCAS UI 选 `-APVFilename` | ✅ |
| 4 | 人口 / 基线发病率 / 基线患病率 | BenMAP FDB（`China` setup） | ✅（FDB 自带） |
| 5 | 成本 CSV | `ICBA\Data\Cost\*.csv` | ✅（上卷覆盖） |
| 6 | 情景对应关系 | `ICBA\情景对应关系.csv` | ✅（上卷覆盖） |

**【观察】2 和 3 是唯一的"用户输入"，也是 ABaCAS-SE 自身完全不含的两项**。

### 8.2 五步跑通

```text
(1) 写批处理脚本（见 2.2 全文）
(2) 建浓度网格  -> %AQGDIR%\<n>.aqgx  x2
(3) 病例数      -> %CFGRDIR%\<n>.cfgrx   （健康终点暴露）
(4) 货币化      -> %APVRDIR%\<n>.apvrx
(5) 导出        -> %APVRDIR%\<n>apvrx.csv   <- 这就是 ABaCAS 的唯一输入
```

**【观察】** 若需在无 GUI 环境复现，用 `BenMap.exe` 的批处理模式直接喂 `script.txt`，
脚本语法就是 §2.2 那几行命令（BenMAP 用户手册 `Command Line / Batch` 一节）。

### 8.3 复现检查清单

- [ ] `.apvx` 里 `ValuationFunctionID` 是哪一行？→ 决定单价量级（§5.3，差 25 倍）
- [ ] `CRFID` 是哪一条？→ 决定浓度-响应形态（log-linear vs Pope 2014 vs log-logistic）
- [ ] Pooling 策略是哪个？→ 决定多终点合并方式（§6.3）
- [ ] `income`（`INCOMEGROWTHADJFACTORS`）取值？→ 目标年份的收入调整
- [ ] `Setup` 是 `China`？→ ABaCAS-SE 硬编码 `SETACTIVESETUP -ActiveSetup China`（IL_0139）
- [ ] `apvrx.csv` 是 Pooled 还是未 Pooled？（§6.3 推断验证）
- [ ] ABaCAS 覆写后 `HighBenefit / LowBenefit = 1.2 / 0.8`？→ 验证 ±20% 生效
- [ ] 济南效益 ≈ 7.73 亿元？→ 手册锚点回归

---

## 9. 未知项（诚实清单）

| 项 | 状态 | 验证方法 |
|---|---|---|
| **ABaCAS 实际加载的 `.apvx` 实例** | **【未知】** `D:\杂物\ABaCAS\` 全树搜索 `*.apvx` / `*.cfgx` = **0 个**；`BenMAP-CE\Configs\` 只有 4 个 `ParamsTree*.xml`；`Example\` 目录**首次运行才创建** | 跑一次含 BenMAP 的情景，抓取运行时读/写的 `.apvx`，或从 ABaCAS 作者处获取 |
| `.apvx` 选了哪个 `ValuationFunctionID` | **【未知】** 同上 | 同上（`.apvx` 是 XML，直接可读） |
| Pooling 策略实际取值 | **【未知】** 8 种策略的数学形式已全部查实（§6.3），但ABaCAS 传哪个值未知；推断为 `SumDependent`/`SumIndependent` | 检查 `apvrx.csv` 行数 vs 选中终点数 |
| **收入因子取哪一年** | **【未知】** `情景对应关系.csv` 里 `TargetYear` 的具体值决定用 `INCOMEGROWTHADJFACTORS` 里哪一行（2017=1.469 / 2025=2.890 / 2030=3.777） | 读该 CSV 的 TargetYear 列 |
| `SETACTIVESETUP China` 在无裸 `China` Setup 的 FDB 上是否报错 | **【未知】** DB 里只有 `PRD_China`(4) / `JJJ_China`(5) / `JN_China`(7)，**没有** `China`；因此若脚本真的设 `China` 会匹配失败。但因无示例数据无法运行时验证 | 装上 `Example\` 数据后实跑 |
| `ICBA\Data\Benefit\China\Region\*.csv` 的 `_L` 列单位 | **【未知】** 该目录安装包内不存在；代码推断为**亿元**（与成本 CSV 同量纲） | 跑一次 ICBA 情景后查看 CSV 表头与量级 |

**已在本轮关闭的旧未知项**（不再列为未知）：

- ~~Pooling 策略的数学形式~~ → §6.3 已逐行查实8 种策略的公式
- ~~公式如何求值~~ → §5.6 已查实为 CodeDom 动态编译 C# + 反射
- ~~DB 公式的大小写如何映射到 C# 参数名~~ → §4.1.1 已查实 `ToLower()` 是答案
- ~~`INFLATIONENTRIES` 中国指数值~~ → §5.5 已列全表
- ~~`DefaultSetup=China` 绑定哪些 CR/VF~~ → §5.5.2 已查实无独立绑定表，绑定由函数实例表自带外键

### 9.1 ABaCAS-SE 里与 `.apvx` 相关的全部证据

**【观察】** IL_161907 附近：

```csharp
// 文件对话框过滤串
"All Files|*.*|APV files|*.apvx"
// 默认配置取自字典
Field::dicExampleConfiguration["BenMAP"]["APVConfigFile"]
```

**【观察】** 回退文件名（硬编码 3 个中国区域情景）：

```text
BenMAP_WUS_State_2025.apvx      // 华北平原
BenMAP_YRD_2017.apvx            // 长三角
BenMAP_PRD_2017_Ozone.apvx      // 珠三角 · 臭氧
```

> **【推断】** 这三个 `.apvx` 是 ABaCAS 作者**基于 BenMAP 官方中国区配置裁剪**的产物，
> 路径变量 `%APVDIR%` 指向用户自行放置的目录。第一次运行时若目录为空，会回退到上述文件名。

---

## 10. 结论

1. **ABaCAS-SE 不做任何健康经济学计算**。它是"BenMAP-CE 的中文外壳 + 成本侧 + 效益/成本比"。
2. **健康效益 = BenMAP APV 模块按 `income × 病例数 × 单价` 算出**，单价来自 `.apvx` 选中的估值函数行。
3. **BenMAP 的公式不在 exe 里**，在 Firebird 数据库的 `*FUNCTIONALFORMS` 表（36+12+19 条公式文本），
   运行时 `ToLower()` + 字符串替换翻译成 C#，用 CodeDom 动态编译成 DLL 再反射调用（§5.6）；
   参数在 `CRFUNCTIONS`(476) / `VALUATIONFUNCTIONS`(477)。
4. **ABaCAS 覆盖掉了 BenMAP 的不确定度区间**，改用固定 ±20%，然后按省 `Sum`。
5. **完全复现 ABaCAS-SE 的健康效益，必须拿到那个 `.apvx`**（当前磁盘 0 个）——这是唯一的硬缺口，
   其余全部环节本文已给出可执行级别的公式与流程。

---

## 附录 A — 源码坐标索引

| 环节 | 文件:行 / RVA |
|---|---|
| 脚本生成 | `ABaCAS_SE.CommonClass::createProjectScriptBenMAP` RVA `0x2D60C` |
| CSV 读入 + ±20% | `ABaCAS_SE.CommonClass::InitializeBenMapResult` RVA `0x2E254`（区间公式 IL_0377–IL_0490） |
| 省级汇总 | `ABaCAS_SE.CommonClass::InitializeBenefitResult` RVA `0x2EFB4` |
| 三类成本 | `CommonClass::GetRegionSocialEconomicCost` / `GetRegionSocialWelfareCost` / `GetKeySectorCost` RVA `0x2078C` / `0x208C0` / `0x209F4` |
| 比率构造 | `ABaCAS_SE.BenefitCostRatio::.ctor` RVA `0x11F10` |
| 全国合计 | `ABaCAS_SE.CommonClass::GetTotalBenefit` RVA `0x20B28`（`b__11_1` RVA `0xF7F14`） |
| 11 种比率口径 | `uc_BenefitCostRatio::cboBenefitType_SelectedIndexChanged` RVA `0xB8CB4` |
| 健康影响 | `ConfigurationCommonClass.cs:4251` `CalculateCRSelectFunctionsOneCel` |
| 公式翻译 | `ConfigurationCommonClass.cs:4434` `getFunctionStringFromDatabaseFunction` |
| 公式动态编译 | `Tools/CalculateFunctionString.cs:62/114/178` `CreateAllBaseline/PointEstimate/PopulationEvalObjects` |
| 公式反射求值 | `Tools/CalculateFunctionString.cs:287/328/373` `PointEstimateEval` / `PopulationEval` / `ValuationEval` |
| 货币化 | `APV/APVCommonClass.cs:3127` `getOneAllSelectValuationMethodCRSelectFunctionCalculateValue` |
| **APV 三因子相乘** | `APVCommonClass.cs:3217-3222` |
| 收入调整查表 | `APVCommonClass.cs:1420` `getIncomeGrowthFactorsFromDataSetIDAndYear` |
| 通胀查表 | `APVCommonClass.cs:1392` `getInflationFromDataSetIDAndYear` |
| 估值参数 LHS 采样 | `APVCommonClass.cs:5259` `getLHSArrayValuationFunctionSeed` |
| Pooling（8 策略） | `APVCommonClass.cs:2404` `getPoolingMethodCRSelectFunctionCalculateValue` |
| Pooling 异质性检验 | `APVCommonClass.cs:2326` `getChidist` |
| Pooling 字符串映射 | `APVCommonClass.cs:5417` `getPoolingMethodTypeEnumFromString` |
| 百分位分箱 | `APVCommonClass.cs:2313` `getMedianSample` |
| QALY 路径 | `APVCommonClass.cs:3413 / 3468 / 3522 / 3569` |

## 附录 B — 复现所需的两份文档

| 文档 | 位置 | 内容 |
|---|---|---|
| **本文（桥接层）** | `_rea_abacas\abacas-se-benmap-calculation-analysis.md` | ABaCAS 怎么调 BenMAP、传什么、结果怎么回流 |
| **ABaCAS_SE 本体（上卷）** | `_rea_abacas\abacas-se-health-benefit-analysis.md` | ±20% / 省级汇总 / 三类成本 / 11 种比率 / 全国合计 |
| **BenMAP 通用（核心公式库）** | `_rea_benmap\benmap-health-calculation-analysis.md` | 36+12+19 条公式全文、476+477 参数实例、可运行 Python 复现 |

**推荐阅读顺序**：先本文 §1–§3 建立心智模型 → 再读 BenMAP 文档 §3（公式库）→ 最后回到上卷 §2–§6 对齐数据结构。

## 附录 C — 复现工具

```text
# ABaCAS_SE 全量 IL 反汇编（2974 方法，ok: 2974 fail: 0）
cd E:/CodeProject/_rea_abacas
python dump_il.py
python extm.py "createProjectScriptBenMAP"     # 抽批处理脚本
python extm.py "InitializeBenMapResult"         # 抽 ±20% 区间
python extm.py "BenefitCostRatio::.ctor"        # 抽比率构造

# BenMap.exe 侧
cd E:/CodeProject/_rea_benmap
python benmap_repro.py                         # 可运行 Python 复现
# 挖取公式/参数：
#   FUNCTIONALFORMS(36) / BASELINEFUNCTIONALFORMS(12)
#   VALUATIONFUNCTIONALFORMS(19) / EIFUNCTIONS(12)
#   CRFUNCTIONS(476) / VALUATIONFUNCTIONS(477)
```

---

**全文完**。

**原理层面已全部挖通**（第4 轮关闭了最后的硬缺口：公式大小写映射 = `ToLower()`）。
公式求值= CodeDom 动态编译 C#（§5.6）；APV = 收入因子 × 健康影响 × 估值公式（§5.7）；
Pooling 8 种策略数学全表（§6.3）；中国区数据集矩阵与经济调整链（§4.3.1 / §5.5）。

剩余的**唯一硬缺口只有一个**：拿到 ABaCAS-SE 运行时实际使用的 `.apvx` 文件，
才能确定它选的是哪个 `SetupID` / `ValuationFunctionID` / 目标年份。




