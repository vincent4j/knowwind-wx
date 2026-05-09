# wx-still

KnowWind 的微信数据源插件。从本机微信群采集消息，经策略清洗后推送给 KnowWind 决策平台。

**必须配合 [KnowWind](https://github.com/vincent4j/knowwind) 使用，无法单独运行。**

---

## 前提条件

1. 已安装并启动 [KnowWind](https://github.com/vincent4j/knowwind)
2. Windows、macOS 或 Linux
3. 微信桌面版已登录

---

## 安装

打开任意 AI Agent（Claude Code、Cursor、Windsurf 等），复制以下内容发送：

```
帮我安装 wx-still 微信插件：clone https://github.com/vincent4j/wx-still，安装依赖，注册开机自启。
```

AI 自动完成所有步骤。安装完成后，KnowWind 界面导航里自动出现「微信」入口。

---

## 前置依赖：wechat-decrypt

wx-still 通过 [wechat-decrypt](https://github.com/ylytdeng/wechat-decrypt) 读取本机微信消息。

**一次性初始化（微信升级后需重做第 1 步）：**

macOS：
```bash
# 1. 对微信重签名（允许读取进程内存，无需关闭 SIP）
sudo codesign --force --deep --sign - /Applications/WeChat.app

# 2. 安装 Python 依赖
cd /path/to/wechat-decrypt
pip install -r requirements.txt

# 3. 编译密钥扫描器
cc -O2 -o find_all_keys_macos find_all_keys_macos.c -framework Foundation
```

Windows / Linux：
```bash
# 安装 Python 依赖
cd /path/to/wechat-decrypt
pip install -r requirements.txt
```

**每次使用前启动服务（微信需在前台运行并已登录）：**

macOS：
```bash
cd /path/to/wechat-decrypt
sudo ./find_all_keys_macos
python3 main.py
```

Windows / Linux：
```bash
cd /path/to/wechat-decrypt
python3 main.py
```

服务启动后监听 `http://localhost:5678`。

> 密钥文件 `all_keys.json` 包含本机微信数据库密钥，**不要分享、不要提交 Git**。

---

## 配置

安装完成后，复制配置文件并编辑：

```bash
cp config.example.sh config.sh
```

必改项：

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `WECHAT_DECRYPT_URL` | wechat-decrypt 服务地址 | `http://localhost:5678` |
| `GROUP_KEYWORDS` | 目标微信群名称关键词，逗号分隔 | `AI大航海,5月航海` |
| `KNOWWIND_URL` | KnowWind 服务地址 | `http://localhost:8000` |

`config.sh` 已加入 `.gitignore`，不会被提交。

---

## 使用

安装完成后，所有操作在 KnowWind 界面里进行：

- **配置策略**：打开 KnowWind → 点击「微信」→ 选群、设置策略标签、补充自定义描述
- **采集消息**：点击右上角「采集」按钮，触发增量采集
- **查看结果**：采集完成后，insights 自动出现在 KnowWind 列表里
- **点评优化**：对单条或整体点评，AI 自动完善策略，可选立刻重跑

---

## 工作原理

```
wechat-decrypt（本机）
        ↓ 增量拉取
  规则粗过滤（系统消息、表情、短句）
        ↓
  LLM 精提取（批量，一次调用）
        ↓
  推送给 KnowWind REST API
```

LLM 使用 Claude Code 当前登录账号，无需额外配置。

---

## 文件结构

```
wx-still/
├── config.example.sh          # 配置模板
├── config.sh                  # 你的配置（不提交 Git）
├── AGENTS.md                  # AI 操作规则手册
├── docs/
│   └── TECH.md                # 技术实现文档
├── data/
│   └── wx_still.db            # 插件私有数据库
├── server/
│   └── main.py                # 后台服务（端口 8001）
├── ui/
│   └── index.html             # 配置界面（托管在 KnowWind）
└── scripts/
    ├── export-wechat-groups.sh  # 拉取微信消息
    ├── extract-insights.py      # 过滤 + LLM 提取
    └── push-insights.py         # 推送给 KnowWind
```

---

## 详细文档

- [AGENTS.md](./AGENTS.md)：AI 操作规则手册（完整提取规则、安全要求等）
- [docs/TECH.md](./docs/TECH.md)：技术实现文档（数据库设计、接口规范、数据流详解）
- [KnowWind DESIGN.md](./knowwind/docs/DESIGN.md)：整体产品架构设计
