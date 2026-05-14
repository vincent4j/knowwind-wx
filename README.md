# knowwind-wx

KnowWind 的微信数据源插件。从本机微信群采集消息，经策略清洗后推送给 KnowWind 决策平台。

**必须配合 [KnowWind](https://github.com/vincent4j/knowwind) 使用，无法单独运行。**

---

## 前提条件

- Python 3.10+
- git
- 微信桌面版已登录（macOS 需 `/Applications/WeChat.app`）
- 已安装并启动 [KnowWind](https://github.com/vincent4j/knowwind)

---

## 安装

```bash
curl -fsSL https://raw.githubusercontent.com/vincent4j/knowwind-wx/main/install.sh | sh
```

安装程序自动完成：

- 克隆仓库到 `~/.knowwind/wx/`
- 创建 Python 虚拟环境并安装依赖
- macOS：对微信做 ad-hoc 重签名、提取解密密钥、启动 wechat-decrypt 服务
- 创建 `knowwind-wx` 和 `knowwind-wx-decrypt` 命令

---

## 配置

```bash
cp ~/.knowwind/wx/.env.example ~/.knowwind/wx/.env
# 编辑 .env，填入目标群关键词和 KnowWind 地址
```

必改项：

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `GROUP_KEYWORDS` | 目标微信群名称关键词，逗号分隔 | `AI大航海,5月航海` |
| `KNOWWIND_URL` | KnowWind 服务地址 | `http://localhost:8000` |

`.env` 已加入 `.gitignore`，不会被提交。

---

## 启动

```bash
knowwind-wx run
```

启动后 KnowWind 自动检测到插件在线，导航里出现「微信」入口。

验证：

```bash
knowwind-wx status
# → ✅ 运行中 — {"status": "ok"}
```

---

## macOS 重启或微信更新后

wechat-decrypt 需要重新提取解密密钥，运行：

```bash
knowwind-wx-decrypt
```

---

## 使用

所有操作在 KnowWind 界面里进行：

- **同步群列表**：打开 KnowWind → 微信 → 点击「同步群」
- **配置策略**：选群、设置策略标签、补充自定义描述
- **采集消息**：点击「采集」按钮，触发增量采集
- **查看结果**：采集完成后，insights 自动出现在 KnowWind 列表里
- **点评优化**：对单条或整体点评，AI 自动完善策略

---

## 工作原理

```
wechat-decrypt（本机，:5678）
        ↓ 增量拉取
  规则粗过滤（系统消息、表情、短句）
        ↓
  LLM 精提取（Claude，批量一次调用）
        ↓
  推送给 KnowWind REST API（:8000）
```

LLM 使用 Claude Code 当前登录账号，无需额外配置。

---

## 详细文档

- [AGENTS.md](./AGENTS.md)：AI 操作规则手册（完整提取规则、接口规范、安全要求）
- [docs/TECH.md](./docs/TECH.md)：技术实现文档（数据库设计、数据流详解）
- [docs/SETUP.md](./docs/SETUP.md)：开发环境启动指南

