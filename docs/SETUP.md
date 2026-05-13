# knowwind-wx 启动指南

## 前置条件

- macOS，微信 4.x 正在运行
- Python 3.10+
- KnowWind 后端已启动（默认 `http://localhost:8000`）

## 启动顺序

**必须按顺序启动：** KnowWind → wechat-decrypt → knowwind-wx

### 1. 启动 KnowWind

```bash
cd /Users/vincent4j/Tools/Source/knowwind
.venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

### 2. 启动 wechat-decrypt

```bash
cd /Users/vincent4j/Tools/Source/wechat-decrypt
.venv/bin/python main.py
```

监听 `http://localhost:5678`，启动后自动：
- 从微信进程内存提取加密密钥（需要微信正在运行）
- 解密数据库到 `decrypted2/` 目录
- 实时监听新消息（WAL 增量 + SSE 推送）

### 3. 启动 knowwind-wx

```bash
cd /Users/vincent4j/Tools/Source/knowwind-wx
.venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 8001
```

启动时自动注册到 KnowWind（`POST /api/plugins/register`）。

## 验证启动成功

```bash
# 三个服务都应返回 ok
curl http://localhost:8000/health
curl http://localhost:5678/     # 返回 HTML 页面
curl http://localhost:8001/health

# knowwind-wx 已注册到 KnowWind
curl http://localhost:8000/api/plugins
# 应看到 name: "wechat" 的插件
```

## 采集流程

```bash
# 1. 同步群列表（从 wechat-decrypt 的消息中提取匹配的群）
curl -X POST http://localhost:8001/groups/sync

# 2. 查看已注册的群
curl http://localhost:8001/groups

# 3. 触发采集
curl -X POST http://localhost:8001/collect -H "Content-Type: application/json" -d '{}'

# 4. 查看采集结果
curl http://localhost:8001/logs?limit=5
curl 'http://localhost:8000/api/insights?source=wechat'
```

## 常见问题

### wechat-decrypt 启动报 `PermissionError`

**症状：** `decrypted/` 目录下的文件属于 root，导致写入失败。

**原因：** 之前用 sudo 运行过，产生了 root 所有的文件。

**解决：**
```bash
# 删除旧的 decrypted 目录（需要 sudo）
sudo rm -rf /Users/vincent4j/Tools/Source/wechat-decrypt/decrypted

# 或者改 config.json 使用新目录名
# 把 "decrypted_dir": "decrypted" 改为 "decrypted_dir": "decrypted2"
```

### 端口被占用 `Address already in use`

```bash
# 找到占用端口的进程并杀掉
lsof -ti:5678 | xargs kill -9   # wechat-decrypt
lsof -ti:8001 | xargs kill -9   # knowwind-wx
```

### 缺少 Python 依赖

wechat-decrypt 需要 `pycryptodome` 和 `zstandard`。如果系统 Python 受 PEP 668 保护，装到 venv 里：

```bash
cd /Users/vincent4j/Tools/Source/wechat-decrypt
.venv/bin/pip install pycryptodome zstandard
```

如果 `.venv` 权限有问题，重建：
```bash
sudo rm -rf .venv
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 采集后没有新 insights

**检查采集日志：**
```bash
curl http://localhost:8001/logs?limit=3
```

- `message_count=0`：该群没有新消息，或 wechat-decrypt 没捕获到
- `candidate_count=0`：消息被规则过滤掉了（不含关键词、太短、纯表情等）
- `insight_count=0`：LLM 没提取到有价值内容
- `pushed_count=0`：推送失败（检查 KnowWind 是否在运行）

**候选关键词（触发提取的词）：** 请问、怎么、如何、为什么、能不能、有没有、报错、安装、登录、问题 等。群聊消息需要包含这些词才会进入提取流程。

### 群没有出现在 knowwind-wx 里

knowwind-wx 只同步名称匹配 `GROUP_KEYWORDS` 的群。检查 `.env`：

```bash
# 匹配所有群（不限关键词）
GROUP_KEYWORDS=

# 匹配指定关键词的群（逗号分隔）
GROUP_KEYWORDS=AI大航海,技术交流
```

修改后需要重启 knowwind-wx。

## 架构简图

```
微信进程 (macOS)
    │
    ▼
wechat-decrypt (:5678)
    │ 解密数据库 + 实时监听
    ▼
knowwind-wx (:8001)
    │ 规则过滤 → LLM 提取 → 推送
    ▼
KnowWind (:8000)
    │ REST API + 前端展示
    ▼
浏览器 (:5173 / :8000)
```
