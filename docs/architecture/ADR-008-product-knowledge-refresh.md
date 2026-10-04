# 商品候选知识库与定时复查

日期：2026-10-03

## 行为

外部商品查询得到的候选独立持久化到 `FOOD_LABEL_DATA_DIR/product-knowledge.sqlite3`。缺少配料或完成标记的商品也保留；按品类、名称、品牌或配料原文查询，不进入已审核推荐目录。相同条码可以属于多个品类。当前属于候选证据库，不声称已经实现商品向量检索。

Open Food Facts 搜索结果不完整时，每轮最多补查 5 件商品详情，包括“有配料文字但缺少完成标记”的情况。默认每个自然月检查一次麦片、乳制品、饮料各前 50 条结果，并按最早检查时间补查最多 5 件已入库但不在本次搜索页内的商品。每次请求至少间隔 7 秒。不是全量镜像，也不保证每件商品每月检查；商品级检查时间如实返回。

官方来源和配料图片补齐也每个自然月执行一次。按执行日期计算下个月同日；下个月没有对应日期时取月末。失败或部分失败也保留月度周期，不再每小时自动重试；保留上次成功时间和证据，可由管理员手动重试。独立进程持有文件锁，多个 worker 不会同时执行；网页查询不再触发抓取。两种来源不自动互相拼接配料。

## 时间与证据语义

- `last_attempt_at`：任务最近尝试时间。
- `last_success_at`：该任务最近完整成功时间；失败不刷新。
- `next_check_at`：计划复查时间，不保证届时一定执行；超过时间显示延迟。
- `last_checked_at`：具体商品成功取得数据的时间。
- `source_updated_at`：外部来源自己的更新时间，缺失为未知。
- `verified_at`：本库中的人工核实时间。同步及 OCR 均不填写，不将来源更新时间伪装成人工核实时间。
- 内容变化后标记 `change_detected` 并清除旧 OCR 草稿。相同内容的重复抓取不刷新内容变化时间。

## OCR 补齐与审核边界

后台图片识别默认启用，使用项目配置的真实 OCR Provider（未指定时默认腾讯 OCR）；拒绝演示 Provider。只抓取 HTTPS `images.openfoodfacts.org` 图片，不跟随重定向，限制图片大小，再复用原有图像质量检查。已入库商品每月逐条补查详情（核对返回条码），随后对所有已有的配料图和营养图进行识别；图片补齐先于耗时的官方来源复查执行，不再每轮限于 5 张图片，失败候选按最近尝试时间轮转。识别结果按来源内容哈希绑定存为草稿，不写回已核实配料，必须核对同一条码、规格、口味、销售地区及包装版本。

本轮提供图片识别草稿的持久化基础，现有包装证据捕获、双人复核和官方发现审核仍是正式目录入口。社区商品不会自动成为官方商品，不能直接将社区 OCR 草稿批准成官方证据。官方来源没有完整包装时仍需补拍或厂家资料。

## 运行

一次到期检查：

```sh
python -m food_label_agent.alternatives.refresh --once
```

持续调度（每 30 秒检查是否到期，业务请求按上述周期执行）：

```sh
python -m food_label_agent.alternatives.refresh
```

`--force --once` 忽略下一次检查时间，适合管理员维护。后台默认启用真实图片识别并使用现有腾讯 OCR 配置。`--no-ocr` 可显式暂停后台识别，`--ocr` 可覆盖环境变量重新启用；不改变用户上传识别配置。

环境变量：

- `FOOD_LABEL_DATA_DIR`：Web 与 worker 必须使用同一持久化目录。
- `FOOD_LABEL_KNOWLEDGE_CATEGORIES`：默认 `breakfast_cereal,dairy,drink`。
- `FOOD_LABEL_KNOWLEDGE_OCR`：默认 `1`，沿用配置好的真实 OCR；设为 `0` 仅暂停后台图片补齐。

生产 Compose 已添加 `knowledge-refresh` 服务，与 Web 共用数据卷；部署并运行该服务之后才有后台定时检查。仅修改代码或打开网页不会启动任务。未运行时页面显示尚无记录，停机过期后显示复查延迟。

## 查询与归因

`GET /api/v1/alternatives/knowledge?category=dairy&q=商品名` 返回候选摘要、来源、时间及任务状态。返回的候选明确标记 `recommendation_eligible=false`；接口不公开原始 OCR 草稿。前台显示至多 5 件待核实线索，正式推荐流程仍走原有证据和用户约束检查。

候选库保留 Open Food Facts 来源与 ODbL 归因，不把该社区数据复制到官方目录。正式分发数据库时需按数据源许可处理；参考 [Open Food Facts API 文档](https://openfoodfacts.github.io/openfoodfacts-server/api/)。

## 本机后台服务

本机 Web 和知识库更新进程都读取 `~/.config/food-label-agent/.env`，并默认共用 `~/.local/share/food-label-health-agent`。可通过其中的 `FOOD_LABEL_DATA_DIR` 覆盖；两者必须一起重启以加载目录变更。

安装并立即启动，之后登录自动启动、异常退出自动恢复：

```sh
./scripts/install_local_knowledge_autostart.sh
```

服务名：`com.foodlabel.knowledge-refresh`。它是 macOS 用户级 LaunchAgent，退出 Codex 不影响运行；机器关机、睡眠或用户退出登录期间不能保证执行，恢复运行后补做已到期检查。

日志：`~/Library/Logs/food-label-agent/knowledge-refresh.out.log` 和 `knowledge-refresh.err.log`。

```sh
# 查看状态
launchctl print "gui/$(id -u)/com.foodlabel.knowledge-refresh"
# 暂停，直到再次 bootstrap 或下次登录
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.foodlabel.knowledge-refresh.plist"
```

网页可通过 `/api/v1/alternatives/knowledge` 读取正式候选库。首次完整同步可能需要几分钟；API 限流、官网超时与图片识别失败均以实际状态记录，不把服务已启动等同于同步成功。

## 补齐质量控制（2026-10-03）

图片识别使用同语言、同包装图版本的高清 `full` 图片，避免 400 像素展示图被质量检查拒绝。格式依据 [Open Food Facts 官方图片文档](https://openfoodfacts.github.io/openfoodfacts-server/api/how-to-download-images/)。识别不到对应配料/营养字段不会保存为成功草稿；配料和营养图分别留存来源、图片哈希和识别字段，部分成功不会跳过剩余图片。所有草稿仍需身份和内容复核。

`ProductKnowledgeStore.coverage()` 输出逐商品缺口及来源字段覆盖率，字段存在与人工核实分开计数，零营养值不误判为缺失。普通接口成功、字段存在和 OCR 草稿成功均不能表述为知识库已经完整。
