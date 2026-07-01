# 金融公告问答系统

基于 RAGFlow 搭建的上市公司公告问答系统。一只股票对应一个知识库 + 一个 Chat Assistant，自动从巨潮资讯网抓取公告并解析。

## 功能特性

- 📈 **一只股票一个 Chat**：每只股票独立知识库、独立问答助手
- 📄 **自动抓取公告**：从巨潮资讯网 (cninfo.com.cn) 抓取全部公告
- 🔄 **增量同步**：只下载新增公告，避免重复
- ⏰ **定时任务**：每天自动检测并同步新公告
- 🖥️ **前端管理界面**：顶部导航新增「股票管理」「公告中心」
- 🔍 **引用溯源**：回答基于公告原文，可查看具体出处

## 前置准备

1. 进入 http://localhost 完成管理员注册
2. **设置 → Model Providers** 中添加：
   - Embedding 模型，例如 `BAAI/bge-m3@SILICONFLOW`
   - LLM，例如 `glm-4-flash@ZHIPU-AI`
3. **头像 → API Keys** 生成 API Key

## 安装依赖

```bash
cd examples/financial_qa
pip install ragflow-sdk requests fastapi uvicorn
```

前端依赖在 `web/` 目录下：

```bash
cd web
npm install
```

## 启动完整系统

### 1. 启动 RAGFlow 后端

确保 Docker 中的 RAGFlow 服务已运行：

```bash
cd docker
docker compose -f docker-compose.yml up -d
```

### 2. 启动金融公告管理 API 服务

前端「股票管理」和「公告中心」页面依赖此服务：

```bash
cd examples/financial_qa
export RAGFLOW_API_KEY="your-api-key"
export RAGFLOW_BASE_URL="http://localhost:9380"
python api_server.py
# 默认监听 http://localhost:9500
```

### 3. 启动前端开发服务器

```bash
cd web
npm run dev
```

访问 http://localhost:9222，顶部导航栏会新增：
- **股票管理**：添加股票、触发同步
- **公告中心**：查看已同步公告及状态
- **聊天**：进入 Chat 后会显示股票代码/名称标签

## 使用方法

### Web 界面操作

1. 进入「股票管理」页面
2. 点击「添加股票」，输入股票代码（如 `000001`）
3. 系统自动创建知识库和 Chat Assistant
4. 点击「同步」按钮，自动从巨潮资讯网抓取全部公告
5. 进入「公告中心」查看同步进度
6. 进入「聊天」，选择对应股票的 Chat 进行提问

### 命令行操作（可选）

```bash
cd examples/financial_qa
export RAGFLOW_API_KEY="your-api-key"

# 添加股票
python announcement_fetcher.py --add-stock 000001 --stock-name 平安银行

# 同步该股票全部公告
python announcement_fetcher.py --sync-stock 000001

# 同步所有股票
python announcement_fetcher.py --sync-all

# 启动定时任务（每天 02:00 自动同步）
python sync_scheduler.py --time 02:00

# 命令行提问测试
python chat_example.py \
    --stock "000001_平安银行" \
    --question "2024年净利润是多少？"
```

### 本地批量导入（可选）

如果你已有整理好的本地公告：

```bash
# 目录结构：announcements/000001_平安银行/*.pdf
python setup_financial_kb.py \
    --announcements-dir ./announcements \
    --embedding-model "BAAI/bge-m3@SILICONFLOW" \
    --llm-id "glm-4-flash@ZHIPU-AI"
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `api_server.py` | FastAPI 管理接口服务，供前端调用 |
| `announcement_fetcher.py` | 公告抓取器：从 cninfo 下载并上传到 RAGFlow |
| `sync_scheduler.py` | 定时同步调度器 |
| `cninfo_client.py` | 巨潮资讯网 API 客户端 |
| `models.py` | SQLite 数据模型（股票、公告、同步日志） |
| `setup_financial_kb.py` | 本地公告批量导入脚本 |
| `chat_example.py` | 命令行问答示例 |

## 前端修改说明

新增/修改的前端文件：

| 文件 | 说明 |
|------|------|
| `web/src/pages/stocks/index.tsx` | 股票管理页面 |
| `web/src/pages/announcements/index.tsx` | 公告中心页面 |
| `web/src/services/financial-service.ts` | 金融 API 服务封装 |
| `web/src/layouts/components/global-navbar.tsx` | 顶部导航新增股票/公告入口 |
| `web/src/routes.tsx` | 新增 `/stocks`、`/announcements` 路由 |
| `web/src/locales/zh.ts` | 中文翻译 |
| `web/src/locales/en.ts` | 英文翻译 |
| `web/vite.config.ts` | 开发代理 `/api/financial` 到后端服务 |
| `web/src/pages/next-chats/chat/index.tsx` | Chat 顶部显示股票标签 |

## 数据库

默认使用同目录下的 `financial_qa.db` SQLite 数据库，包含：

- `stocks`：已接入的股票及关联的 KB/Chat ID
- `announcements`：已下载/上传的公告记录
- `sync_logs`：每次同步的历史日志

## 注意事项

1. **请求频率**：抓取公告时请保持合理间隔（默认 1 秒），避免对巨潮资讯网造成压力。
2. **解析耗时**：首次同步大量 PDF 可能需要较长时间，脚本会自动轮询解析状态。
3. **内存要求**：PDF 解析期间 RAGFlow 容器内存可能达到 4-5GB，请保持 Docker Desktop 8GB+ 内存。
4. **生产部署**：生产环境需要在 Nginx 中配置 `/api/financial` 代理到 `api_server.py` 服务。
5. **法律合规**：本工具仅用于学习和研究，请遵守相关法律法规和网站使用条款。
