# 浮风拦截规则 (ad-rules-merged)

多个上游广告拦截订阅规则的**自动合并 + 去重**仓库。每天定时把若干优质规则源拉取、分类、去重，产出 `merged.txt`（Adblock Plus 2.0 格式）与 `loon.txt`（Loon 规则格式），可直接作为广告拦截器的订阅地址使用。

> 仓库为 **Public 只读**——所有人可查看与订阅，仅维护者本人可写入。如需补充规则源，请提 Pull Request。

---

## 📥 订阅地址

### AdGuard / Adblock Plus / uBlock Origin（`merged.txt`）

```
https://raw.githubusercontent.com/Thelongdarkorg/ad-rules-merged/main/merged.txt
```

### Loon（`loon.txt`）

```
https://cdn.jsdelivr.net/gh/Thelongdarkorg/ad-rules-merged@main/loon.txt
```

> 为什么 Loon 订阅走 jsdelivr：`raw.githubusercontent.com` 在部分网络（含中国大陆）拉取不稳定、会静默失败，而 jsdelivr 镜像可达性更好。如需锁定某一版，把 `@main` 换成具体 commit sha 即可。

两个文件由同一次同步生成，内容同源、同步更新。

---

## 🔄 自动同步机制

同步由 GitHub Actions 工作流（`.github/workflows/sync.yml`）驱动，无需人工干预：

| 触发方式 | 说明 |
|---|---|
| 每日定时 | 每天 **UTC 02:21** 自动运行一次 |
| 推送触发 | 修改 `merge.py` / `to_loon.py` 或工作流文件后自动重跑 |
| 手动触发 | 在仓库 **Actions → Sync Merged Ad Rules → Run workflow** 手动执行 |

工作流依次执行：

1. `merge.py` → 拉取上游 → 合并去重 → 生成 `merged.txt`
2. `to_loon.py` → 读取 `merged.txt` → 转换为 Loon 语法 → 生成 `loon.txt`
3. 两个文件一起提交，若无变化则跳过 push

---

## 📊 当前规则规模

| 文件 | 格式 | 规则数 | 适用 |
|---|---|---|---|
| `merged.txt` | Adblock Plus 2.0 | 约 3.4 万条 | AdGuard Home / AdGuard / uBlock Origin 等 |
| `loon.txt` | Loon 规则语法 | 约 2.0 万条 | Loon 及兼容其规则语法的工具 |

（随上游动态变化，详见各文件头部 `Total rules`；拦截器建议刷新间隔 **12 小时**）

---

## 🔧 Loon 转换规则说明（`to_loon.py`）

Adblock 语法与 Loon 语法差异较大，转换遵循以下原则，**以不误伤为优先**：

| 原始类型 | 处理方式 | 理由 |
|---|---|---|
| `\|\|domain^` | → `DOMAIN-SUFFIX,domain,REJECT` | 一对一映射 |
| `0.0.0.0 domain`（hosts） | → `DOMAIN-SUFFIX,domain,REJECT` | 含 `*` 通配时取后缀匹配 |
| `@@` 例外规则 | **不输出**，改为「豁免集」 | 从 REJECT 列表里剔除对应域名；若转成 `DIRECT` 会强制直连、改变原有代理策略 |
| 带路径规则 `\|\|domain/path` | → `URL-REGEX` | Loon 无路径语法，置文件末尾 |
| `##` / `#@#` / `#?#` 元素隐藏 | 丢弃 | Loon 不支持 |
| 带 `$domain=` 等条件修饰语 | 丢弃 | Loon 无条件语法，强行转换会误伤非目标站点 |
| 纯 IP 规则 | → `IP-CIDR,ip/32,REJECT,no-resolve` | — |

输出前做安全校验：逗号会破坏 Loon 的 CSV 解析、非法正则会导致整个订阅加载失败，这类规则一律丢弃。

---

## 🌐 上游规则源

规则来自以下公开订阅（在 `merge.py` 的 `SOURCES` 中维护，可自由增删）：

1. **banad/jiekouAD** — `damengzhu/banad` 的接口广告规则
2. **AWAvenue-Ads-Rule** — `TG-Twilight/AWAvenue-Ads-Rule` 主流广告拦截规则
3. **qq5460168/666/rules** — `qq5460168/666` 规则集

`merge.py` 会对所有上游做**全局去重（忽略大小写，保留首次出现的写法）**，并按类别归类：

| 类别 | 识别方式 | 说明 |
|---|---|---|
| 拦截规则 (blocking) | `\|\|...` 等 | 网络层拦截 |
| 元素隐藏 (cosmetic) | `##`、`#@#`、`#?#` | 页面元素隐藏 |
| 例外规则 (exceptions) | `@@` 开头 | 置于末尾，优先覆盖误杀 |

---

## 🛠 如何使用

### AdGuard Home / AdGuard 客户端
1. 打开 AdGuard 设置 → **过滤器 / DNS 黑名单**
2. 选择「添加自定义过滤器」→「按 URL 导入」
3. 粘贴 `merged.txt` 订阅地址，保存并启用

### uBlock Origin（浏览器扩展）
1. 打开 uBlock Origin 设置 → **过滤器列表 → 自定义**
2. 在「导入」处粘贴 `merged.txt` 订阅地址 → 应用

### Loon（iOS）
1. Loon → **订阅** → 右上角「+」→ **规则集 / Remote Rule**
2. 订阅链接填 `loon.txt` 地址（jsdelivr），类型选 **规则（Rule）**
3. 保存后在需要的位置引用该规则集（策略选 REJECT 已内建于规则本身）

### 其他兼容 Adblock Plus 2.0 语法的工具
凡支持 ABP2.0 订阅格式的工具，均可直接导入 `merged.txt` 地址。

---

## 🤝 如何贡献

本仓库仅维护者本人可写入。如果你发现某条规则有误、或希望加入新的上游源：

1. **Fork** 本仓库
2. 修改 `merge.py` 中的 `SOURCES`（增删上游 URL）或调整分类/去重逻辑
3. 修改 `to_loon.py` 可调整 Loon 转换策略
4. 提交 **Pull Request**，由维护者审核合并

---

## ⚠️ 免责声明

- 本仓库规则**聚合自第三方公开源**，不对其完整性与准确性作担保。
- 规则可能误伤正常网站，如遇到问题请使用拦截器的「临时禁用」或提交 PR 修正。
- 使用本规则产生的任何后果由使用者自行承担。

---

## 📮 反馈

规则误杀 / 漏杀反馈：QQ **1584574988**
