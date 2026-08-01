# iris-eval · 评测分数会撒谎

> 一个可离线复现的实证：同一批 100 道 GSM8K、同一个模型（DeepSeek）的生成结果，只换一个「答案抽取器」，分数就从 **64%** 跳到 **98%**，相差 34 个百分点。模型没变，题目没变，生成的文本一字没改。

这是 [Joe-rq](https://github.com/Joe-rq) 的 **FDE 评测工程作品**：展示如何识破"模型能力幻觉"——很多看起来漂亮的评测分数，提升的其实不是模型能力，而是评测方法的口径。

## 30 秒看懂

> **评测分数 = 模型能力 × 评测方法**

本仓库用两个互补的实证把这两项拆开：

| 洞察 | 一句话 | 证据强度 |
|---|---|---|
| [01 · 抽取器凭空变出 34 分](cases/01-extractor-gap.md) | 同一批 GSM8K × DeepSeek 生成，`strict-match` 64% / `flexible-extract` 98%——因为模型用 `\boxed{}` 收尾，而 strict 只认 `####` | **可独立复算** |
| [02 · 公开题的 100% 是假信号](cases/02-public-vs-private-bench.md) | 公开 CS 题拿 100%（gold 偏斜 + 可能训练污染），自建 IRIS 私有题只 62% | 观察性结论 |

## 一行复现核心结论

clone 后，无需任何 API key、不联网：

```bash
python3 replay.py
```

```
  答案抽取器                    exact_match
  --------------------------------------
  strict-match                   64.0%   (n=100)
  flexible-extract               98.0%   (n=100)
  --------------------------------------
  差值                             34.0   个百分点
```

想看 34 道被 strict 误判成错的题（含模型原始推理文本）：

```bash
python3 replay.py --examples
```

## 这 34 分到底怎么来的

不是统计噪声，是确定性的**格式协议错配**：

- `strict-match` 几乎只认 GSM8K 原生锚定格式 `#### 数字`。
- DeepSeek 习惯用 LaTeX `\boxed{20}` 给最终答案。
- strict 把所有非 `####` 结尾的输出抽成 `[invalid]`，直接判 0 分。
- 固化数据里的铁证：**strict 判对的 64 道，100% 用了 `####`；判错的 34 道，全都没用**（其中 28 道用 `\boxed{}`）。
- `flexible-extract` 用正则抓最后一个数字，把这 34 道的答案捞了回来。

**34 分差 = 34 道格式不符的题，一道 1 分，严丝合缝。** 模型不是算错了，是用了 strict 不认的输出格式——strict 把"格式协议不匹配"误读成了"数学能力不足"。

完整机制、具体题例和交付启示见 [cases/01](cases/01-extractor-gap.md)。

## 数据怎么来的

| 项 | 值 |
|---|---|
| 模型 | DeepSeek（`deepseek-chat`，官方 API） |
| 任务 | GSM8K v3，100 题（测试集前 100，seed 1234） |
| 框架 | lm-eval-harness 0.4.12，5-shot CoT |
| 后端 | `local-chat-completions`，跑在 Modal 云容器 |
| 成本 | 那次正式评测约 ¥0.12 API + <$0.01 Modal |
| 固化 | `--log_samples` 开启，逐题原始生成 + 两个 filter 的判分全部落盘 |

数据已扫描，**不含任何 API 凭据**（`sk-` / `Bearer` / `api_key` 等 0 命中）。

## 仓库结构

```
iris-eval/
├── replay.py                          # 离线复现脚本（纯标准库，无依赖）
├── data/
│   ├── gsm8k_deepseek_samples.jsonl   # 固化逐题 responses（200 行 = 100 题 × 2 filter）
│   └── gsm8k_deepseek_results_meta.json  # lm-eval 元数据（版本 / seed / hash）
├── cases/
│   ├── 01-extractor-gap.md            # 34 分差的机制 + 具体题例
│   └── 02-public-vs-private-bench.md  # 公开题假信号 + IRIS 私有题
├── private-eval/
│   └── iris_mcqa_8.json               # 8 道自拟 IRIS MCQA + gold + DeepSeek 预测
└── runner/
    └── run_deepseek_gsm8k.py          # 进阶：自带 key + Modal 重跑一份数据
```

## 想跑一份新鲜数据

`data/` 是 2026-07-28 那次运行的结果。若你想用更新的模型版本或换样本量重新生成：

```bash
DEEPSEEK_API_KEY=sk-xxx python -m modal run runner/run_deepseek_gsm8k.py --limit 100
```

需要 Modal 账号 + DeepSeek key。**这是进阶选项，离线复现完全不需要它。**

## 证据边界（先看这里再看分数）

- **98% 不是 headline，而是要被解释的对象。** 它来自 flexible-extract 抓最后一个数字，掩盖了 strict 协议下的 64%。本仓库的第一立场是批判这个 98%，而不是炫耀它。
- **8 道 IRIS 题样本量过小，不能用于任何模型排名**，只用于展示"公开题满分 / 私有题露边界"这一现象。
- 洞察 01 的 GSM8K 结果**可独立复算**（固化数据 + `replay.py`）；洞察 02 的公开题 / 私有题结果是**观察性结论**，逐题 responses 未固化，不能在本仓库独立复算（见各 case 文档的"证据强度"段）。
- IRIS SFT 数据集（本仓库不收录）经 AI 评分筛选、**无人工金标**，不可称"高质量"。
- 所有数字都标注了样本量、口径与证据强度。

## 这是什么、不是什么

- **是**：个人评测工程实践，展示在交付现场如何识破"分数幻觉"。
- **不是**：InterSystems IRIS 官方观点；不含客户数据、生产数据或任何密钥；不代表任何模型在 IRIS 领域的权威排名。

## 与 FDE Delivery OS 的关系

[FDE Delivery OS](https://github.com/Joe-rq/fde-delivery-os) 是作者的方法体系层（机会判断 → 现场发现 → 定界 → SOW → Spec → **Eval** → 生产化 → 采用 → 复用）。本仓库是其中 **Eval** 环节的一个可运行样本——把"评测分数必须按模型 × 任务 × 抽取器 × 样本量 × seed 披露"这件事，做成任何人都能 clone 复现的实证，而不是一句方法论口号。

## 附录 · 课程作业映射

本仓库的实验最早在「零基础 AI 大模型研发」课程的以下作业里完成。这里把作业重构为一个独立的、可复现的评测工程作品：

| 课程模块 | 原作业内容 | 本仓库呈现 |
|---|---|---|
| ch05-02 进阶 | OLMo-3-7B 4-bit LoRA，r=16 / r=32 对照 | IRIS 私有题基于该数据集改写（训练数据与 adapter 未收录） |
| ch06 进阶 | lm-eval-harness × DeepSeek × GSM8K，发现抽取器差异 | `data/` + `replay.py` + `cases/01` |
| ch06 基础 | mmlu_cs / ceval_cs / IRIS MCQA 对照 | `cases/02` + `private-eval/iris_mcqa_8.json` |

## License

- 代码（`replay.py`、`runner/`）与固化数据（`data/`）：**MIT**
- 文档（`README.md`、`cases/`）与 8 道自拟 IRIS 题（`private-eval/`）：**CC-BY-4.0**

详见 [LICENSE](LICENSE)。
