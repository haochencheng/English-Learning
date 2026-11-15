# Wordcraft · 职场英语学习室 v2.2

前后端分离的本机学习应用。词库、复习记录、拼写作答、表达草稿、视频信息、收藏和笔记全部保存在 SQLite 数据库。浏览器仅保留界面临时状态，并可读取旧版 localStorage 进行迁移。

当前项目目录：`/Users/cliff/workspace/English-Learning`。旧路径保留兼容链接，迁移与回退说明见 [目录迁移记录](docs/migration-2026-11-15.md)。

## 打开和启动

详细命令见 [启动指南](docs/启动指南.md)，包含日常启动、重启、停止、首次安装、日志和备份。

本机入口：[学习页面](http://127.0.0.1:8765/)。后端接口文档：[OpenAPI / Swagger](http://127.0.0.1:8766/docs)。

进入项目目录后启动、停止或重启：

```sh
cd '/Users/cliff/workspace/English-Learning'
python3 scripts/manage.py start
python3 scripts/manage.py status
python3 scripts/manage.py stop
python3 scripts/manage.py restart
```

`start` 使用独立后台进程启动前端和后端，终端退出后仍可使用；不是开机自启服务，电脑重启后需要再次运行。日志在 `.runtime/frontend.log` 和 `.runtime/backend.log`。若端口被其他应用占用，脚本会报错，不会终止其他应用。

首次安装或换电脑，先准备 Python 3.11+、Node.js 22.12+ 和 npm，再执行：

```sh
sh scripts/setup.sh
python3 scripts/manage.py start
```

本次已在 Python 3.14.4、Node.js 22.22.0 上验证。`setup` 按锁定版本安装依赖并构建，不清空数据库。已有服务运行时，请先停止服务再安装或升级。

## 日常使用

- **今日学习**：先复习到期词，再学习新词；三种自评由后端计算复习时间。
- **我的词库**：后端分页，每页 20 / 40 / 80 条，可跳页；搜索或分类变更回到首页。支持新增、编辑、归档词条。
- **场景练习**：拼写反馈中单词与例句分行显示，各有朗读按钮；英文释义单独标注。表达草稿自动保存，失败时可重试。
- **视频学习**：后端分页，每页 12 / 24 / 48 条，可跳页；支持主题、搜索和收藏筛选。翻页保留当前播放器与笔记。
- **采集资料**：导入一个 YouTube 链接、同步精选视频，或采集预设频道的最新相关视频。

当前数据库为 **1,200 个去重词条、100 个去重视频**。词库分为软件与求职 444、商务 233、雅思主题 523；包含 89 个简历命中词条。原有 48 词和学习记录保留，新增 1,152 词中 108 个配有原创情景例句，其余明确标为英文释义。视频仍由 YouTube 播放，不下载视频或音频文件；可获取的字幕及译文保存到数据库；网络、发布者设置、地区与登录要求可能影响播放。

## 视频原文、翻译和查词

选中视频后，会读取已保存的双语字幕；首次打开时尝试获取英文字幕及中文轨道/平台自动翻译。完整字幕写入数据库，界面分批展开（每次 80 段），搜索覆盖全文。支持时间跳转、显示/隐藏中文、逐段朗读、点击或选中单词查中文释义，以及朗读单词或所在英文段落。

本机已导入 401,614 个 ECDICT 本地词典词条，不改变原来的 1,200 个学习词库数量；已有学习词的工作语境释义优先。支持常见屈折词形还原，专有名词或未知词会明确提示。

当前实测一段 Oxford 面试视频成功保存 262 段英文及 262 段中文；另一段视频保存 414 段英文，但平台限制了中文翻译访问。不是全部 100 个视频都保证有双语字幕，也没有批量抓取全部视频字幕。没有可获取的字幕时支持导入 SRT / VTT / 逐行文本；不能取得译文时保留英文。详见 [字幕与查词说明](docs/video-transcripts.md)。

## YouTube 更新方式

| 方式 | 是否需要密钥 | 实际行为 |
| --- | --- | --- |
| 视频链接导入 | 否 | 读取公开 oEmbed 信息：标题、频道、封面；按视频 ID 更新或新增 |
| 同步精选视频 | 否 | 更新 `backend/seed/videos.json` 中的精选清单 |
| 频道最新视频 | 否 | 先尝试公开订阅源；不可用时读取公开频道列表，按英文标题关键词筛选 |
| 关键词检索 | 是 | 使用 YouTube Data API，按求职／商务／雅思方向查找可嵌入视频 |

预设频道为 BBC Learning English、Oxford Online English、IELTS Advantage。频道采集每个频道只读取公开列表的前 30 项，整个任务默认处理最多 30 个去重候选，可选上限 50 / 100；不是遍历整个频道历史。筛选根据标题关键词，属于相关性初筛，不是对视频内容逐段审核。公开网页结构变化会显示失败，已有资料不会被删除。

当前采集为手动点击或命令执行，**没有默认定时任务**。可在需要更新时运行：

```sh
PYTHONPATH=backend .venv/bin/python -m app.cli sync --mode channels
PYTHONPATH=backend .venv/bin/python -m app.cli sync --mode curated
```

启用关键词检索：复制 `.env.example` 为 `.env`，在本地文件中设置 `YOUTUBE_API_KEY`，然后重启后端。密钥只由后端读取，不提交到版本库，不进入浏览器。需要在 Google 项目中启用 YouTube Data API v3；配额和费用以该项目控制台为准。[官方入门说明](https://developers.google.com/youtube/v3/getting-started)

```sh
PYTHONPATH=backend .venv/bin/python -m app.cli sync --mode search --deck job --query 'English interview software engineer' --limit 50
```

关键词搜索通过官方 `nextPageToken` 翻页，每个任务最多请求 2 个搜索结果页、处理 100 个候选。上限指候选数量，重复或不可用视频不会形成新的记录；实际写入数量见采集日志。密钥已在本机配置并通过真实检索验证。

## 词库扩充与资料来源

可运行流程与来源见 [词库来源和维护](docs/vocabulary-sources.md)。`backend/seed/expanded.json` 是可审阅的词条快照；每词包含中文、英文例句或释义、内容类型及来源说明。个人简历原文和下载语料保存在被忽略的 `data/corpus/`，不进入前端或版本库。

`002_vocabulary_metadata` 迁移新增内容类型和来源字段。扩充种子按稳定词条 ID 和大小写归一化词面去重，仅新增，不覆盖编辑，也不恢复已归档词条。已入库词条的修订应通过页面编辑/API或独立受控迁移完成，不能靠覆盖种子强行重置。

## 数据、迁移和备份

默认数据库：`data/wordcraft.sqlite3`。可用 `.env` 中的 `WORDCRAFT_DB` 指定其他**绝对路径**。种子内容只在词条不存在时插入，重启不会覆盖已有编辑。

旧版进度：在相同浏览器、相同地址打开新页面，会检测尚未导入的旧进度，点击“合并到数据库”即可。也支持导入旧页面导出的 JSON。合并保留数据库中复习次数更多的记录和已有草稿，日进度取并集；原始浏览器记录不删除。不同浏览器或地址之间请使用 JSON 文件迁移。

完整数据库备份（包含学习词库、查词词典、视频、字幕及笔记）：

```sh
PYTHONPATH=backend .venv/bin/python -m app.cli backup
```

备份进入 `backups/`，使用 SQLite 在线备份接口，可在运行中执行。页面底部“导出进度”仅包含词汇复习进度和表达草稿；自定义词条、视频笔记与采集日志请用完整数据库备份。

恢复时先停止服务，将当前数据库及存在的 `-wal`、`-shm` 文件保留到另一个备份目录，再将所选 `.sqlite3` 备份复制到配置的数据库路径，最后启动服务。不要在服务运行时直接覆盖数据库。恢复后检查 `/api/health` 及学习数据。

`data/`、`.env`、备份和运行日志均被 `.gitignore` 排除；复制源码不等于备份学习数据。

## 结构与开发

```text
frontend/              独立前端，原生 ES modules + Vite
  src/api.js           HTTP 请求和错误处理
  src/store.js         从后端加载的数据与未保存草稿
  src/study.js         词卡、复习、拼写与表达
  src/content-editor.js 词条维护
  src/videos.js        视频列表、播放、笔记与采集状态
  src/pagination.js    两个列表共用的分页控件
  src/transcripts.js   双语字幕、查词、手动导入
  src/speech.js        共用语音朗读
backend/
  app/routes/          内容、学习、视频 API
  app/db.py            每请求连接、事务、初始化和迁移
  app/youtube.py       外部资料采集适配器
  app/transcripts.py   字幕获取、对齐、缓存与导入
  app/dictionary.py    本地词典及词形查询
  app/cli.py           初始化、采集、备份命令
  migrations/          按编号执行的 SQL 迁移
  seed/                初始词库及视频来源配置
  tests/               重要持久化与采集回归测试
scripts/               安装、启动、停止、重启、下载语料、构建词库
legacy/index.html      原单文件版，仅供迁移参考
```

开发前先停止后台服务，在两个终端分别运行：

```sh
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8766 --reload
```

```sh
npm --prefix frontend run dev
```

构建和验证：

```sh
npm --prefix frontend run build
.venv/bin/python -m pytest -q -c backend/pytest.ini
```

前端变更后重新构建并重启即可。数据库结构变更请新增 `004_*.sql` 等迁移文件，不修改已执行的迁移；数据库备份应先于结构升级。

当前是单人本机版，服务仅绑定 `127.0.0.1`。若将来要部署给多人或跨设备访问，需要补充登录、用户数据隔离、HTTPS 和部署管理；当前不应直接改为公网监听。

详见 [技术方案](./技术方案.md) 与 [验收记录](./验收记录.md)。
