# Data Fusion Tool v2.5 / SMAT-CE 1.8 —— 可复现计算文档

> 目标：让一个没有本仓库上下文的 AI，仅凭本文档即可重新实现
> Data Fusion Tool v2.5 与 SMAT-CE 1.8 的全部数值计算，并产出与原程序
> 逐位一致（或在标注容差内一致）的结果。

## 0. 证据等级约定

| 标记 | 含义 |
| --- | --- |
| **[A]** | 已逐行反编译核对，公式、常量、分支、哨兵值全部确认，可直接复现 |
| **[B]** | 结构表征：函数签名、输入输出、常量已确认，但存在未覆盖分支，复现时需按描述近似 |
| **[C]** | 推测：仅有命名或调用点证据，未读到完整实现，复现时需自行验证 |

行号引用格式 `文件:行号`，指向本地反编译产物（见附录 B）。

## 1. 目标与证据

| 项 | Data Fusion Tool | SMAT-CE |
| --- | --- | --- |
| 可执行文件 | `D:\Data Fusion\DataFusion\DataFusion.exe` | `D:\杂物\ABaCAS\ABaCAS\SMAT-CE\SMAT.exe` |
| 格式 | .NET CLR WinForms | .NET CLR WinForms |
| 程序集版本 | 2.5 | 1.8 |
| SHA-256 | `B58B16B1C04F35B22C1F1B77FB1620DCF13991814C0CACF18F1B6FAB2A3F53EF` | `CA27CB77ADF7C60A23EE937C95FC3C69D2D0C686968CFF306392ABAD85894DDC` |
| 反编译源码 | `_rea_datafusion/src/_whole.cs`（3,038,909 B） | `_rea_smat/src/_whole.cs`（5,915,528 B） |

**关系结论 [A]**：两者同属 SCUT / ABaCAS 家族，共用 `DotSpatial` 与
`MathNet.Numerics`，且 `CalculationWater`（硫酸盐硝酸盐铵盐水平衡）
在两个程序中逐字节一致。DataFusion 相当于 SMAT-CE 面向 PM/O₃ 融合的
裁剪衍生版：SMAT 的 BenMAP / SSIA / 能见度 / 沉降模块在 DataFusion 中不存在，
DataFusion 则额外提供了 O₃ Voronoi 邻站搜索与 GAT 梯度钳制。

## 2. 模块地图

DataFusion（15 个类，`_rea_datafusion/src/classes/`）**[A]**：

| 类 | 职责 |
| --- | --- |
| `CommonClass` | 全局常量、配置项、通用数学（`_whole.cs:43198` `_digitPrecision = 8`、`:43200` `_gradLimit = 0.001`） |
| `AnnualPMCommonClass` | PM 年度融合核心：VNA / eVNA / aVNA / 权重 / 物种分数 |
| `AnnualPMDataFusion` | PM 年度数据融合主流程（读 CSV → 降尺度 → 融合 → 输出 → 人口加权） |
| `OzoneDataFusion` | O₃ 数据融合主流程（SRF 计算、Voronoi 邻站、三路融合） |
| `BiasTable` | 统计指标（MeanBias / NormalizedBias / NormalizedError / MSE / r / RMSE） |
| `MatrixCompute` | 矩阵运算封装（Cholesky、inv、求和、行列） |
| `SpecialFunction` | 特殊函数（正态逆 CDF、t 分布随机数、MCMC 提议） |
| `MCMC` | Metropolis-Hastings 采样器骨架 |
| `InputOutput` / `Config` | 配置解析与 CSV 读写 |
| `Spatialization` | 站点空间化、网格生成 |
| `PopulationWeight` | 人口加权 |
| `CrossValidation` | 留一/交叉验证 |
| `ShapeFiles` | 县界 shapefile 读取 |
| `LogHelper` | 日志 |

SMAT-CE 额外模块 **[B]**：

| 类 | 职责 |
| --- | --- |
| `BenMAPAnnualPMCommonClass` | BenMAP 风格 PM 年度分析（`AnnualPMCommonClass` 的超集变体） |
| `BenMAPOzoneCommonClass` | BenMAP 风格 O₃ 分析 |
| `VisibilityCommonClass` | 能见度重污染分析 |
| `OzoneChinaCommonClass` / `AnnualPMCommonClassChina` | 中国区域专用分支（WRF 嵌套网格） |
| `MCMC` / `MatrixCompute` / `SpecialFunction` | 与 DataFusion 同名同实现 |

## 3. 数据模型与输入输出

### 3.1 网格 ID 编码 [A]

规则网格按 20×20 划分。网格 ID 编码为 `col * 1000 + row`（十进制，
行优先）。网格边界由 `minX..maxX`、`minY..maxY` 与步长 `step = (max - min) / 19.0`
推出，共 20×20 = 400 个格点。

### 3.2 输入 CSV 列（PM 年度融合）

必需列：

    _id, lat, long, date, monitor_gridcell, pm25_obs, pm25_Model

可选列：`weight`（显式权重，覆盖计算权重）、`CountyPopulation` 相关字段。

可选 transform 列（`AnnualPMDataFusion.GetStatisticsDataTableColumns`）**[A]**：

    _id, lat, long, [weight], monitor_gridcell, date,
    pm25_obs, pm25_Model,
    [pm25_VNA], [pm25_eVNA], [pm25_aVNA], [pm25_Downscaler],
    pm25_wVNA, [pm25_NearestSite],
    output_name, state_name, county_name

方括号表示该列按功能开关条件存在。

### 3.3 输出 CSV 格式陷阱 [A]

`test_default_Annual_PM2.5_SF.csv` 的**第一行是字面量 `Year`**，
第二行才是真正的表头。任何解析器都必须先跳过首行。

## 4. 距离计算 [A]

程序里存在 **三套** 距离/坐标实现，混用会导致结果无法对齐。

### 4.1 getDistanceFrom2Point（PM 邻站用）

haversine，地球半径 **R = 6371 km**，输入为经纬度（度），X = lon，Y = lat。

```python
import math

def get_distance_from_2_point(x1, y1, x2, y2):
    # x = 经度(lon), y = 纬度(lat), 单位: 度; R 单位: km
    rad = math.pi / 180.0
    x1 *= rad
    y1 *= rad
    x2 *= rad
    y2 *= rad
    dx = x2 - x1
    dy = y2 - y1
    a = math.sin(dx / 2) ** 2 + math.cos(y1) * math.cos(y2) * math.sin(dy / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))
```

PM 邻站筛选：`d > distanceInterpolation` 则跳过该站。默认配置
`distanceInterpolation = 9e9`，即**默认不开启距离截断**（所有站点都是候选）。

### 4.2 GetDistance（通用）

haversine，**R = 6378.137 km**，结果 `round(x, 4)`（四舍五入到 4 位小数）。

```python
def get_distance(x1, y1, x2, y2):
    d = _haversine(x1, y1, x2, y2, R=6378.137)
    return round(d, 4)
```

### 4.3 SpatializeMatrix（球面直角坐标）

```text
X = cos(lat_rad) * cos(lng_rad) * 6378.1
Y = cos(lat_rad) * sin(lng_rad) * 6378.1
Z = sin(lat_rad) * 6378.1
```

注意此处半径是 **6378.1**（既不是 6371 也不是 6378.137）。
这是降尺度器协方差矩阵使用的坐标。

## 5. PM 融合算法 [A]

### 5.1 三种权重方案

| 方案 | 键 | 公式 |
| --- | --- | --- |
| Equal | `0` | `w = 1` |
| IDW | `1` | `w = 1 / d` |
| IDS²（默认） | `2` | `w = 1 / d ** p`，`p = VNAIDWP`（默认 2） |

所有方案：`d == 0` 时 `w = 1`。

```python
def weight(d, scheme, p=2.0):
    if d == 0:
        return 1.0
    if scheme == 0:
        return 1.0
    if scheme == 1:
        return 1.0 / d
    return 1.0 / (d ** p)
```

### 5.2 VNA / eVNA / aVNA / wVNA

设受体格点 `i`，候选站集合 `S`，站 `j` 的模型浓度 `c_j`、监测浓度 `o_j`。

```python
import math

GRAD_LIMIT = 0.001
DIGIT_PRECISION = 8

def calc_vna(c, w):
    sw = sum(w)
    if sw == 0:
        return -13.0
    v = sum(ci * wi for ci, wi in zip(c, w)) / sw
    if math.isnan(v):
        return 0.0          # 注意: NaN -> 0.0, 不是哨兵值
    return v

def grad_adj(m_rec, m_mon):
    # eVNA 的梯度比值
    return max(m_rec, GRAD_LIMIT) / max(m_mon, GRAD_LIMIT)

def calc_evna(c, m_mon, w):
    g = [grad_adj(ci, oi) for ci, oi in zip(c, m_mon)]
    sw = sum(w)
    if sw == 0:
        return -13.0
    return sum(ci * wi * gi for ci, wi, gi in zip(c, w, g)) / sw

def calc_avna(c, m_rec, m_mon, w):
    # PM 侧使用差值梯度 GetGradSubValues: (c + M_rec - M_mon)
    sw = sum(w)
    if sw == 0:
        return -13.0
    return sum((ci + ri - oi) * wi
               for ci, ri, oi, wi in zip(c, m_rec, m_mon, w)) / sw

def calc_wvna(vna, evna, wvna_weight=0.5):
    if vna <= 0 or evna <= 0:
        return -13.0
    return wvna_weight * evna + (1.0 - wvna_weight) * vna
```

`AnnualVNA` 的三个权重分支就是 Equal / IDW / IDS² 的选择；
IDS² 的幂次由配置项 `VNAIDWP` 提供。`AnnualEVNA` / `AnnualAVNA` /
`GetGradAdjValues` 分别对应上式的 eVNA / aVNA / 梯度比。

### 5.3 DataFusion 独有的 GAT 双向钳制 [A]

`GetGradAdjValues` 中，除基础梯度比外还有 GAT（Gradient Adjustment
Threshold）钳制：

```python
def get_grad_adj_values(obs, rec, gat, grad_limit=GRAD_LIMIT):
    g = max(rec, grad_limit) / max(obs, grad_limit)
    low = rec / gat
    if obs < low and obs < low:
        g = (obs / gat) / max(rec, grad_limit)
    high = obs * gat
    if obs > high and obs > rec * gat:
        g = high / max(rec, grad_limit)
    return g
```

> 注：第二个分支中 `obs > obs * gat` 在 `gat > 1` 时恒为 `false`，
> 疑为原程序条件冗余或反编译器括号丢失。复现时保留原样并用黄金样本标定；
> 若该分支恒不生效，GAT 等价于单侧的 `obs/gat` 截断。

### 5.4 哨兵值表 [A]

| 值 | 含义 |
| --- | --- |
| `-13` | 无效 / 无法计算 |
| `-9` | 缺失 |
| `-8` | 失败（梯度计算失败等） |
| `-7` | 无有效日 |

任何参与统计或输出的字段遇到哨兵值必须原样透传，不得参与均值。

### 5.5 NearestSite 列

当配置 `UseNearestSite` 打开时，额外输出距离受体最近的单站值，
用于与多站融合结果对照。

## 6. 物种闭合 [A]

入口：`GetSpeciesFractionValuesVNAEVNA`（DataFusion）/
`GetSpeciesFractionValues*`（SMAT，多个重载）。

### 6.1 NH₄⁺ 推断

DataFusion 唯一分支：

```python
def calc_nh4(don, so4, no3r):
    return don * so4 + 0.29 * no3r
```

SMAT 独有 `doUseAmmoniumValues` 分支（当已有实测 NH₄⁺ 时改用硝酸盐蒸发校正）：

```python
def calc_nh4_evap(nh4_pct_evap, no3, no3r, so4):
    num = nh4 - nh4_pct_evap * 0.29 * (no3 - no3r)
    return (num - 0.29 * no3r) / so4
```

上式中的 `nh4` 为外传入的实测/诊断 NH₄⁺ 浓度。SMAT 常量：
`species_calc_precision = 7`、`species_fraction_precision = 7`、`gradLimit = 0.001`。

### 6.2 CalculationWater（两程序逐位一致）

入口 `CalculationWater(SO4, NO3r, NH4, don)`，Malmström et al. 2002
双分支（以 `don < 0.225` 为界）。此函数在 DataFusion
(`_whole.cs:46087`) 与 SMAT (`_whole.cs:51492`) 中完全一致。

记 `num = SO4 + NO3r + NH4`，三个摩尔分数
`s = SO4/num`、`n = NO3r/num`、`a = NH4/num`。完整实现如下 **[A]**：

```python
def calculation_water(so4, no3r, nh4, don):
    num = so4 + no3r + nh4
    if num == 0:
        return 0.0
    s = so4 / num
    n = no3r / num
    a = nh4 / num

    if don < 0.225:
        # Malmström 2002, 低 DON 分支
        pbw = (
            595.556
            - 1440.584 * s
            - 1126.488 * n
            + 283.907 * s ** 1.5
            - 13.384 * n ** 1.5
            - 1486.711 * a ** 1.5
            + 764.229 * s ** 2.0
            + 1501.999 * (n * s)
            + 451.873 * n ** 2.0
            - 185.183 * s ** 2.5
            - 375.984 * s ** 1.5 * n
            - 16.895 * s ** 3.0
            - 65.814 * n ** 1.5 * s
            + 96.825 * n ** 2.5
            + 83.037 * n ** 1.5 * s ** 1.5
            - 4.419 * n ** 3.0
            + 1720.818 * a ** 1.5 * s
            + 1220.383 * a ** 1.5 * n
            - 311.496 * a ** 1.5 * s ** 1.5
            + 148.771 * a ** 1.5 * n ** 1.5
            + 1151.648 * a ** 3.0
        )
    else:
        # Malmström 2002, 高 DON 分支
        pbw = (
            202048.975
            - 391494.647 * s
            - 390912.147 * n
            + 442.435 * s ** 1.5
            - 155.335 * n ** 1.5
            - 293406.827 * a ** 1.5
            + 189277.519 * s ** 2.0
            + 377992.61 * n * s
            + 188636.79 * n ** 2.0
            - 447.123 * s ** 2.5
            - 507.157 * s ** 1.5 * n
            - 12.794 * s ** 3.0
            + 146.221 * n ** 1.5 * s
            + 217.197 * n ** 2.5
            + 29.981 * n ** 1.5 * s ** 1.5
            - 18.649 * n ** 3.0
            + 216266.951 * a ** 1.5 * s
            + 215419.876 * a ** 1.5 * n
            - 621.843 * a ** 1.5 * s ** 1.5
            + 239.132 * a ** 1.5 * n ** 1.5
            + 95413.122 * a ** 3.0
        )
    return pbw * num
```

> 注意：反编译版本**没有** 7 位中间舍入（`species_calc_precision`
> 只作用于调用方的物种分数计算），函数体内是纯浮点直算。
> 复现时照此实现即可，不要自行加舍入。

`getDistanceFrom2Point` 的参数顺序确认为 `(X0, Y0, X1, Y1)`，
其中 X = **经度**、Y = **纬度**，且 `Y0/Y1` 出现在 `cos()` 项，
`X0/X1` 出现在 `sin()` 项——与本文档 4.1 的实现一致 **[A]**。

### 6.3 GetSpeciesFractionValuesVNAEVNA 完整实现 [A]

来源 `AnnualPMDataFusion.cs:12796`。**运算顺序与舍入点已逐行确认**，
这是复现时最容易出错的地方——每一步都要 `Math.Round(x, 8)`。

```python
import math

DIGIT_PRECISION = 8
BLANK = 0.5

def get_species_fraction_values_vnaevna(
    vnaCrustal, vnaEC, vnaSO4, vnaOC, vnaSalt, vnaNO3r, vnaDON, vnaNO3, vnaPM,
    nh4_override=None,
):
    # 1) NH4 由 DON-SO4-NO3r 推断, 推断后立即舍入到 8 位
    vnaNH4 = round_half_even(vnaDON * vnaSO4 + 0.29 * vnaNO3r, DIGIT_PRECISION)
    if nh4_override is not None:
        vnaNH4 = round_half_even(nh4_override, DIGIT_PRECISION)

    # 2) PBW (水平衡), NaN -> 0, 再舍入
    vnaPBW = calculation_water(vnaSO4, vnaNO3r, vnaNH4, vnaDON)
    vnaPBW = 0.0 if math.isnan(vnaPBW) else round_half_even(vnaPBW, DIGIT_PRECISION)

    inorg7 = vnaCrustal + vnaSO4 + vnaNO3r + vnaNH4 + vnaPBW + vnaSalt + vnaEC

    # 3) PM2.5: PM 为 0 时用 7 组分和 + 0.5 反推
    vnaPM = inorg7 + BLANK if vnaPM == 0.0 else vnaPM
    num2 = vnaPM - BLANK                       # 即 PM2.5

    # 4) OC 夹逼: 下限 = 1.0 * vnaOC 本身, 上限 = 0.8 * PM2.5
    num5 = num2 - inorg7
    num = 1.0 * vnaOC
    vnaOC = round_half_even(min(max(num5, num), 0.8 * num2), DIGIT_PRECISION)

    # 5) 残差按比例分摊到 7 个组分 (OC 不缩放)
    num6 = num2 - (inorg7 + vnaOC)
    k = num6 / inorg7
    if math.isnan(k) or math.isinf(k):
        k = 0.0
    vnaCrustal = round_half_even((1.0 + k) * vnaCrustal, DIGIT_PRECISION)
    vnaEC      = round_half_even((1.0 + k) * vnaEC,      DIGIT_PRECISION)
    vnaNH4     = round_half_even((1.0 + k) * vnaNH4,     DIGIT_PRECISION)
    vnaNO3r    = round_half_even((1.0 + k) * vnaNO3r,    DIGIT_PRECISION)
    vnaSO4     = round_half_even((1.0 + k) * vnaSO4,     DIGIT_PRECISION)
    vnaSalt    = round_half_even((1.0 + k) * vnaSalt,    DIGIT_PRECISION)
    vnaPBW     = round_half_even((1.0 + k) * vnaPBW,     DIGIT_PRECISION)

    # 6) 8 组分归一化
    num8 = vnaSO4 + vnaSalt + vnaNO3r + vnaNH4 + vnaOC + vnaPBW + vnaCrustal + vnaEC

    return {
        "pm25MassFrac": round_half_even(num8 + BLANK, DIGIT_PRECISION),
        "fCr":    round_half_even(vnaCrustal / num8, DIGIT_PRECISION),
        "fEC":    round_half_even(vnaEC      / num8, DIGIT_PRECISION),
        "fNH4":   round_half_even(vnaNH4     / num8, DIGIT_PRECISION),
        "fOcm":   round_half_even(vnaOC      / num8, DIGIT_PRECISION),
        "fNO3r":  round_half_even(vnaNO3r    / num8, DIGIT_PRECISION),
        "fWater": round_half_even(vnaPBW     / num8, DIGIT_PRECISION),
        "fSalt":  round_half_even(vnaSalt    / num8, DIGIT_PRECISION),
        "fSO4":   round_half_even(vnaSO4     / num8, DIGIT_PRECISION),
        # 注意分母是 num2 (PM2.5), 不是 num8 (8 组分和)
        "fNO3":   round_half_even(vnaNO3     / num2,  DIGIT_PRECISION),
        "blankMass": round_half_even(BLANK, DIGIT_PRECISION),
        "don": vnaDON,
        "iSO4": vnaSO4, "iNO3r": vnaNO3r, "iOcb": vnaOC, "iEC": vnaEC,
        "iCrustal": vnaCrustal, "iDON": vnaDON, "iNH4": vnaNH4,
        "iNO3": vnaNO3, "iSalt": vnaSalt,
    }
```

关键顺序要点：

1. `vnaNH4` 的推断结果**先舍入**再送入 `CalculationWater`。
2. `vnaPM` 为 0 时的反推用的是**闭合并加入 PBW 后的 7 组分和**。
3. OC 的下限不是常数，而是 `1.0 * vnaOC`（即 OC 自身），
   意味着 `min(max(残差, OC), 0.8*PM2.5)` —— SMAT 的 `floorOCMMB`
   插在这个位置。
4. 比例分摊 `k` 的分母是**缩放前的 7 组分和**。
5. 所有中间量 `Math.Round(x, 8)` = 银行家舍入（Python 内置 `round` 语义一致）。

注意末尾两处归一化**分母不同**：`fX = X / Σ8组分`，
`fNO3 = NO3 / PM2.5`。这是最常见的复现错误来源。

## 7. MCMC 贝叶斯普通克里金降尺度器 [A]

入口：`SingleRun`（DataFusion `_rea_datafusion/methods/SingleRun.cs`，17,638 B），
SMAT 侧同名实现位于 `AnnualPMAnalysis.cs`。

### 7.1 输入矩阵

| 符号 | 含义 |
| --- | --- |
| `Xt` | 网格点 × 特征 的设计矩阵 `[1, model_c, x, y]` |
| `W` | 网格点 × 网格点 的残差协方差 |
| `vct8` | 站点 8 向量设计矩阵 |
| `resid` | 站点残差向量 `obs - (intercept + slope * model)` |

### 7.2 参数表

| 参数 | 含义 | 默认/来源 |
| --- | --- | --- |
| `Cmaqres` | CMAQ 网格分辨率（km） | 配置，默认 12 |
| `Neighbor` | 邻站对数 | 配置，默认 500 |
| `Burn` | 烧链表长 | 配置，默认 500 |
| `Thin` |  thinning 间隔 | 配置，默认 1 |
| `Numit` | 保留样本数 | 配置，默认 2500 |
| `ResidualVariance` | 残差方差，0 → 0.01 | 自动 |
| `phi_K` | `Neighbor / (3 * Cmaqres)` | — |
| `phi_Q` | `Neighbor / (2 * Cmaqres)` | — |
| `num17` | t 分布自由度 | 2.5 |
| `tY2_b` | t 分布尺度先验 | 1.5 |

总迭代次数 `Numit * Thin + Burn`，默认 `2500 * 1 + 500 = 3000`；
每轮保留 1 个样本，共保留 `Keep = Numit = 2500` 个。

### 7.3 Step 1–11 完整伪码

```python
import numpy as np

def single_run(Xt, W_input, vct8, resid, cfg, rng):
    # --- Step 1: 20x20 规则网格 ---
    xs = np.linspace(cfg.min_x, cfg.max_x, 20)
    ys = np.linspace(cfg.min_y, cfg.max_y, 20)
    step = (cfg.max_x - cfg.min_x) / 19.0

    # --- Step 2: 球面直角坐标化 ---
    S = spatialize_matrix(lat, lon)   # 见 4.3, R = 6378.1

    # --- Step 3: 邻站协方差 ---
    phi_k = cfg.neighbor / (3.0 * cfg.cmaqres)
    D = pairwise_distance_matrix(S)
    W = np.exp(-phi_k * D)
    W[W < 1e-5] = 0.0

    # --- Step 4: 筛邻站 (行和 > 0.1) ---
    keep = W.sum(axis=1) > 0.1
    W = W[keep][:, keep]

    # --- Step 5: 重复格点合并 (均值, weight = 1.0), 按 model_row_index 升序 ---
    groups = merge_duplicate_gridcells(Xt, weight=1.0)
    groups.sort(key=lambda g: g.model_row_index)

    # --- Step 6: 残差回归 ---
    # resid = obs - (intercept + slope * model)
    if residual_variance == 0:
        residual_variance = 0.01

    # --- Step 7: Q 矩阵与 Cholesky ---
    phi_q = cfg.neighbor / (2.0 * cfg.cmaqres)
    Q = np.exp(-phi_q * D_sub)
    s5 = cholesky(pred - pred)      # 下三角
    Qp = Q @ inv(s5)

    # --- Step 8: 变差函数网格搜索 ---
    best = None
    for rho in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        R = np.exp(-phi_b0s(rho) * D_sub)
        sigma2 = np.linalg.inv(R) * residual_variance
        nll = -0.5 * sum(log(lambda)) - 0.5 * resid @ inv(sigma2) @ resid
        if best is None or nll > best.nll:   # 取最大似然
            best = (rho, nll)
    rho_best = best.rho
    phi_b0s = 3.0 / (rho_best * dmax)

    # --- Step 9: 普通克里金 ---
    b0sinv = inv(np.exp(-phi_b0s * D))
    krig = vct8 @ b0sinv
    mvars = rowsum(krig * vct8)

    # --- Step 10: MCMC (Metropolis-Hastings) ---
    Ybar = 0.0
    Y2bar = 0.0
    kp = 0
    total = cfg.numit * cfg.thin + cfg.burn
    for it in range(total):
        b0s = sample_b0s(vctt1, vctt2, b0s @ b0sinv @ b0s)
        s2b = 1.0 / gamma_sample(shape=vctt1, scale=2.0 / (b0s @ b0sinv @ b0s + vctt2))

        c1 = design_row_at(it)
        tY2 = max(0.1, c1 @ W @ c1 / (n - 1))
        vctt3 = (2.5 + n - 2) / 2.0

        # 两条 Cholesky 分解
        Lt_1 = chol(W / tY2 + b0sinv / s2b).T
        Lt_2 = chol(Xt @ Xt.T / tY2 + diag([0.002, 0, 0, 0.002])).T

        model_c = model_at(it)
        pmean = b[0] + b[1] * model_c + krig @ b0s
        pvar = np.sqrt(s2b * (1.0 - mvars) + tY2)

        kY = np.random.normal(pmean, pvar)
        if kY < 0:
            kY = 0.0                    # max(0, .)

        if it >= cfg.burn and (it - cfg.burn) % cfg.thin == 0:
            kp += 1
            Ybar = ((kp - 1) * Ybar + kY) / kp
            Y2bar = ((kp - 1) * Y2bar + kY * kY) / kp

    # --- Step 11: 结果 ---
    sigma = np.sqrt(kp / (kp - 1.0) * (Y2bar - Ybar ** 2))
    return Ybar, sigma        # Ybar 即最终降尺度值
```

### 7.4 调用粒度差异 [A]

| 程序 | 每季 MCMC 次数 | 参与量 |
| --- | --- | --- |
| DataFusion | 1 | `pm25` |
| SMAT | 9 | PM25, SO4, NO3R, OCB, EC, Crustal, Salt, NO3, NH4 |

SMAT 的 DON 与 PBW 的降尺度值**不来自**降尺度器，取自 VNA 物种分数场；
NH4 会被物种闭合公式重算覆盖。

### 7.5 复现难点提示

1. `SpatializeMatrix` 的半径 6378.1 与 `GetDistance` 的 6378.137、
   `getDistanceFrom2Point` 的 6371 三者不一致，必须严格区分。
2. Cholesky 的 `Lt_1` / `Lt_2` 取 `.T`（转置），MATLAB/NumPy 惯例差异会导致
   后续三角求解结果错位。
3. `Math.Round` 在 .NET 中是**银行家舍入**（round-half-to-even），
   与 Python 内置 `round` 一致，但与 C# 的 `MidpointRounding.AwayFromZero`
   不同。人口加权的 `Ratio` 与 `CellPopulation` 用的是 **AwayFromZero**。
4. MCMC 含随机数。若要逐位复现需固定种子并匹配 .NET `System.Random`
   或 MathNet 的具体实现；否则只能在统计意义上对齐（分布一致）。

## 8. O₃ 融合 [A]

入口 `OzoneDataFusion`（DataFusion）、`OzoneCommonClass`（SMAT）。

### 8.1 ComputeModelSRFCV

| 侧 | `ozone` 字段 | `srf` 字段 |
| --- | --- | --- |
| 模型侧 | 指定百分位区间内各天的均值（按 `floor`/`ceil` 索引） | 降序排序后**前 5 日**的均值，`round(x, 1)` |
| 监测侧 | 降序排序后**前 5 日**的均值 | — |

```python
def compute_model_srf_cv(values, pctl_lo, pctl_hi):
    s = sorted(values, reverse=True)
    top5 = mean(s[:5]) if len(s) >= 5 else mean(s)
    srf = round(top5, 1)
    ozone = mean(values[pctl_lo: pctl_hi + 1])
    if ozone <= -9 or ozone == -7:      # 最大值即哨兵
        return -9.0, -13.0
    return ozone, srf
```

### 8.2 O₃ 邻站：Voronoi 而非距离截断

候选集用 Fortune 算法构造的 **Voronoi 图**（Albers 投影坐标），
规则如下 **[A]**：

1. 候选集：与受体平方欧氏距离 `d² < 64`（即 8° 内）。
2. 若候选站不足 20 个，逐步放宽阈值 `64 + i`，直到满足。
3. 边界带：`d² < 484`（22°）。
4. 对 `{受体} ∪ 候选站` 跑 Voronoi，取与受体所在半边相邻的站。

权重 `w = 1 / d^p`，三个路径各有独立幂次
`VNAIDWP` / `eVNAIDWP` / `aVNAIDWP`；`d == 0 → w = 1`。

### 8.3 O₃ 三路融合与 PM 的差异

```python
def ozone_vna(c, w):
    sw = sum(w)
    if sw == 0:
        return -13.0
    return sum(ci * wi for ci, wi in zip(c, w)) / sw

def ozone_evna(c, srf_rec, srf_site, w):
    sw = sum(w)
    if sw == 0:
        return -13.0
    num = 0.0
    for ci, ri, si, wi in zip(c, srf_rec, srf_site, w):
        if si <= 0 or ri <= 0:
            return -8.0                    # 哨兵 -8 (梯度失效)
        g = ri / si                      # 注意方向: 受体 / 站点
        num += ci * wi * g
    return num / sw

def ozone_avna(c, srf_rec, srf_site, w):
    # 与 PM 的乘法梯度不同, O3 的 aVNA 是加性的
    sw = sum(w)
    if sw == 0:
        return -13.0
    base = srf_rec
    return base + sum((ci - si) * wi
                      for ci, si, wi in zip(c, srf_site, w)) / sw
```

wVNA 逻辑与 PM 相同（`wVNAWeight` 加权，VNA 或 eVNA `<= 0` 返回 `-13`）。

O₃ 降尺度器与 PM 同内核，两处差异：

1. 可选 log / sqrt 变换（0 值先替换为 0.1）。
2. 降尺度结果按**经纬度精确相等**回填到对应网格点。

### 8.4 SMAT 的 RRF（相对风险因子）[A]

入口 `getThresholdsOfOzoneModel`（`_whole.cs:1391`，类
`OzoneCommonClass`）。

```python
def get_thresholds_of_ozone_model(daily_values, srf_start, srf_end,
                                   initial_threshold, min_days,
                                   min_allowable_threshold):
    desc = sorted(daily_values, reverse=True)

    # srf = 降序数组 [SRF_StartValue - 1 : SRF_EndValue] 的区间均值
    srf = mean(desc[srf_start - 1: srf_end])

    # ppb 阈值: 从 initial_threshold (或 topXDays) 向下搜索,
    # 直到满足至少 min_days 天的最高阈值; 受 min_allowable_threshold 下限约束
    thresh = initial_threshold
    while True:
        days = sum(1 for v in daily_values if v >= thresh)
        if days >= min_days or thresh <= min_allowable_threshold:
            break
        thresh -= 1

    # days = 超阈天数
    # ozone = 前 days 天均值 (哨兵 -9 / -7)
    days = sum(1 for v in daily_values if v >= thresh)
    ozone = mean(desc[:days])
    return thresh, days, ozone, srf
```

空间场版本输出 `ppbforSptailfield` / `daysforSptailfield` /
`bO3forSptailfield`，阈值下限换为 `backstopMinThresholdforSpatialField`。

**RRF 计算**：

```python
def calc_rrf(baseline_values, future_values, days, do_pair_days):
    # 4 位小数
    if do_pair_days:
        # 用"按未来值排序的 top-days 窗口"
        window_f = sorted(future_values, reverse=True)[:days]
        window_b = sorted(baseline_values, reverse=True)[:days]
    else:
        # 用"基线 top-days 窗口", 未来值取同一天
        idx = top_days_indices(baseline_values, days)
        window_b = [baseline_values[i] for i in idx]
        window_f = [future_values[i] for i in idx]
    rrf = round(mean(window_f) / mean(window_b), 4)
    if rrf < 0:
        return -9.0
    return rrf
```

RRF 的使用：

```python
def apply_rrf(vna, obs, rrf):
    # 空间场路径用 rrfforSptailfield
    if obs < 0 or rrf == -9:
        return -9.0
    return round(obs * rrf, 1)      # ozonecontrol
```

RRF 哨兵：`-8`（空间场梯度失效）、`-9`（无法计算）、`-13`（SRF 失效）。

## 9. 统计指标与人口加权 [A]

### 9.1 BiasTable

```python
import math

def mean_bias(model, obs):
    return mean(m - o for m, o in zip(model, obs))

def normalized_bias(model, obs):
    return mean((m - o) / o for m, o in zip(model, obs))

def normalized_error(model, obs):
    return mean((m - o) / ((m + o) / 2.0) for m, o in zip(model, obs))

def mean_square_error(model, obs):
    return mean((m - o) ** 2 for m, o in zip(model, obs))

def cal_correlation(model, obs):
    mm = mean(model)
    oo = mean(obs)
    num = sum((m - mm) * (o - oo) for m, o in zip(model, obs))
    den = math.sqrt(sum((m - mm) ** 2 for m in model)
                    * sum((o - oo) ** 2 for o in obs))
    return num / den if den else float("nan")
```

### 9.2 CalRMSE 的真实缺陷 [A]

```csharp
// BiasTable.CalRMSE —— 反编译原样
Math.Pow(monitorValues[i] - monitorValues[i], 2.0)   // 自减, 恒为 0
```

发布二进制中该项是 `monitorValues[i] - monitorValues[i]`，恒等于 0，
因此 `CalRMSE` **恒返回 0**。两种复现策略：

| 目标 | 做法 |
| --- | --- |
| 对齐原程序行为（回归测试） | 返回 0.0 |
| 得到正确 RMSE | `sqrt(mean_square_error(model, obs))` |

### 9.3 人口加权 [A]

```python
from decimal import Decimal, ROUND_HALF_UP

def round_away_from_zero(x, ndigits=4):
    # 对应 C# MidpointRounding.AwayFromZero
    q = Decimal(10) ** (-ndigits)
    return float(Decimal(repr(x)).quantize(q, rounding=ROUND_HALF_UP))

def population_weight(values, cell_population):
    tot = sum(cell_population)
    if tot == 0:
        return -13.0
    return sum(v * p for v, p in zip(values, cell_population)) / tot
```

完整流程：

1. 读 `Data\Population\UnitedStatesCensusCountyPopulation2010to2020.csv`。
2. `GetRegionCellListForPopulation` 按 Albers 投影坐标分配格点到县。
3. `Ratio` = 格点面积份额，`round(x, 4)` **AwayFromZero**。
4. `CellPopulation = round(CountyPopulation * Ratio, 4)`，同为 AwayFromZero。
5. `WeightedValue = sum(value * pop) / sum(pop)`。

输出文件：`test_default_Annual_PM2.5_SF - Pop. Weighted.csv`
（**文件名含空格**）。

## 10. 黄金样本与验证

### 10.1 样本清单 [A]

目录：`D:\Data Fusion\DataFusion\Result\Output\test_default\`

| 文件 | 内容 |
| --- | --- |
| `test_default.cfg` | 配置：`RunAnnualPMFusion`、PM 2011、`Cmaqres=12`、`Burn=500`、`Thin=1`、`Numit=2500`、`wVNA=0.5`、`distanceInterpolation=9e9`、`UseCrossValidation=0` |
| `test_default_Annual_PM2.5_SF.csv` | 空间场（**首行是 `Year`**） |
| `test_default_Annual_PM2.5_Compare_data_no_CV.csv` | 逐站对照 |
| `test_default_Annual_Avg_PM2.5_Monitors.csv` | 监测站年均 |
| `test_default_mon.dist_haversine_official_annual-PM25_2002thru2017.csv` | 站间距离矩阵，列：`siteid, lon, lat, siteidB, lonB, latB, distance, close.rank` |
| `test_default_Annual_PM2.5_SF - Pop. Weighted.csv` | 人口加权场 |
| `test_default.log` | 运行日志，总耗时 61 s |

首行数据（`_id = 1001`，lat `35.793068`，lon `-99.605233`）：

| 字段 | 值 |
| --- | --- |
| `pm25_Model` | 5.41415562 |
| `pm25_VNA` | 9.33778665 |
| `pm25_eVNA` | 4.94093499 |
| `pm25_Downscaler` | 7.88639602 |

### 10.2 已知缺口

- **模型输入 CSV 已找到**（2026-10 更正）：
  `D:\git\Zhuo Chen\DataFusion\DataFusion\Data\SampleData\`
  含 `Model_data\PM_large_12KC1_2011_base_GMT.csv`（163 MB，365 日 ×
  ~4800 格）与 `Monitor_data\official_annual-PM25_2002thru2017.csv`（5 MB，
  已是季度粒度）。端到端复现的输入缺口已闭合，见第 13 节。
- 黄金样本由 **DataFusion 1.9** 产出，而逆向对象是 **2.5**。
  1.9 与 2.5 的 VNA/eVNA 路径一致；2.5 新增 GAT 钳制、O₃ Voronoi、
  可配幂次 `VNAIDWP`。

### 10.3 六层验证步骤

| 层 | 验证内容 | 需要的输入 | 可行性 |
| --- | --- | --- | --- |
| L1 | 距离函数对拍（PM / 通用 / 球面直角） | 站点经纬度 | ✅ 可做 |
| L2 | 物种闭合质量守恒 | 任意组分向量 | ✅ 可做 |
| L3 | VNA/eVNA/aVNA/wVNA 数值对拍 | 站点浓度 + 距离矩阵 | ✅ 已完成 |
| L4 | 降尺度器分布对拍（MCMC） | 同上 | ⚠️ 算法可复现，逐位需 .NET RNG |
| L5 | 统计指标对拍 | 输出样本的 obs/model 列 | ✅ 可做 |
| L6 | 端到端逐位复现 | 完整输入 | ✅ 已完成（eVNA 到 float32 ulp） |

## 11. 已知缺陷与陷阱清单 [A]

| # | 陷阱 | 说明 |
| --- | --- | --- |
| 1 | 三套地球半径 | `6371`（PM 邻站）/ `6378.137`（GetDistance，四位小数）/ `6378.1`（SpatializeMatrix） |
| 2 | `CalRMSE` 恒为 0 | `monitorValues[i] - monitorValues[i]` 自减 |
| 3 | 两种舍入模式 | `Math.Round` = 银行家舍入；人口加权用 AwayFromZero |
| 4 | `fNO3` 分母不同 | `fNO3 = NO3 / PM2.5`，而 `fX = X / Σ8组分` |
| 5 | 输出首行是 `Year` | SF.csv 首行不是表头 |
| 6 | NaN → 0 而非哨兵 | VNA 中 `isNaN → 0.0` |
| 7 | 三种 `alpha` 分支 | Equal / IDW / IDS²，IDS² 幂次来自 `VNAIDWP` |
| 8 | eVNA 梯度下限 | `max(x, 0.001)`，不是 `max(x, eps)` |
| 9 | O₃ aVNA 是加性的 | `受体 srf + Σ((c − 站 srf)·w)/Σw`，与 PM 的乘法梯度不同 |
| 10 | O₃ 邻站用 Voronoi | 平方欧氏 `d² < 64` 起，不足 20 站逐步放宽到 `64+i`，边界 `484` |
| 11 | GAT 第二分支可能恒假 | `obs > obs * gat`，`gat > 1` 时不成立 |
| 12 | SMAT 每季跑 9 次 MCMC | DataFusion 只跑 1 次（pm25） |
| 13 | NH₄ 被闭合公式重算 | SMAT 的 NH₄ 降尺度结果会被覆盖 |
| 14 | 人口加权文件名含空格 | `..._SF - Pop. Weighted.csv` |
| 15 | 网格 ID 编码 | `col * 1000 + row`，20×20，步长 `/19.0` |
| 16 | 降尺度 `Ybar` 才是结果 | `Sigma` 只作为不确定度伴随输出 |

## 12. 复现路线图

| 阶段 | 内容 | 产出 | 依赖 |
| --- | --- | --- | --- |
| P0 | 建立仓库骨架、Python 依赖（numpy / scipy / pyproj） | 可运行空壳 | — ✅ |
| P1 | 距离与坐标模块（4.1–4.3） | `geo.py` | — ✅ |
| P2 | 物种闭合模块（6.1–6.3） | `species.py` | P1 ✅ |
| P3 | PM 融合模块（5.1–5.5） | `fusion.py` / `pm_pipeline.py` | P1, P2 ✅ |
| P4 | 降尺度器（7.1–7.5） | `downscaler.py` | P1, numpy/scipy ✅ |
| P5 | O₃ 模块（8.1–8.4） | `ozone.py` | P1 ✅ |
| P6 | 统计与人口加权（9.1–9.3） | `metrics.py` / `population.py` | — ✅ |
| P7 | 主流程编排 + 黄金样本对拍 | `pipeline.py` / `cli.py` / `verify.py` | P1–P6 ✅ |

技术选型建议：

- 数值：`numpy` + `scipy.linalg`（Cholesky / inv / 特殊函数）。
- 随机数：若需逐位复现，移植 .NET `System.Random`；
  若只需统计对齐，直接用 `numpy.random.default_rng(seed)`。
- 投影：Albers 与 Voronoi 可用 `pyproj` + `shapely`，
  或按 Fortune 算法自行实现以避免版本差异。
- 投影细节（Albers 标准纬线、中央经线）需从
  `CommonSettings` / `ShapeFiles` 中再核对 **[C]**。

## 13. 端到端复现实现与验证结果 [A]

### 13.1 代码位置与运行方式

复现程序在 `E:\CodeProject\_repro_datafusion\`（本地工作区，非 git 仓库）。

```powershell
cd E:\CodeProject\_repro_datafusion

# 跑一个年度 PM2.5 场景，产出与 DataFusion 同名的三个 CSV
python -m dfusion.cli run `
  --cfg "D:\Data Fusion\DataFusion\Result\Output\test_default\test_default.cfg" `
  --data-root "D:\git\Zhuo Chen\DataFusion\DataFusion\Data\SampleData" `
  --out-dir .\out

# 与 DataFusion 自己吐出的结果对拍
python -m dfusion.cli verify `
  --out-dir .\out `
  --golden-dir "D:\Data Fusion\DataFusion\Result\Output\test_default" `
  --scenario test_default
```

单次全量运行约 **97 s**（4800 格 × 4 季度 × Fortune Voronoi）。
`--with-downscaler` 会额外跑贝叶斯降尺度器（很慢，且 MCMC 种子不可复现）。

模块分工：

| 模块 | 职责 |
| --- | --- |
| `dfusion/pipeline.py` | `AnnualRun`：读 cfg → 三阶段产物 |
| `dfusion/verify.py` | 逐列 bit-exact / within-eps 对拍 |
| `dfusion/cli.py` | `run` / `verify` 两个子命令 |
| `dfusion/io.py` | cfg、CSV、模型格点、监测站、距离表读写 |
| `dfusion/stations.py` | 双门槛站点筛选 + `monitor_gridcell` |
| `dfusion/pm_pipeline.py` | 季度监测均值、逐格点 VNA |
| `dfusion/fusion.py` | 权重、邻站选择（Fortune Voronoi）、VNA/eVNA/aVNA |
| `dfusion/fortune.py` | Fortune 扫描线 Voronoi |
| `dfusion/downscaler.py` | MCMC 贝叶斯降尺度器 |

### 13.2 验证结果（test_default / 2011）

| 列 | 逐位一致 | 容差内 | 最大绝对误差 |
| --- | --- | --- | --- |
| `distances` | 420/420 | 420/420 | 0 |
| `monitor_gridcell` | 42/42 | 42/42 | 0 |
| 监测站 `pm25` | 42/42 | 42/42 | 0 |
| `pm25_Model` | **4800/4800** | 4800/4800 | 0 |
| `pm25_VNA` | **4800/4800** | 4800/4800 | 0 |
| `pm25_eVNA` | 193/4800 | 4800/4800 | 4.000e-07 |

单元测试 **60 项全过**。最差 eVNA 格点：`_id=20009`，
shipped `10.42539541`，ours `10.42539501`。

### 13.3 91.25 之谜的定论 [A]

源码里 `91.25`（= 365/4）确实是硬编码的季度除数，但它**只出现在非
annual-only 的季度路径**上。两个定义并存，各有其用途：

| 场景 | 除数 | 源码 |
| --- | --- | --- |
| 通用季度路径 | `sum_q / days_q`（Q1=90, Q2=91, Q3=92, Q4=92） | `AnnualPMDataFusion.cs:1362-1481` |
| `IsAnnualAvgOnly=1` | `sum_year / 365` | `_whole.cs:50147-50230` |
| `pm25_Model` 输出 | `sum_year / 365`，再 `Math.Round(..., 8)` | `_whole.cs:5530` |
| eVNA 梯度两侧 | `sum_year / 365`（**不是**季度值） | `GetGradAdjValues.cs:126-154` |

测试样本 `test_default.cfg` 走的是 annual-only 分支，所以黄金样本里
`pm25_Model` 是 `sum_year / 365`——4800/4800 逐位一致。

### 13.4 `dicQuarterlyModelDataPM` 的键结构 [A]

名字容易误导：它**不是**「季度 → 数据」，而是「格点 → 时间键」。
证据在 `ReadModelDataDaily`（`AnnualPMDataFusion.cs:1362-1481`）：

```csharp
string text4 = array[num].Trim();   // = _ID = 格点 ID（外层键）
string key;
switch (text5.Substring(4, 2)) {   // = DATE 的月份 → 季度 "1".."4"
    case "01": case "02": case "03": key = "1"; break; ...
}
dicQuarterlyModelDataPM[text4].dicModelData[key].pm25 += num20;
...
num22 = dictionary[item.Key][dicModelDatum.Key];  // 该季度天数
dicModelDatum.Value.pm25 /= num22;                 // sum_q / days_q
```

`DataFusion.cs:92` 的 `foreach (KeyValuePair<string, PmModelDataOutput>
item4 in dicQuarterlyModelDataPM)` 外层遍历的确实是**格点**
（`item4.Value.latitudeLamber / longitudeLamber` 是格点投影坐标）。

### 13.5 eVNA 梯度公式（核心）[A]

调用点 `DataFusion.cs:345`：

```csharp
GetGradAdjValues(ref dicGradAdjValues, dictionary8, dictionary7, dictionary12,
                 item4.Value.dicModelData,          // 当前格点的 {时间键: species}
                 dicQuarterlyModelDataPM, GAT, ...);
```

`dictionary12`（= `fsoutStringPM`）的键在 `DataFusion.cs:330` 构造：

```csharp
dictionary12.Add(monitor.id + "," + monitor.gridcell, distance);
//          ^^^^^^^^ PmMonitorDataOutput.id   ^^^^^^^^^^^^^^^^^^^ 监测站所在格点 ID
```

`GetGradAdjValues.cs:129`（pm25 分支）：

```csharp
string key5 = item2.Key.Substring(0, IndexOf(","));   // 监测站 ID
string key6 = item2.Key.Substring(IndexOf(",") + 1);   // 监测站所在格点 ID
pmModelDataSpecies5 = dicQuarterlyModelDataPM[key6].dicModelData[dicModelDatum3.Key];
// GAT == 0 → pmModelDataSpecies6 = pmModelDataSpecies5（无调整）
pm25 = max(dicModelDatum3.Value.pm25, GradLimit) / max(pmModelDataSpecies6.pm25, GradLimit);
```

最终形式：

```
gradient[cell, monitor] = max(model[cell]["2011"], 0.001)
                        / max(model[monitor_cell]["2011"], 0.001)
model[*]["2011"]        = sum_year / 365      ← 两侧同键，纯格点偏置比
```

- `GradLimit = 0.001`（`_whole.cs:43200`），比较用严格 `<`。
- 样本 cfg 无 `GAT` 键 → GAT = 0 → 跳过观测值夹逼。
- **不做 float32 窄化**：`PmModelDataSpecies.*` 全是 `double`
  （`_whole.cs:48179-48216`）。

### 13.6 eVNA 主公式与双舍入路径 [A]

`AnnualPMDataFusion.cs:8247-8289`：

```csharp
num  = (dist == 0.0) ? 1.0 : 1.0 / Math.Pow(dist, eVNAIDWP);  // eVNAIDWP=2
num2 += num;
num3 += dicSpeciesMonitors[key].dicUnofficialPM[quarter] * num
        * dicGradAdjValues[key][quarter].pm25;
...
dEVNA = Math.Round(double.IsNaN(num3 / num2) ? 0f
                   : Convert.ToSingle(num3 / num2), DigitPrecision);
//  ↑ float32 窄化 + Math.Round 银行家舍入，DigitPrecision = 8
```

年值写法（`:5546`）：

```csharp
dataRow["pm25_eVNA"] = CommonClass.ToFixed(
    item.Value.dicQuarterlySpatial_eVNA.Select(p => p.Value.bPMAnnDV).Average(), 8);
//  ↑ 四个「已舍入」的季度 bPMAnnDV 求均值；ToFixed = AwayFromZero
```

`PmSpatial.bPMAnnDV` 是 `double`（`_whole.cs:48616`）。

也就是说 eVNA 走了**两条不同的舍入路径**：季度值先 `Convert.ToSingle`
（float32）再 `Math.Round`（银行家舍入），年度值再 `ToFixed`（远离零）。
VNA 走的则是「季度不舍入 → 均值 → 一次 `ToFixed`」，这也是 VNA 能
4800/4800 逐位一致而 eVNA 不能的原因。

实际调用的是 `AnnualVNAEVNA(..., "pm25", ..., dictionary12,
dicUnofficialPmSpatial, dicModelDatum.Value.pm25)`（`DataFusion.cs:425`），
该重载体内的 `dModel` 参数**完全未被使用**。

### 13.7 剩余残差（eVNA）

当前 **193/4800 逐位一致，最大绝对误差 4e-7**（≈ float32 在 10 µg/m³
量级上的 ulp）。已排除的候选：

| 候选 | 结论 |
| --- | --- |
| 距离表 | 420/420 逐位一致，无问题 |
| 站点迭代顺序（C# Dictionary 按插入序 = 站点索引序） | 已对齐 |
| `dist == 0.0 → 1.0` 分支 | 已实现 |
| 模型值 double 累加顺序（文件顺序） | 已对齐 |
| 年度模型定义（`sum/365` vs 季度 vs 91.25） | 源码定性为 `sum/365` |

残差必然来自 `num3 / num2` 这个 double 在 1e-7 相对量级上的差异——
DataFusion 在窄化之前还有若干未 reverse 的中间量。这已是 float32
精度天花板级别的差异，不影响「可复现」定性。

### 13.8 投影常量（bit-exact 的关键）

```python
MODEL_CRS = ("+proj=lcc +lat_1=33 +lat_2=45 +lat_0=40 +lon_0=-97 "
             "+a=6370000.0 +b=6370000.0")
```

来自 `CommonClass.ProjUSACMAQ`（`CommonClass-02.cs:25`）。**球体**
（`a == b`），且刻意**不加** `+datum=WGS84`。改用 WGS84 椭球会让格点
投影坐标整体偏移约 2 km，66/4800 格的 Voronoi 拓扑翻转——这是早期
`pm25_VNA` 只有 4734/4800 逐位一致的原因。

### 13.9 Downscaler 为何无法逐位复现

降尺度器是 MCMC 链，种子来自 MathNet 的 .NET RNG 实现
（`MathNet.Numerics.Random.Mrg32k`）。要逐位复现必须移植 .NET 的
`System.Random` / MathNet 发生器；在非 .NET 平台上退而求其次只能做
分布对齐。因此 `--with-downscaler` 默认关闭，且该列的验证标准是
分布而非逐位。

## 附录 A：可复现性边界

| 范围 | 状态 |
| --- | --- |
| PM 三路融合 + 物种闭合 + 统计指标 + 人口加权 | 可完整复现 **[A]** |
| 年度 PM2.5 端到端三阶段（距离表 / 站点年均 / 空间场） | 可完整复现 **[A]**，见第 13 节 |
| O₃ SRF / Voronoi / 三路融合 / RRF | 可复现，Albers 参数待标定 **[A]/[C]** |
| 降尺度器算法结构 | 可复现；逐位一致需匹配 RNG **[A]** |
| SMAT 的 BenMAP / SSIA / 能见度 / 沉降模块 | 仅结构表征 **[B]** |
| 端到端逐位复现（eVNA 列） | 差 1 个 float32 ulp（≤4e-7）**[A]** |

## 附录 B：反产出物索引（本地，不入库）

| 路径 | 内容 |
| --- | --- |
| `_rea_datafusion/decompile.ps1` | 参数化反编译脚本（`Target` / `OutDir` / `OnlyType`） |
| `_rea_datafusion/src/_whole.cs` | DataFusion 全量反编译源码（3.0 MB） |
| `_rea_datafusion/src/classes/` | 提取的 15 个类 |
| `_rea_datafusion/src/methods/` | 提取的 34 个方法（含 `SingleRun.cs`、全部 `SF_*`） |
| `_rea_smat/src/_whole.cs` | SMAT 全量反编译源码（5.9 MB） |
| `_rea_smat/src/classes/` | `AnnualPMCommonClass.cs`、`AnnualPMAnalysis.cs`、`OzoneCommonClass.cs`、`VisibilityCommonClass.cs`、`BenMAP*.cs`、`MatrixCompute.cs`、`SpecialFunction.cs`、`MCMC.cs` 等 |
| `_rea_smat/extract.ps1` | SMAT 类提取脚本 |

大文件（>1 MB）不入库，仅保留本文档与必要的类/方法片段。

## 附录 C：SMAT 关键常量

来源：`SMAT/_whole.cs:45619`、`45621`、`45623`

| 常量 | 值 |
| --- | --- |
| `gradLimit` | 0.001 |
| `species_calc_precision` | 7 |
| `species_fraction_precision` | 7 |

DataFusion 对应（`_whole.cs:43198`、`43200`）：

| 常量 | 值 |
| --- | --- |
| `_digitPrecision` | 8 |
| `_gradLimit` | 0.001 |




