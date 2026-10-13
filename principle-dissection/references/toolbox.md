# 工具箱:按「拆哪种原理」选项目

> 第 4 步(oracle 实测)和第 5 步(补黑箱层)从这里选。**星数为 2026-10-13 查得,会变。**
> 铁律:这些是**工具候选**,不是清单成就。**没跑 = 没做。**

---

## 一、先亲手撞上「绿着却没盯住东西」

拆**并发 / 分布式 / 有状态**产物时,先来这一组。它会让你亲眼看到"我的实现看着对,但检查器说不对"。

| 项目 | 星 | 拆什么原理时用它 |
|---|---|---|
| `jepsen-io/maelstrom` | 3.7k | **最好的入门**。给几个小玩具分布式系统让你实现,配一个线性一致性检查器。一个周末就能体验"我以为对了"。 |
| `jepsen-io/jepsen` | 7.5k | 进阶。价值一半在代码、一半在**分析文章**:每篇都是"厂商自己的测试全过,Jepsen 找出真 bug"。 |
| `asatarin/testing-distributed-systems` | 2.6k | 上面这类的书单。 |
| `tigerbeetle/tigerbeetle` | 17.2k | 确定性仿真测试的工业样板:把时间/网络/故障都变成可控变量,于是"跑一万次都过"才第一次有意义。 |
| `ivanyu/awesome-deterministic-simulation-testing` | — | 确定性仿真测试(DST)的资源汇总。 |
| `antithesishq/bombadil` | 1.5k | 把属性测试用到 **UI / 终端**上。 |
| `chaos-mesh/chaos-mesh` · `chaostoolkit/chaostoolkit` | 7.9k / 2.0k | 把"注入故障"变成常规纪律。 |

---

## 二、造你自己那层 oracle(工具,直接治病)

拆**纯函数 / 算法 / 库 / 单进程服务**时的主力。

| 手段 | 项目 | 星 | 治什么 |
|---|---|---|---|
| **变异测试** | `boxed/mutmut`(Py) · `sixty-north/cosmic-ray`(Py) | 1.5k / 660 | **「测试绿着但根本没盯住东西」**。故意把代码改错,看测试抓不抓得住。 |
| | `sourcefrog/cargo-mutants`(Rust) · `stryker-mutator/stryker-js`(JS) · `hcoles/pitest`(JVM) | 1.3k / 3.2k / 1.9k | 同上,各语言版。 |
| | `mbj/mutant`(Ruby) | 2.2k | 同上。Slogan 就是 *"AI writes your code. AI writes your tests. But who tests the tests?"* |
| **属性测试** | `HypothesisWorks/hypothesis`(Py) | 9.1k | 逼你把**不变量**写出来、而不是写流程。 |
| | `BurntSushi/quickcheck`(Rust) · `dubzzz/fast-check`(TS) · `jqwik-team/jqwik`(JVM) | — | 同上,各语言版。 |
| **契约/符号执行** | `pschanely/CrossHair`(Py) | 1.3k | 把契约当断言,自动搜反例。卡在测试和类型之间。 |
| **fuzz** | `uds-se/fuzzingbook`(书+代码) | 1.3k | 最系统的 fuzz 入门。**先查这个。** |
| | `antonio-morales/Fuzzing101` · `google/oss-fuzz` | 3.9k / 12.7k | 练习 / 工业基础设施。 |
| | `google/oss-fuzz-gen` | 1.4k | **本身就是「用 LLM 生成 fuzz 靶子」**——AI 产物如何被独立验证的现实样本。 |
| **差分/对拍** | 自己写 | — | 同输入喂两个实现(新旧 / 我的 vs 参考),比输出。**拆数值/科学计算必上。** |

---

## 三、往下补一层(重建你会委托出去的东西)

第 5 步用。**只挑最承重的一层,别全上。**

| 项目 | 星 | 补哪一层 |
|---|---|---|
| `nand2tetris`(中文仓库 `woai3c/nand2tetris`) | 2.9k | 从 NAND 门搭到能跑程序。「多懂一层」最标准的一门课。 |
| `codecrafters-io/build-your-own-x` | 552k | 总目录,先挑方向再看。 |
| `chaozh/MIT-6.824`(6.5840 labs) | 3.3k | 分布式。**和第一组配套**:先自己实现 Raft/KV,再拿 Jepsen 找茬。 |
| `munificent/craftinginterpreters` | 11.1k | 手写解释器,弄懂"编译能不能过"背后是什么。 |
| `remzi-arpacidusseau/ostep` | — | 操作系统(Three Easy Pieces)。 |
| `amitshekhariitbhu/build-your-own-x-machine-learning` | 731 | 从线性回归手撸到 LLM。**产物是 LLM 相关的看这个。** |

---

## 四、判数学 / 规格的卷

拆**协议 / 状态机 / 数学断言**时用。也是"人只能审阅"这句话里,**审阅端**的实打实工具。

| 项目 | 星 | 拆什么 |
|---|---|---|
| `leanprover-community/mathlib4`(+ Lean 4) | 4.3k | 数学证明的**机器核验**。把"看着对的证明"和"通过机器检查的证明"分开。 |
| `tlaplus/tlaplus` · `tlaplus/Examples` · `tlaplus/DrTLAPlus` | 3.1k / 1.6k / 860 | 把"规格"写成**可模型检查**的东西。规格对了,代码对错才有判据。 |

---

## 五、判 AI 的卷(eval)

拆 **LLM / agent / prompt 链**时用——这块最贴日常。

| 项目 | 星 | 拆什么 |
|---|---|---|
| `promptfoo/promptfoo` | 26k | prompt / agent / RAG 的测试与红队。OpenAI、Anthropic 自己都在用。 |
| `UKGovernmentBEIS/inspect_ai` | 3.0k | 英国 AISI 的评测框架,设计上偏"**可核验**",比一般 eval 严。 |
| `confident-ai/deepeval` | 18.8k | 通用 LLM eval 框架。 |
| `open-compass/opencompass` | 7.5k | 覆盖 100+ 数据集的多模型评测。 |
| `huggingface/evaluation-guidebook` | 2.2k | 做 eval 的经验/教训。**

> 这类工具的意义**不是给你分数**,是逼你把"好"定义成可执行的东西——也就是"出题 + 判卷"那件事。

---

## 按产物类型 → 选哪一组

| 产物 | 主用哪一组 |
|---|---|
| 并发 / 分布式 / 有状态 | 一(盲区)+ 四(规格) |
| 纯函数 / 算法 / 库 | 二(oracle) |
| 数值 / 科学计算 | 二(差分/对拍)**必上** + 边界清单 |
| LLM / agent / prompt | 五(eval) |
| 协议 / 状态机 | 四(TLA+)+ 一(Jepsen) |
| UI / 交互 | 一(bombadil)+ 二(属性) |
| 一次性脚本 / 胶水 | 二(变异)+ `failure-modes.md` 边界项 |

**如果只挑一个**:`jepsen-io/maelstrom`——它把"我以为对了"这件事,变成一次能亲手经历的、会报错的现场。
