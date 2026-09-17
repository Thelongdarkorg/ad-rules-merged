# 浮风拦截规则 (ad-rules-merged)

多个上游广告拦截订阅规则的**自动合并 + 去重**仓库。每天定时把若干优质规则源拉取、分类、去重，产出单一的 `merged.txt`，可直接作为广告拦截器的订阅地址使用。

> 仓库为 **Public 只读**——所有人可查看与订阅，仅维护者本人可写入。如需补充规则源，请提 Pull Request。

---

## 📥 订阅地址

```
https://raw.githubusercontent.com/Thelongdarkorg/ad-rules-merged/main/merged.txt
```

把上面这条地址添加到你的广告拦截器即可（见下方「如何使用」）。

---

## 🔄 自动同步机制

同步由 GitHub Actions 工作流（`.github/workflows/sync.yml`）驱动，无需人工干预：

| 触发方式 | 说明 |
|---|---|
| 每日定时 | 每天 **UTC 02:21** 自动运行一次 |
| 推送触发 | 修改 `merge.py` 或工作流文件后自动重跑 |
| 手动触发 | 在仓库 **Actions → Sync Merged Ad Rules → Run workflow** 手动执行 |

工作流运行 `merge.py` → 拉取上游 → 合并去重 → 生成 `merged.txt` → 若无变化则跳过提交，有变化则自动 push 回 `main` 分支。

---

## 📊 当前规则规模

- 单文件 `merged.txt`，约 **1.8 万条**规则（随上游动态变化，详见文件头部 `Total rules`）
- 拦截器建议刷新间隔：**12 小时**（文件头 `Expires: 12 hours`）

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
3. 粘贴订阅地址，保存并启用

### uBlock Origin（浏览器扩展）
1. 打开 uBlock Origin 设置 → **过滤器列表 → 自定义**
2. 在「导入」处粘贴订阅地址 → 应用

### 其他兼容 Adblock Plus 2.0 语法的工具
凡支持 ABP2.0 订阅格式的工具，均可直接导入上面的 `merged.txt` 地址。

---

## 🤝 如何贡献

本仓库仅维护者本人可写入。如果你发现某条规则有误、或希望加入新的上游源：

1. **Fork** 本仓库
2. 修改 `merge.py` 中的 `SOURCES`（增删上游 URL）或调整分类/去重逻辑
3. 提交 **Pull Request**，由维护者审核合并

---

## ⚠️ 免责声明

- 本仓库规则**聚合自第三方公开源**，不对其完整性与准确性作担保。
- 规则可能误伤正常网站，如遇到问题请使用拦截器的「临时禁用」或提交 PR 修正。
- 使用本规则产生的任何后果由使用者自行承担。

---

## 📮 反馈

规则误杀 / 漏杀反馈：QQ **1584574988**
