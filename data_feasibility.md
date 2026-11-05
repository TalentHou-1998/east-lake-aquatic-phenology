# 平台与 GitHub 项目可行性核验

- 核验日期：2026-11-05
- 结论等级：`可直接使用`、`可改造`、`仅作参考`、`未发现专用项目`

| 平台/用途 | 项目 | 结论 | 本项目验证 |
|---|---|---|---|
| 抖音、快手关键词检索 | [TYP1227/Douyin_keyword_crawler](https://github.com/TYP1227/Douyin_keyword_crawler) | 可直接使用 | 已固定版本 `d25b29a`；抖音实测可导出文案、时间、POI、地址、坐标和帖子链接；仓库也声明支持快手 |
| 抖音媒体下载 | [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | 可直接使用但受许可证约束 | 已固定版本 `b059657`；实测 100/100 获取静态媒体，36 条保留完整视频 |
| 抖音替代实现 | [orange-suli/douyin_topic_crawler](https://github.com/orange-suli/douyin_topic_crawler) | 仅作备选 | 支持关键词、发布时间和链接，但未看到本研究必需的 POI/坐标字段验证 |
| 高德 POI 基础信息 | [Accright/java-map-spider](https://github.com/Accright/java-map-spider) | 可改造 | 适合 POI 名称、地址、类型和坐标；不能直接满足评价照片、评价文案和评价时间 |
| 高德网页评价 DOM 采样参考 | [ErikaAlk/trip-planner](https://github.com/ErikaAlk/trip-planner) | 可改造 | 项目记录了高德评价 HTML 面板选择器思路；仍需在当前登录网页上实测字段与翻页 |
| 快手 API 参考 | [ShilongLee/Crawler](https://github.com/ShilongLee/Crawler) | 仅作参考 | 文档包含关键词搜索、详情与评论接口；Cookie/接口稳定性和许可证需另行验证 |
| 可颂 | 未发现面向可颂内容检索、定位与发布时间的成熟开源采集器 | 未发现专用项目 | 优先核对与抖音同步的重合内容；独有内容可能需要 App 端人工抽样或依法获得的数据接口 |

## 采用方案

1. 抖音：`Douyin_keyword_crawler` 负责候选发现，`MediaCrawler` 负责单帖静态媒体和分层视频保存。
2. 高德：登录网页低频采样地点页评价；POI 坐标优先用官方 Web 服务 API 标准化（需要用户自己的 Key），评价媒体仍从网页逐条核验。
3. 快手：先复用 `Douyin_keyword_crawler` 的快手模式做小样本验收，通过后扩到 100 条。
4. 可颂：先按抖音帖子链接、标题和时间做同步内容去重；若 Web 端不可检索，不以逆向 App 或绕过风控作为默认方案。

## 使用约束

- `MediaCrawler` 使用“NON-COMMERCIAL LEARNING LICENSE 1.1”，限非商业学习/研究，不得大规模抓取或干扰平台。
- 仅采集完成研究目标所需的公开内容，不保留作者昵称、账号 ID 等非必要个人信息。
- 原始媒体不公开再分发；论文或报告优先展示聚合结果，个别样例需脱敏并处理版权授权。
- 遇到验证码、访问频繁或明确禁止访问时停止并人工处理，不绕过平台安全措施。
