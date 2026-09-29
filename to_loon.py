#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 Adblock / AdGuard 格式的 merged.txt 转换为 Loon 规则格式（loon.txt）。

设计要点（为什么这么转）：
  1) 只输出 REJECT 规则，不输出 DIRECT。
     adblock 的 @@ 例外语义是「这条不拦」，而不是「强制直连」；
     若转成 DIRECT 会改变用户原有的代理策略（副作用大）。
     正确做法：把 @@ 规则解析成「豁免集」，生成 REJECT 列表时剔除掉，
     未被规则命中的请求本就按 Loon 后续规则/默认策略处理，效果等价。
  2) 元素隐藏规则（## / #@# / #?#）Loon 不支持，直接丢弃。
  3) 带 $domain= 等条件修饰语的规则丢弃（Loon 无条件修饰语语法，
     强行转成全局拦截会误伤非目标站点）。
  4) 带路径的规则转为 URL-REGEX（数量可控，性能可接受）。
  5) hosts 行（0.0.0.0 xxx）按是否含通配 * 选择 DOMAIN / DOMAIN-SUFFIX。

用法:
    python to_loon.py                 # 读 merged.txt -> 写 loon.txt
    python to_loon.py --check         # 只打印统计，不写文件
    python to_loon.py --in a.txt --out b.txt
"""

import sys
import re
import os
import argparse
import datetime
from collections import Counter

DEFAULT_IN = "merged.txt"
DEFAULT_OUT = "loon.txt"

# 合法域名（不含通配）
DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
# 纯 IPv4
IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
# hosts 行：0.0.0.0 domain / 127.0.0.1 domain
HOSTS_RE = re.compile(r"^(?:0\.0\.0\.0|127\.0\.0\.1)\s+(\S+)\s*$")

# 被认为是「无害」的修饰语：不影响是否拦截的判断，可直接剥离后转全局拦截
SAFE_MODIFIERS = {
    "third-party", "first-party", "document", "script", "image", "stylesheet",
    "xmlhttprequest", "subdocument", "object", "font", "media", "websocket",
    "ping", "other", "popup", "empty", "match-case", "important", "all",
    "network", "content", "extension", "generichide", "elemhide", "csp",
}
# 危险/条件修饰语：Loon 无法表达，丢弃该规则（宁可漏拦，不可误伤）
BLOCKED_MODIFIERS = ("domain=", "denyallow=", "from=", "to=", "method=", "header=",
                     "cookie=", "ua=", "url=", "removeheader=", "app=", "ctag=",
                     "client=", "network=", "strict")


def split_modifiers(rule: str):
    """把 ||xxx^$a,b 拆成 (主体, 修饰语列表)；无 $ 返回 (rule, [])。"""
    if "$" not in rule:
        return rule, []
    body, _, mods = rule.partition("$")
    return body, [m.strip() for m in mods.split(",") if m.strip()]


def normalize_domain(d: str):
    """归一化域名：去首尾点、小写、去 ^ 尾。返回 None 表示非法。"""
    if not d:
        return None
    d = d.strip().lower().rstrip("^").strip(".")
    if not d or "*" in d or "/" in d:
        return None
    if not DOMAIN_RE.match(d):
        return None
    return d


def host_to_domain(h: str):
    """hosts 条目的域名部分（可能含 * 通配），返回 (域名, 是否后缀匹配)。"""
    h = h.strip().lower().rstrip(".")
    if not h:
        return None, False
    # *.example.com / *-ads.example.com / *example.com
    if h.startswith("*."):
        d = h[2:]
    elif h.startswith("*-"):
        d = h[2:]
    elif h.startswith("*") or "*" in h:
        # 通配在中间或开头，退化成后缀匹配（去掉星号及左侧片段）
        d = h.split("*")[-1].lstrip(".-")
    else:
        d = h
    d = d.strip(".")
    if not d or not DOMAIN_RE.match(d):
        return None, False
    return d, True  # hosts 一律按后缀匹配，覆盖面与 adblock hosts 语义一致


def path_to_regex(body: str):
    """把 ||example.com/path 形态转成 Loon URL-REGEX 主体。失败返回 None。"""
    # 去掉开头 || 与结尾 ^
    s = body
    if s.startswith("||"):
        s = s[2:]
    s = s.rstrip("^")
    if not s:
        return None
    # 分离域名部分与路径部分
    m = re.match(r"^([^/]*)(/.*)?$", s)
    if not m:
        return None
    host_part, path_part = m.group(1), (m.group(2) or "")
    if not host_part:
        return None
    # 域名里的通配 * 转成正则
    host_re = ""
    for ch in host_part:
        if ch == "*":
            host_re += "[^/]*"
        elif ch == ".":
            host_re += r"\."
        elif ch == "-":
            host_re += r"\-"
        else:
            host_re += re.escape(ch)
    path_re = ""
    if path_part:
        # 路径里的 * 在 adblock 里是通配，^ 是分隔符
        p = path_part
        p = p.replace("^", r"[/?=&:]|(?![a-z0-9%-])")
        p = re.sub(r"\*+", "[^ ]*", p)
        p = re.sub(r"([.?+()\[\]{}])", r"\\\1", p)
        path_re = p
    return r"^https?://(?:[a-z0-9-]+\.)*" + host_re + path_re


def valid_rule(rule_line: str):
    """输出前的安全校验：非法规则会让 Loon 整个订阅加载失败，宁可丢弃。"""
    # 逗号是 Loon 规则的分隔符，除类型/值/策略外不允许再出现
    parts = rule_line.split(",")
    if rule_line.startswith("URL-REGEX,"):
        # URL-REGEX,<正则>,REJECT —— 正则内若含逗号会破坏解析，直接判非法
        if len(parts) != 3:
            return False
        pattern = parts[1]
        if not pattern or len(pattern) > 300:
            return False
        # 混入 HTML / 非法字符（上游源偶发混入网页内容）
        if any(ch in pattern for ch in '<>"\n\r\t '):
            return False
        try:
            re.compile(pattern)
        except re.error:
            return False
        return True
    if len(parts) not in (3, 4):
        return False
    value = parts[1]
    if not value or len(value) > 253:
        return False
    if any(ch in value for ch in '<>"\n\r\t ,'):
        return False
    return True


def convert(lines):
    """返回 (loon 规则行列表, 统计 Counter)"""
    stats = Counter()
    exemptions = set()          # 豁免域名（来自 @@）
    blocks = []                 # 转换后的拦截规则（去重前）
    seen = set()                # 转换结果去重

    def add(rule_line: str):
        if not valid_rule(rule_line):
            stats["丢弃-输出非法"] += 1
            return
        if rule_line in seen:
            stats["去重丢弃"] += 1
            return
        seen.add(rule_line)
        blocks.append(rule_line)

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("!") or line.startswith("["):
            continue

        # ---------- 元素隐藏：Loon 不支持 ----------
        if "##" in line or "#@#" in line or "#?#" in line:
            stats["丢弃-元素隐藏"] += 1
            continue

        # ---------- 例外规则 ----------
        if line.startswith("@@"):
            body = line[2:]
            body, mods = split_modifiers(body)
            # 带条件修饰语的例外忽略（无法表达）
            if any(m in body or any(b in m for b in BLOCKED_MODIFIERS) for m in mods):
                stats["丢弃-例外带条件"] += 1
                continue
            if body.startswith("||"):
                d = normalize_domain(body[2:].split("/")[0])
                if d:
                    exemptions.add(d)
                    stats["豁免域名"] += 1
                    continue
            m = HOSTS_RE.match(body)
            if m:
                d, _ = host_to_domain(m.group(1))
                if d:
                    exemptions.add(d)
                    stats["豁免域名"] += 1
                    continue
            stats["丢弃-例外无法解析"] += 1
            continue

        # ---------- 拦截规则 ----------
        body, mods = split_modifiers(line)
        # 危险条件修饰语 -> 丢弃
        if any(any(b in m for b in BLOCKED_MODIFIERS) for m in mods):
            stats["丢弃-拦截带条件"] += 1
            continue
        if any(m not in SAFE_MODIFIERS for m in mods):
            stats["丢弃-未知修饰语"] += 1
            continue

        # 1) ||domain^ 形态
        if body.startswith("||"):
            rest = body[2:]
            if "/" in rest:                     # 带路径 -> URL-REGEX
                rx = path_to_regex(body)
                if rx:
                    add(f"URL-REGEX,{rx},REJECT")
                    stats["转-URL-REGEX"] += 1
                else:
                    stats["丢弃-路径无法解析"] += 1
                continue
            d = normalize_domain(rest.rstrip("^"))
            if d:
                add(f"DOMAIN-SUFFIX,{d},REJECT")
                stats["转-DOMAIN-SUFFIX"] += 1
                continue
            if IPV4_RE.match(rest.rstrip("^")):  # 纯 IP
                add(f"IP-CIDR,{rest.rstrip('^')}/32,REJECT,no-resolve")
                stats["转-IP-CIDR"] += 1
                continue
            stats["丢弃-域名非法"] += 1
            continue

        # 2) hosts 形态
        m = HOSTS_RE.match(body)
        if m:
            d, _ = host_to_domain(m.group(1))
            if d:
                add(f"DOMAIN-SUFFIX,{d},REJECT")
                stats["转-hosts"] += 1
            else:
                stats["丢弃-hosts非法"] += 1
            continue

        # 3) 正则形态 /regex/
        if body.startswith("/") and body.endswith("/") and len(body) > 2:
            add(f"URL-REGEX,{body[1:-1]},REJECT")
            stats["转-正则"] += 1
            continue

        # 4) 裸域名
        d = normalize_domain(body)
        if d:
            add(f"DOMAIN-SUFFIX,{d},REJECT")
            stats["转-裸域名"] += 1
            continue

        # 5) 以路径开头的规则（如 .xyz/xxx 或 /js/x.js）
        rx = path_to_regex(body)
        if rx:
            add(f"URL-REGEX,{rx},REJECT")
            stats["转-路径规则"] += 1
        else:
            stats["丢弃-其他"] += 1

    # ---------- 应用豁免：命中豁免域名的规则不输出 ----------
    final = []
    dropped_by_exemption = 0
    for r in blocks:
        if r.startswith("DOMAIN-SUFFIX,"):
            d = r.split(",")[1]
            if d in exemptions or any(d.endswith("." + e) for e in exemptions):
                dropped_by_exemption += 1
                continue
        final.append(r)
    stats["豁免剔除"] = dropped_by_exemption

    return final, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=DEFAULT_IN)
    ap.add_argument("--out", dest="out", default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    with open(args.inp, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    rules, stats = convert(lines)

    cst = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(datetime.timezone.utc).astimezone(cst).strftime("%Y-%m-%d %H:%M:%S UTC+8")
    repo = os.environ.get("GITHUB_REPOSITORY", "Thelongdarkorg/ad-rules-merged")

    header = [
        "# ============================================================",
        "# Loon 规则集（由 ad-rules-merged 从 merged.txt 自动转换生成，勿手改）",
        f"# Homepage: https://github.com/{repo}",
        f"# Generated: {now}",
        f"# Total rules: {len(rules)}",
        "# 上游: banad/jiekouAD, AWAvenue-Ads-Rule, qq5460168/666/rules",
        "# 说明: @@ 例外规则已作为豁免集从本列表中剔除（不输出 DIRECT，避免改变代理策略）",
        "# ============================================================",
        "",
    ]

    # 分类输出：先域名后缀，再 IP，再正则（正则放最后，减少性能开销）
    suffix = [r for r in rules if r.startswith("DOMAIN-SUFFIX,")]
    ipcidr = [r for r in rules if r.startswith("IP-CIDR,")]
    regex = [r for r in rules if r.startswith("URL-REGEX,")]
    other = [r for r in rules if r not in suffix and r not in ipcidr and r not in regex]

    body = []
    if suffix:
        body.append("# ---------- 域名后缀拦截 ----------")
        body.extend(suffix)
    if ipcidr:
        body.append("# ---------- IP 拦截 ----------")
        body.extend(ipcidr)
    if other:
        body.append("# ---------- 其他 ----------")
        body.extend(other)
    if regex:
        body.append("# ---------- URL 正则拦截（置于末尾） ----------")
        body.extend(regex)

    content = "\n".join(header + body) + "\n"

    print("=== 转换统计 ===")
    for k, v in stats.most_common():
        print(f"  {k}: {v}")
    print(f"\n  >>> 最终 Loon 规则数: {len(rules)}")
    print(f"      域名后缀 {len(suffix)} / IP {len(ipcidr)} / 正则 {len(regex)} / 其他 {len(other)}")

    if not args.check:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n已写入 {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
