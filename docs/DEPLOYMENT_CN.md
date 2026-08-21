# 国内部署

第一阶段使用单服务部署：前端由 Starlette 提供，后端 API、腾讯 OCR 和 SQLite 数据都在同一台腾讯云服务器上。这样先验证真实 OCR 和核心流程，再拆分 COS/CDN 与 OpenAI Gateway。

## 服务器准备

安装 Docker 和 Docker Compose，将仓库检出到服务器。把腾讯云凭证文件放在服务器用户的 `~/.tencentcloud/credentials`，权限设为 `600`。不要把凭证提交到 Git。

```bash
cp .env.production.example .env.production
chmod 600 .env.production
docker compose -f docker-compose.production.yml up -d --build
curl http://127.0.0.1:8000/api/health
```

健康接口必须返回 `status: ok`、`synthetic_ocr: false`，且 `ocr_provider` 以 `tencentcloud-` 开头。防火墙只开放 80/443；8000 仅供 Nginx 或本机访问。

## OpenAI Agent

国内版本先使用 `hybrid_tfidf`，避免在没有明确数据跨境方案时把用户图片、健康约束或确认文本发送到境外。未来启用 OpenAI 时，在服务端设置 `FOOD_LABEL_RAG_PROFILE=hybrid_dense_rerank` 和 `OPENAI_API_KEY`，不在前端配置密钥。
