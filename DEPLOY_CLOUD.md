# PetroPID-Agent 公网 HTTPS 一键部署指南（拿满 Demo 演示链接 10 分）

为了让**大赛评委（国内网络环境）**和 **ChatGPT** 都能随时稳定访问你的 Web Demo，下面提供 3 种一步到位方案，**强烈首选方案一（国内访问最快、免费 HTTPS、免备案）**：

---

## 方案一：魔搭社区 ModelScope 创空间（最推荐！国内评委秒开、免费 HTTPS）
1. 注册/登录魔搭社区：https://modelscope.cn
2. 点击顶部 **「创空间」→「创建创空间」**：
   - SDK 类型选择 **Docker**
   - 空间名称填 `PetroPID-Agent`，可见性设为 **公开**
3. 创建后，将 `D:\石油\PetroPID-Agent\` 文件夹内的全部文件推送到该创空间 Git 仓库（或在网页端直接上传）：
   ```bash
   cd D:\石油\PetroPID-Agent
   git init
   git add .
   git commit -m "Deploy PetroPID-Agent V2.0"
   git remote add origin https://www.modelscope.cn/studios/<你的用户名>/PetroPID-Agent.git
   git push -u origin master
   ```
4. 魔搭会自动读取根目录的 `Dockerfile` 完成构建（约 2–3 分钟），构建成功后即可获得**国内免翻墙、永久可访问的公网 HTTPS Demo 链接**！

---

## 方案二：HuggingFace Spaces / Render.com（海外及 ChatGPT 访问极佳）
- **HuggingFace Spaces**：新建 Space → 选择 **Docker (Blank)** → 推送 `D:\石油\PetroPID-Agent` 全部代码，自动监听 `7860` 端口上线。
- **Render.com**：将代码传至 GitHub，在 Render 点击 **New → Blueprint**，选择该仓库，Render 会自动识别 `render.yaml` 和 `Dockerfile` 一键生成 `https://petropid-agent.onrender.com`。

---

## 方案三：自有云服务器 / 华为云 ECS（Docker 2 条命令上线）
如果你已有华为云/阿里云服务器（或大赛发放的云主机），把 `PetroPID-Agent` 目录上传后运行：
```bash
cd PetroPID-Agent
docker build -t petropid-agent:v2 .
docker run -d -p 80:7860 --name petropid-agent --restart unless-stopped petropid-agent:v2
```
随后直接用 `http://<服务器公网IP>` 即可访问！

---

## 可选：接入真实大模型 API（让 AI 副驾驶支持任意自由多轮对话）
在任意上述云平台的**环境变量（Environment Variables）**中配置以下 3 项，即可从离线引擎无缝切换为真实在线大模型（支持 DeepSeek / 通义千问 / 昇腾 MindIE）：
- `PETROPID_LLM_BASE_URL`：如 `https://api.deepseek.com/v1` 或 `https://dashscope.aliyuncs.com/compatible-mode/v1`
- `PETROPID_LLM_API_KEY`：你的 API Key
- `PETROPID_LLM_MODEL`：如 `deepseek-chat` 或 `qwen-plus`
