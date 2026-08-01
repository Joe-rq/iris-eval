#!/usr/bin/env python3
"""replay.py — 离线复现「抽取器如何制造 34 分差」

================================================================================
一句话
================================================================================
同一批 100 道 GSM8K、同一模型（DeepSeek）的生成结果，在 lm-eval-harness 里
被两个不同的答案抽取器判分，分数相差 34 个百分点。模型没变、题目没变、生成
的文本没变，变的只是「怎么从推理文本里捞出最终答案」。

  - strict-match     只认模型输出末尾严格锚定格式的答案（#### 数字）
  - flexible-extract 用正则从整段输出的任意位置抽最后一个数字

→ 这就是「评测分数 = 模型能力 × 评测方法」最直接的实证。

================================================================================
为什么能离线复现
================================================================================
lm-eval-harness 跑评测时开了 --log_samples，把每道题的原始生成文本（resps）
和两个 filter 各自的抽取 / 判分结果都写进了 data/gsm8k_deepseek_samples.jsonl。
本脚本只是把这些固化结果读出来重新聚合，不调任何 API、不联网。

数据来源：Modal 云端 2026-07-28 那次正式 100 题运行，逐题 samples 原样下载。

================================================================================
用法
================================================================================
  python3 replay.py             # 打印 strict vs flexible 对照 + 差值
  python3 replay.py --examples  # 额外打印 3 道 strict 判错 / flexible 判对的题
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLES = HERE / "data" / "gsm8k_deepseek_samples.jsonl"
META = HERE / "data" / "gsm8k_deepseek_results_meta.json"


def load_samples(path):
    """读 lm-eval samples JSONL。每行 = 某 filter 下某道题的一条判分记录。"""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            rows.append({
                "filter": r["filter"],
                "doc_id": r["doc_id"],
                "exact_match": r["exact_match"],
                "filtered_resps": r.get("filtered_resps"),
                "target": r.get("target"),
                "resps": r.get("resps"),
                "doc": r.get("doc", {}),
            })
    return rows


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def main():
    ap = argparse.ArgumentParser(description="离线复现抽取器造成的分数差")
    ap.add_argument("--examples", action="store_true",
                    help="打印 3 道 strict 判错 / flexible 判对的题（含原始生成）")
    args = ap.parse_args()

    rows = load_samples(SAMPLES)
    by_filter = defaultdict(list)
    for r in rows:
        by_filter[r["filter"]].append(r["exact_match"])

    # 元数据（能读就读，读不到用占位 —— 核心结论不依赖这些字段）
    meta = {}
    if META.exists():
        meta = json.load(open(META, encoding="utf-8"))
    n_q = len(set(r["doc_id"] for r in rows))
    n_shot = (meta.get("n-shot") or {}).get("gsm8k", "?")

    print("=" * 66)
    print(" 评测分数 = 模型能力 × 评测方法")
    print("=" * 66)
    print(f"  模型      : {meta.get('model_name', 'deepseek-chat')}")
    print(f"  任务      : GSM8K  (lm-eval-harness)")
    print(f"  题数      : {n_q}")
    print(f"  lm-eval   : {meta.get('lm_eval_version', '?')}")
    print(f"  n-shot    : {n_shot}  (CoT)")
    print(f"  seed      : 1234")
    print()
    print(f"  {'答案抽取器':<20}{'exact_match':>16}")
    print("  " + "-" * 38)

    order = [f for f in ["strict-match", "flexible-extract"] if f in by_filter]
    scores = {}
    for f in order:
        acc = _mean(by_filter[f])
        scores[f] = acc
        print(f"  {f:<20}{acc * 100:>15.1f}%   (n={len(by_filter[f])})")
    print("  " + "-" * 38)

    if "strict-match" in scores and "flexible-extract" in scores:
        gap = (scores["flexible-extract"] - scores["strict-match"]) * 100
        print(f"  {'差值':<20}{gap:>15.1f}   个百分点")
    print()
    print("  同一批生成结果，只换抽取规则 → 分数相差约 34 个百分点。")
    print("  模型能力没有任何变化，变化的是评测器能否从推理文本里抽出最终数字。")
    print("  → 只写「GSM8K 98%」会把规则收益误写成模型能力。")

    if args.examples:
        _print_disagreements(rows)

    return scores


def _print_disagreements(rows):
    """找出 strict 判错但 flexible 判对的题，打印原始生成，看清差距来自哪。"""
    by_id = defaultdict(dict)
    for r in rows:
        by_id[r["doc_id"]][r["filter"]] = r

    disagree = []
    for doc_id, fs in by_id.items():
        s = fs.get("strict-match")
        fl = fs.get("flexible-extract")
        if s and fl and s["exact_match"] == 0 and fl["exact_match"] == 1:
            disagree.append((doc_id, s, fl))

    print("\n" + "=" * 66)
    print(f" strict 判错 / flexible 判对的题：共 {len(disagree)} 道，展示前 3 道")
    print("=" * 66)
    for doc_id, s, fl in disagree[:3]:
        doc = s.get("doc") or {}
        question = doc.get("question", "(题目原文缺失)").strip()
        resp = ""
        if s.get("resps"):
            resp = s["resps"][0][0] if isinstance(s["resps"][0], list) else s["resps"][0]
        target = s.get("target", "?")
        print(f"\n— 题 #{doc_id}  (金标答案: {target!r})")
        print(f"  strict 抽出: {s['filtered_resps']!r}  → 判 {'✓' if s['exact_match'] else '✗'}")
        print(f"  flexible 抽出: {fl['filtered_resps']!r}  → 判 {'✓' if fl['exact_match'] else '✗'}")
        print(f"  题目: {question[:120]}{'…' if len(question) > 120 else ''}")
        print(f"  模型生成(尾段): …{str(resp)[-180:]!r}")


if __name__ == "__main__":
    main()
