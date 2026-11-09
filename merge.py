#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并并去重多个 AdGuard / Adblock Plus 2.0 广告拦截订阅规则。

- 拉取多个上游规则文本
- 按类别分类：拦截规则(||...) / 元素隐藏(##) / 例外规则(@@)
- 应用本地白名单 LOCAL_WHITELIST：剔除上游误拦的域名，并在例外区块追加放行
- 全局去重（忽略大小写，保留首次出现的原始写法）
- 输出单一 merged.txt，可直接作为订阅地址使用

用法:
    python merge.py            # 拉取上游并生成 merged.txt
    python merge.py --check    # 只打印统计，不写文件
"""

import sys
import os
import re
import datetime
import subprocess
import urllib.request

# ---------------------------------------------------------------------------
# 上游规则源（按需增删即可，脚本会自动同步它们）
# ---------------------------------------------------------------------------
SOURCES = [
    ("banad/jiekouAD",
     "https://raw.githubusercontent.com/damengzhu/banad/main/jiekouAD.txt"),
    ("AWAvenue-Ads-Rule",
     "https://raw.githubusercontent.com/TG-Twilight/AWAvenue-Ads-Rule/main/AWAvenue-Ads-Rule.txt"),
    ("qq5460168/666/rules",
     "https://raw.githubusercontent.com/qq5460168/666/refs/heads/master/rules.txt"),
    ("rssvcn/qy-Ads-Rule",
     "https://raw.githubusercontent.com/rssvcn/qy-Ads-Rule/main/black.txt"),
]

OUTPUT = "merged.txt"

USER_AGENT = "Mozilla/5.0 (compatible; ad-rule-merge/1.0)"

# 过宽例外规则黑名单：放行整个根域会抵消大量广告拦截规则
# 格式必须是小写的 AdGuard / Adblock Plus 规则原文
WIDE_EXCEPTION_DENYLIST = {
    "@@||360.cn^",
}

# ---------------------------------------------------------------------------
# 本地白名单：上游误拦了自己要用的域名时，把域名写在这里。
# 脚本会自动做两件事，双保险：
#   1) 剔除上游中「精确指向该域名」的拦截规则（hosts 形式与 ||域名^ 形式都识别）
#   2) 在例外规则区块末尾追加 @@||域名^
# 只写域名，不要带 @@ 或 || 前缀。父域规则（如 ||mzstatic.com^）不会被剔除，
# 但例外规则优先级更高，仍然生效。
# ---------------------------------------------------------------------------
LOCAL_WHITELIST = [
    "metrics.mzstatic.com",   # Apple 埋点上报，被广告规则误拦后 App Store 异常
]

_HOSTS_RE = re.compile(r"^(?:0\.0\.0\.0|127\.0\.0\.1|::1?)\s+([a-z0-9._-]+)$")
_BLOCK_DOMAIN_RE = re.compile(r"^\|\|([a-z0-9._-]+)\^?(?:\$.*)?$")
_PLAIN_DOMAIN_RE = re.compile(r"^[a-z0-9._-]+\.[a-z]{2,}$")


def blocked_domain_of(rule: str):
    """尽力识别一条拦截规则针对的域名；识别不了返回 None。

    只识别「精确指向单个域名」的规则，绝不碰父域规则和通配规则，
    避免为了放行一个子域误删整片拦截能力。
    """
    s = rule.strip().lower()
    if not s or s.startswith("!") or s.startswith("@@"):
        return None
    if "##" in s or "#@#" in s or "#?#" in s:
        return None
    m = _HOSTS_RE.match(s)
    if m:
        return m.group(1).rstrip(".")
    m = _BLOCK_DOMAIN_RE.match(s)
    if m:
        return m.group(1).rstrip(".")
    if _PLAIN_DOMAIN_RE.match(s):
        return s
    return None


def local_whitelist_domains():
    """规整本地白名单：去空格、小写、去尾点、去重。"""
    out = []
    for d in LOCAL_WHITELIST:
        d = d.strip().lower().rstrip(".")
        if d and d not in out:
            out.append(d)
    return out


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

    wl = local_whitelist_domains()
    wl_set = set(wl)
    dropped_by_wl = 0

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
            stripped = line.strip()
            if cat == "block":
                # 本地白名单：上游误拦的域名，直接剔除对应拦截规则
                if blocked_domain_of(stripped) in wl_set:
                    dropped_by_wl += 1
                    continue
                blocks.append(stripped)
            elif cat == "cosmetic":
                cosmetics.append(stripped)
            else:
                # 过滤过宽例外规则（如 @@||360.cn^ 放行整个根域）
                if stripped.lower() in WIDE_EXCEPTION_DENYLIST:
                    continue
                exceptions.append(stripped)
            added += 1
        per_source[name] = added

    # 本地白名单例外规则，追加到例外区块末尾（去重后）
    existing = {e.strip().lower() for e in exceptions}
    wl_added = 0
    for d in wl:
        rule = f"@@||{d}^"
        if rule.lower() in existing:
            continue
        exceptions.append(rule)
        existing.add(rule.lower())
        wl_added += 1

    total = len(blocks) + len(cosmetics) + len(exceptions)
    # 北京时间 UTC+8
    cst = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(datetime.timezone.utc).astimezone(cst).strftime("%Y-%m-%d %H:%M:%S UTC+8")

    # CI 环境下自动填入仓库主页
    repo = os.environ.get("GITHUB_REPOSITORY")
    homepage = f"https://github.com/{repo}" if repo else "https://github.com/ (请替换为你的仓库)"

    # 来源信息只打印到控制台供调试，不写进订阅文件本身
    header = (
        "[Adblock Plus 2.0]\n"
        "! ============================================================\n"
        "! Title: Merged Ad Rules (自动合并去重)\n"
        "! 浮风拦截规则\n"
        "! 反馈加QQ:1584574988\n"
        f"! Homepage: {homepage}\n"
        "! 订阅线路1官方文件直链（部分国内网络可能无法访问）：https://raw.githubusercontent.com/Thelongdarkorg/ad-rules-merged/main/merged.txt\n"
        "! 订阅线路2国内连接稳（可达性更好）：https://ghproxy.net/https://raw.githubusercontent.com/Thelongdarkorg/ad-rules-merged/main/merged.txt\n"
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
    print(f"本地白名单 : {len(wl)} 个域名，剔除拦截规则 {dropped_by_wl} 条，新增例外 {wl_added} 条")
    for d in wl:
        print(f"  放行 {d}")
    for n, c in per_source.items():
        print(f"  源 {n}: {c if c >= 0 else 'FETCH FAILED'}")

    if "--check" not in sys.argv:
        with open(OUTPUT, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n已写入 {OUTPUT}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
