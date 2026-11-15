# 词库来源与维护

2026-11-15 快照：1,200 个不同词面。软件与求职 444、商务 233、雅思主题 523。保留最初 48 词，新增 1,152 词。

## 内容来源与标注

| 来源 | 用途 |
| --- | --- |
| 本机 Chencheng_Hao_AI_Resume_EN.docx | 词面匹配提取；89 个新增词命中，覆盖零停机部署、服务发现、佣金结算、数据摄取等 |
| [Python 官方术语表](https://docs.python.org/3/glossary.html) | 软件词汇的真实语料和出处 |
| [PostgreSQL 官方术语表](https://www.postgresql.org/docs/current/glossary.html) | 数据库、事务和存储词汇 |
| [Google 工程实践](https://github.com/google/eng-practices) | 代码审查、沟通和提交变更的工作场景 |
| [Google 技术写作](https://developers.google.com/tech-writing/one/words) | 技术表达与写作相关词汇 |
| [ECDICT 双语词典](https://github.com/skywind3000/ECDICT) | 英文与中文基础释义，保留其 [MIT 许可证](licenses/ECDICT-LICENSE.txt) |
| 自主主题选编 | 商务协作、财务、工作与社会、教育与环境、学术表达，以及原词表没有覆盖的技术表达 |

语料已下载到本机 data/corpus/。使用英文词边界做候选词匹配；一个词有多个来源时优先标记简历，其次标记下载语料。命中证明词面出现，不等同于整条例句来自原文。没有下载论文，本次采用官方软件文档和工程实践文章作为软件资料。

新增词中 108 个配有原创情景例句和中文译文，其余为英文释义与中文释义。技术多义词另有自主修订，如 daemon、bootstrap、thread、deployment、constructor，避免误用神话、服装、军事等含义。词典导入部分不声称已逐词达到教材编辑标准；可持续修订释义、搭配和例句。

所有词条均有中文含义、英文内容和来源说明；没有合适搭配的词条允许留空，不生成无意义搭配。界面明确区分“英文释义”和“情景例句”；编辑时可以改变类型并补充自己的真实工作句子。

雅思主题是学习选编，不是雅思官方词表或必考清单。主题候选由脚本中的候选集合控制；候补选择使用 ECDICT 的 IELTS 标签和词频，不能把这些标签当作官方资格。使用的词典数据保留其开源许可证；未把第三方文章全文塞进公开词条。

## 私有资料

简历只在本机解析。词条快照不包含简历全文、联系方式、公司履历原句或电话号码。data/corpus/resume.private.txt 和全部下载缓存位于忽略目录，不随源码提交，也不会通过前端接口提供。来源说明仅标识“个人简历提取”；学习释义链接指向公开词典，原简历不会上传。

## 可重跑流程

在项目根目录执行。首次下载词典约 63 MB；后续不需要重复下载即可构建。

```sh
.venv/bin/python scripts/fetch_corpus.py --dictionary --resume '/Users/cliff/workspace/learn/工作/Chencheng_Hao_AI_Resume_EN.docx'
.venv/bin/python scripts/build_vocabulary.py
```

构建结果：

- backend/seed/expanded.json：稳定词条 ID、分类、中英文内容、来源和内容类型。
- backend/seed/context_glossary.tsv：人工编写的工作语境例句与双语解释。
- backend/seed/definition_overrides.tsv：技术多义词的工作语境释义修订。
- backend/seed/vocabulary_provenance.json：词条来源映射、原文 URL、许可证名称和下载文本 SHA-256；不保存简历原文。

构建器不连接应用数据库。先审阅内容，再备份并重启服务，初始化会补入尚不存在的词条。它不会覆盖已编辑词条，也不会恢复已归档词条。已入库词条的修订请使用页面编辑/API，批量修订应另外编写带备份和精确范围的迁移。

为保持当前快照，重跑时使用现存 data/corpus 缓存；重新下载会读取来源的最新内容，输出可能改变。归档当前词条 JSON 和来源清单可以保留旧版本。脚本当前目标固定为 1,200 词，继续扩充时需要同步调整目标、候选集及种子计数测试。

## 视频更新

本次使用已配置的官方 API 密钥，按软件面试、商务会议谈判、雅思口语检索并获取元信息，新增 66 个不同视频，数据库合计 100 个。视频不是素材下载文件，播放器直接使用 YouTube。

界面采集可设置 30 / 50 / 100 个候选。命令行支持 1–100：

```sh
PYTHONPATH=backend .venv/bin/python -m app.cli sync --mode search --deck business --query 'business English meetings communication' --limit 50
```

记录按 YouTube ID 去重，采集日志显示写入/更新数量；重新采集不会覆盖笔记或收藏。相关性由查询、标题和频道筛选，未逐段验证内容、音轨语言或发布者所称分数。人工精听后可收藏值得复习的视频。
