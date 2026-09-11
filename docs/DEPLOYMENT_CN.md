# 国内部署

第一阶段使用单服务部署：前端由 Starlette 提供，后端 API、腾讯 OCR 和 SQLite 数据都在同一台腾讯云服务器上。这样先验证真实 OCR 和核心流程，再拆分 COS/CDN 与 OpenAI Gateway。

## 服务器准备

安装 Docker 和 Docker Compose，将仓库检出到服务器。把腾讯云凭证文件放在服务器用户的 `~/.tencentcloud/credentials`，权限设为 `600`。不要把凭证提交到 Git。

```bash
cp .env.production.example .env.production
# 填写两个不同的随机令牌、OpenAI API Key、HTTPS 公开地址和明确的受信任域名
chmod 600 .env.production
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
curl http://127.0.0.1:8000/api/ready
```

`/api/ready` 必须返回 HTTP 200，并确认 SQLite 检查点、长期记忆和短期对话均为 durable、自由对话模型已配置、官方目录可加载、OCR 不是 synthetic。`/api/health` 用于查看处理方式披露、公开地址等诊断信息。防火墙只开放 80/443；8000 仅供 Nginx 或本机访问。

所有页面在生产模式下都受共享访问令牌保护。浏览器首次访问会显示 HTTP Basic 登录框：用户名可留空或任意填写，密码使用 `FOOD_LABEL_SITE_ACCESS_TOKEN`。发现队列刷新接口还必须单独提供 `FOOD_LABEL_DISCOVERY_ADMIN_TOKEN`，不要在前端保存这个管理员令牌。共享口令只适合受控试用；面向多用户公开发布前仍需接入独立账户、服务端会话、撤销机制和租户级数据隔离。

Remote 开发环境可在设置上述两个令牌后执行 `scripts/run_remote_platform.sh`。脚本监听 `0.0.0.0`，并优先采用平台注入的 `PORT`；从本机访问时使用平台的端口转发地址，不要写死 `localhost:8000`。生产环境在 `.env.production` 中设置 `FOOD_LABEL_PUBLIC_BASE_URL=https://<你的域名>`，并将 `FOOD_LABEL_ALLOWED_HOSTS` 设置为逗号分隔的精确域名（不能使用 `*`）；健康接口会回报公开地址以便自检。`FOOD_LABEL_DATA_DIR` 必须指向平台的持久卷，否则重启后档案与工作流状态会丢失。

浏览器写请求使用同源校验：通过站点 HttpOnly Cookie 发出的 POST、PUT、PATCH、DELETE 必须携带与当前 Host 一致的 `Origin`。跨站 Origin 或缺失 Origin 的 Cookie 写请求都会以 403 关闭；纯服务端 Bearer 调用不依赖 Cookie，允许不携带 Origin。

官方目录默认在当前类别已有 3 件完整记录时不请求社区实时补充源，避免 Remote 网络受限时不必要地降级。如需更宽的实时目录，可调高 `FOOD_LABEL_OFFICIAL_MINIMUM_RECORDS`；补充源失败只会降低广度，不会放宽证据门。

## OpenAI Agent

自由对话首版使用 `gpt-5.6-terra`，生产启动要求服务端设置 `OPENAI_API_KEY`；密钥不得写入前端或仓库。对话请求使用 `store: false`，原始图片不发送给对话模型。普通问题由网页逐个短期会话征得明确同意，服务端也会拒绝缺少 `remote_processing_consent=true` 的请求；该产品控制不替代部署方对个人信息跨境处理、告知、单独同意、安全评估或标准合同等适用义务的专业合规审查。

```bash
FOOD_LABEL_CHAT_PROVIDER=openai
FOOD_LABEL_CHAT_MODEL=gpt-5.6-terra
FOOD_LABEL_CHAT_REASONING_EFFORT=low
FOOD_LABEL_CHAT_RETENTION_HOURS=24
OPENAI_API_KEY=由密钥管理服务注入
```

国内法规检索仍可使用 `hybrid_tfidf`，避免额外发送法规查询与候选条款。如完成相应数据处理评估后启用远程 RAG，再设置 `FOOD_LABEL_RAG_PROFILE=hybrid_dense_rerank`；所有远程能力共用服务端 API Key，但拥有独立开关。
