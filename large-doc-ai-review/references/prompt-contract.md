# Prompt 契约

## 核心原则：业务语义不进代码

Python 里写死"什么材料、什么字段、什么判断标准"，会带来三个必然后果：改一条业务规则要改代码、
代码里塞满自然语言字符串没法 review、业务规则散落各处互相矛盾。

解法是**一个审查点一对文件**：

```text
prompt_templates/
|-- budget_check.md           # 业务 prompt：角色、输入含义、规则、证据解读、判断标准、JSON 输出示例
`-- budget_check_spec.json    # 机器契约：promptFile、字段 schema、必填、枚举
```

## `.md`（运行时 prompt，给模型看）

必须包含：

1. **角色** —— 你是什么、干什么
2. **输入含义** —— 每个输入字段是什么、单位、可能为空的情况
3. **材料专属规则** —— 只对这个材料成立的条件（跨材料通用规则不要写在这里）
4. **证据解读** —— 什么样的证据算"有"，什么算"没有"，什么算"无法判断"
5. **判断标准** —— 什么条件判 PASS、什么判 FAIL、什么判 MANUAL_REVIEW
6. **JSON 输出示例** —— 完整、按生成顺序

示例（简化）：

````markdown
你是一名申报材料形式审查员，判断项目实施周期是否与申报指南一致。

## 输入
- `sectionText`：从申报书"项目实施周期"章节提取的原始文本
- `guidePeriod`：申报指南中该方向规定的实施周期（月），可能为 null

## 判断标准
- `guidePeriod` 为 null -> 无法判断，输出 MANUAL_REVIEW
- `sectionText` 明确写了起止月份 -> 与 guidePeriod 一致为 PASS，不一致为 FAIL
- `sectionText` 含糊、只有"三年左右"这类描述 -> MANUAL_REVIEW，不要自行推断
- 注意"3 年"与"36 个月"是同一含义

## 输出
```json
{
  "sourceText": "项目实施周期为 2026 年 1 月至 2028 年 12 月。",
  "analysis": "申报书给出明确起止月份，共 36 个月；指南规定该方向实施周期为 36 个月，两者一致。",
  "result": "PASS"
}
```
````

注意示例里 `analysis` 在 `result` **前面**。

## `_spec.json`（机器契约，给代码校验）

```json
{
  "promptFile": "budget_check.md",
  "version": "1",
  "output": {
    "type": "object",
    "properties": {
      "sourceText":  { "type": "string" },
      "analysis":    { "type": "string" },
      "result":      { "type": "string", "enum": ["PASS", "FAIL", "MANUAL_REVIEW"] }
    },
    "required": ["sourceText", "analysis", "result"]
  }
}
```

必须遵守：

- **不要在 json 里重复业务规则。** spec 是契约，不是第二个 prompt。
- **不要在 `systemPrompt` / `userPrompt` 字段里塞长文本。** 有了 `.md` 就别在 JSON 里再写一遍。
- `required` 的顺序要和 `.md` 示例里字段出现的顺序一致。
- 枚举值用 `enum` 声明，代码据此归一，不用在 Python 里硬判字符串。

## 字段顺序策略（重要）

**JSON 对象的字段按输出顺序被模型依次 commit。** 所以结论字段必须写在它所依据的证据字段之后。

反例（这一块故意违反规则，用 `<!-- check-verdict-order: skip -->` 让脚本跳过）：

<!-- check-verdict-order: skip -->
```json
{
  "result": "FAIL",
  "reason": "实施周期与指南要求一致"
}
```

模型先 commit `"FAIL"`，再写 reason 时会倾向于为 FAIL 编理由。这里就是自相矛盾的来源。

正例：

```json
{
  "reason": "实施周期与指南要求一致",
  "result": "PASS"
}
```

检查方式：

```bash
python scripts/check_verdict_order.py <prompt 目录>
```

脚本维护两张词表：

- **结论字段** —— `result` / `score` / `status` / `level` / `grade` / `rating` / `verdict` /
  `decision` / `conclusion` / `finalResult` / `judgement` / `judgment` / `applicability` /
  `requiresHumanReview`，以及以 `Status` / `Match` / `Consistent` 结尾的字段
- **证据字段** —— `reason` / `analysis` / `rationale` / `basis` / `evidence` / `findings` /
  `detail` / `explanation` / `opinion` / `justification` / `reasoning` / `scoreBreakdown`，以及以
  `Reason` / `Evidence` / `Findings` / `Analysis` / `Detail` / `Opinion` / `Assessment` 结尾的字段

还有一张 **结构字段白名单**（`leafId` / `criterion` / `title` / `maxScore` / `sourceInfo` /
`confidence` / `quotes` 等）。这些字段不表达判断，位置无所谓，不能算作"证据"。

**这条规则要有测试守门。** 源项目把它做成了仓库级强制检查，任何新增/变化都让 CI 失败。

## Runner 契约

所有 LLM 调用走同一个执行器，不允许业务代码直接调 SDK：

```python
async def run_prompt(
    spec_path: Path,          # -> promptFile -> 读 .md
    payload: dict,            # 运行时输入，整个作为 JSON 传给模型
    llm: LLMClient,
) -> tuple[dict | None, str | None]:
    """返回 (结果, 错误)。校验失败返回 (None, 原因)，不抛异常。"""
    spec = load_spec(spec_path)
    prompt = (spec_path.parent / spec["promptFile"]).read_text(encoding="utf-8")
    raw = await llm.complete(prompt=prompt, payload=payload)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"invalid json: {e}"
    if err := validate_against_spec(data, spec):
        return None, err
    return data, None
```

关键点：

- **不抛异常**。返回 `(None, 原因)`，让业务层决定怎么兜底。异常会打断整条流水线。
- **校验和调用绑在一起**。业务层拿到的要么是合法的结果，要么是 None，不存在"半合法"状态。
- **Python validator 不重建 prompt 语义**。它只做通用规范化、跨字段关系检查、覆盖完整性检查。

## 什么该进 prompt，什么该进代码

| 该进 prompt | 该进代码 |
|-------------|----------|
| 材料字段的含义和判断标准 | 类型转换、数值归一 |
| 证据如何解读为"满足/不满足" | 确定性的算术校验和加总 |
| 拿不准时该转人工 | 枚举归一、必填检查 |
| 表格列的业务含义 | 表格行列切分、索引覆盖检查 |
| 复核人该看哪几页 | LLM 调用、重试、超时、限流 |

反例（业务规则写进代码）：

```python
# 差：判断标准硬编码，藏在通用打分器里
if "签字" in criterion or "盖章" in criterion:
    if not found_seal:
        return FAIL
```

正例：

```text
# 好：建一个专属 prompt 描述签字盖章的判断标准
#    代码只负责调用、校验、写入 score
seal_review.md
seal_review_spec.json
```

## 共享 prompt 要保持通用

多个业务共用的 prompt 保持通用。**叶子级特殊规则不要往共享 prompt 里堆**，该建专属 prompt 就建。
堆在一起的共享 prompt 会变成谁都不敢改的垃圾场。
