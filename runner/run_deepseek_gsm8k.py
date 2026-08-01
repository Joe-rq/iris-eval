"""runner/run_deepseek_gsm8k.py — 用 lm-eval-harness 在 Modal 上重跑 DeepSeek × GSM8K

================================================================================
什么时候用这个
================================================================================
data/ 里已经固化了 2026-07-28 那次运行的结果，replay.py 能离线复现 34 分差。
**只有当你想用更新的模型版本、或换样本量重新生成一份数据时，才需要跑这个。**
离线复现不需要它。

================================================================================
需要
================================================================================
  - Modal 账号（modal.com），已 `modal setup` 登录
  - DeepSeek API key，放在环境变量 DEEPSEEK_API_KEY 里

================================================================================
用法
================================================================================
  DEEPSEEK_API_KEY=sk-xxx python -m modal run runner/run_deepseek_gsm8k.py            # 100 题
  DEEPSEEK_API_KEY=sk-xxx python -m modal run runner/run_deepseek_gsm8k.py --smoke    # 10 题冒烟

跑完，逐题 samples（含两个 filter 的判分）落在
Modal volume: api-eval-harness-results:/DeepSeek/<时间戳>/deepseek-chat/
"""

import os
import sys

import modal

MODEL = "deepseek-chat"
DEEPSEEK_BASE = "https://api.deepseek.com/v1/chat/completions"

app = modal.App("iris-eval-deepseek-gsm8k")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "lm-eval[api]>=0.4.5",   # [api] 带 tenacity / openai-compat
        "datasets>=2.20",
        "huggingface_hub",
        "transformers",          # local-chat-completions 需要 HF tokenizer 算 prompt 长度
        "torch",
        "openai",
    )
)

results_vol = modal.Volume.from_name("api-eval-harness-results", create_if_missing=True)
RESULTS_DIR = "/results"


@app.function(
    image=image,
    cpu=2.0,
    memory=8000,
    volumes={RESULTS_DIR: results_vol},
    timeout=60 * 30,
)
def eval_one(api_key: str, tasks: str, limit: int):
    """在 Modal 容器里跑一次 lm-eval-harness，开 --log_samples。"""
    import subprocess
    from datetime import datetime
    from pathlib import Path

    os.environ["OPENAI_API_KEY"] = api_key  # local-chat-completions 读这个环境变量
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    out_dir = Path(RESULTS_DIR) / "DeepSeek" / ts / MODEL
    out_dir.mkdir(parents=True, exist_ok=True)

    # DeepSeek 官方 API 是 OpenAI 兼容的 /v1/chat/completions。
    # local-chat-completions 后端 + chat 模式 generative 任务（gsm8k 走 generate_until）。
    model_args = ",".join([
        f"model={MODEL}",
        f"base_url={DEEPSEEK_BASE}",
        "num_concurrent=4",
        "max_retries=3",
        "tokenizer_backend=None",
        "tokenized_requests=False",
    ])

    cmd = [
        sys.executable, "-m", "lm_eval",
        "--model", "local-chat-completions",
        "--model_args", model_args,
        "--tasks", tasks,
        "--limit", str(limit),
        "--apply_chat_template",
        "--output_path", str(out_dir),
        "--log_samples",
        "--seed", "1234",
    ]
    print(f"[DeepSeek] tasks={tasks} limit={limit}")
    print("  $", " ".join(cmd))
    subprocess.run(cmd, check=True)
    results_vol.commit()
    print(f"[DeepSeek] DONE. 结果在 volume: {out_dir}")


@app.local_entrypoint()
def main(smoke: bool = False, tasks: str = "gsm8k", limit: int = 100):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("缺环境变量 DEEPSEEK_API_KEY（去 https://platform.deepseek.com 申请）")
    if smoke:
        limit = 10
    print(f"=== DeepSeek × {tasks} × {limit} 题 ===")
    eval_one.remote(api_key, tasks, limit)
    print("\n完成。从 Modal volume 下载结果：")
    print("  python -m modal volume ls api-eval-harness-results /DeepSeek")
