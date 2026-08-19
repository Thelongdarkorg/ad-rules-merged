#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并并去重多个 AdGuard / Adblock Plus 2.0 广告拦截订阅规则。

- 拉取多个上游规则文本
- 按类别分类：拦截规则(||...) / 元素隐藏(##) / 例外规则(@@)
- 全局去重（忽略大小写，保留首次出现的原始写法）
- 输出单一 merged.txt，可直接作为订阅地址使用

用法:
    python merge.py            # 拉取上游并生成 merged.txt
    python merge.py --check    # 只打印统计，不写文件
"""

import sys
import os
import datetime
import subprocess
import urllib.request

# ---------------------------------------------------------------------------
# 上游规则源（按需增删即可，脚本会自动同步它们）
# ---------------------------------------------------------------------------
SOURCES = [
    ("AWAvenue-Ads-Rule",
     "https://raw.githubusercontent.com/TG-Twilight/AWAvenue-Ads-Rule/main/AWAvenue-Ads-Rule.txt"),
    ("banad/jiekouAD",
     "https://raw.githubusercontent.com/damengzhu/banad/main/jiekouAD.txt"),
    ("qq5460168/666/dns",
     "https://raw.githubusercontent.com/qq5460168/666/master/dns.txt"),
]

OUTPUT = "merged.txt"

USER_AGENT = "Mozilla/5.0 (compatible; ad-rule-merge/1.0)"


def fetch(url: str, timeout: int = 30, retries: int = 4) -> str:
    """优先用 curl（兼容 CI 与受限网络），失败回退 urllib。带重试。"""
    last_err = None
    for attempt in range(1, retries + 1):
        # 1) curl
        try:
            out = subprocess.run(
                ["curl", "-fsSL", "--max-time", str(timeout), "-A", USER_AGENT, url],
                capture_output=True, text=True, timeout=timeout + 10,
            )
            if out.returncode == 0 and out.stdout:
                return out.stdout
            last_err = f"curl exit {out.returncode}"
        except Exception as exc:
            last_err = str(exc)
        # 2) urllib 回退
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:
            last_err = str(exc)
        print(f"    [重试 {attempt}/{retries}] {url}: {last_err}", file=sys.stderr)
    raise RuntimeError(f"拉取失败(已重试{retries}次): {url} -> {last_err}")


def categorize(line: str) -> str:
    """返回 'exception' / 'cosmetic' / 'block'"""
    s = line.strip()
    if s.startswith("@@"):
        return "exception"
    if "##" in s or "#@#" in s or "#?#" in s:
        return "cosmetic"
    return "block"


def is_rule(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s.startswith("!"):   # 注释
        return False
    if s.startswith("["):   # [Adblock Plus 2.0] 等区块头
        return False
    return True


def main() -> int:
    blocks, cosmetics, exceptions = [], [], []
    seen = set()
    per_source = {}

    for name, url in SOURCES:
        try:
            text = fetch(url)
        except Exception as exc:  # 单个源失败不影响其他源
            print(f"[WARN] 拉取失败: {name} -> {exc}", file=sys.stderr)
            per_source[name] = -1
            continue

        added = 0
        for raw in text.splitlines():
            line = raw.rstrip()
            if not is_rule(line):
                continue
            key = line.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            cat = categorize(line)
            if cat == "block":
                blocks.append(line.strip())
            elif cat == "cosmetic":
                cosmetics.append(line.strip())
            else:
                exceptions.append(line.strip())
            added += 1
        per_source[name] = added

    total = len(blocks) + len(cosmetics) + len(exceptions)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # CI 环境下自动填入仓库主页
    repo = os.environ.get("GITHUB_REPOSITORY")
    homepage = f"https://github.com/{repo}" if repo else "https://github.com/ (请替换为你的仓库)"

    # 来源信息只打印到控制台供调试，不写进订阅文件本身
    header = (
        "[Adblock Plus 2.0]\n"
        "! ============================================================\n"
        "! Title: Merged Ad Rules (自动合并去重)\n"
        f"! Homepage: {homepage}\n"
        "! Expires: 12 hours\n"
        f"! Generated: {now}\n"
        f"! Total rules: {total}\n"
        "! ============================================================\n"
    )

    body = []
    if blocks:
        body.append("! ---------- 拦截规则 (blocking) ----------")
        body.extend(blocks)
    if cosmetics:
        body.append("! ---------- 元素隐藏 (cosmetic) ----------")
        body.extend(cosmetics)
    if exceptions:
        body.append("! ---------- 例外规则 (exceptions, 置于末尾优先覆盖) ----------")
        body.extend(exceptions)

    content = header + "\n".join(body) + "\n"

    # 统计输出
    print(f"拦截规则 : {len(blocks)}")
    print(f"元素隐藏 : {len(cosmetics)}")
    print(f"例外规则 : {len(exceptions)}")
    print(f"合并总计 : {total}")
    for n, c in per_source.items():
        print(f"  源 {n}: {c if c >= 0 else 'FETCH FAILED'}")

    if "--check" not in sys.argv:
        with open(OUTPUT, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n已写入 {OUTPUT}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
