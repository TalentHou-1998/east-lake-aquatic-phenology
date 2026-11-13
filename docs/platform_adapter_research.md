# 多平台媒体采集适配调研

更新日期：2026-11-13。

## 结论

平台接入分为三层：成熟开源适配器、现有地图相册处理器、登录浏览器辅助采集。系统不实现验证码绕过、签名破解、代理池轮换或批量账号控制；遇到验证时停止并交由用户在正常浏览器中完成。

| 平台 | 推荐接入方式 | 结论 |
|---|---|---|
| 小红书、抖音、快手、微博、哔哩哔哩 | MediaCrawler | 当前版本可检索并下载帖子图片、视频或封面，作为主采集器 |
| 百度地图 | 项目内 `process_baidu_albums.py` | 从地点相册导出记录和媒体，保留 POI 证据 |
| 高德地图 | 项目内 `build_amap_dataset.py` | 从地点评价导出记录和媒体，保留 POI 证据 |
| 大众点评 | 登录浏览器 + 通用清单导入 | `Sniper970119/dianping_spider` 较活跃，但依赖 Cookie 池、代理与字体解密，且重点是商家/评论数据；本项目只将它作为解析参考，不直接集成高风险采集路径 |
| 美团 | 登录浏览器 + 通用清单导入 | 找到的开源项目多为商家、商品或外卖评论采集，维护时间和媒体能力不足，不适合作为主依赖 |
| 两步路 | 登录浏览器 + 通用清单导入 | 未找到可靠的专用媒体爬虫；优先使用平台“附近图片/附近轨迹”页面进行低频、人工可见范围内采集 |
| 可颂 | 登录浏览器 + 通用清单导入 | 暂无可靠专用适配器，使用同一清单接口接入 |

## 候选开源项目

- MediaCrawler：<https://github.com/NanmiCoder/MediaCrawler>
- 大众点评参考实现：<https://github.com/Sniper970119/dianping_spider>
- 美团 POI/商家参考实现：<https://github.com/guocaoyi/meituan-spider>
- 美团评论参考实现：<https://github.com/pot-not-fish/meituan_spider>
- Playwright：<https://github.com/microsoft/playwright>
- Crawlee：<https://github.com/apify/crawlee>
- SingleFile：<https://github.com/gildas-lormeau/SingleFile>
- Browsertrix Crawler：<https://github.com/webrecorder/browsertrix-crawler>

候选项目是否“可用”不能仅按 GitHub 星标判断。正式接入前还要核对许可证、最近提交、媒体字段、登录方式、导出格式和是否要求规避平台安全机制。

## 无定位内容的召回与判定

平台定位不再是入库前提。候选素材可由以下任一来源召回：

1. 正文、标题、话题或文件说明提及东湖或一级地标；
2. 图片中的招牌、路牌、景区名、桥名等 OCR 文本命中地名词典；
3. 视频抽帧 OCR 命中地名或活动语义；
4. 人工目视识别出岸线、桥梁、建筑、栈道等画面地标；
5. 平台 POI、地址或坐标直接落在研究区。

检索词只负责“召回”，不能单独证明拍摄地点。系统分别保存平台定位、正文、OCR、画面和检索词证据；只有前四类或可靠平台定位才能把记录提升为已定位候选。

## 接入流程

```text
平台搜索/附近图片
  → 原始页面或导出清单
  → 通用媒体清单导入器
  → 正文 + OCR + 画面地标证据表
  → 一级地标候选与置信度
  → 人工核验
  → 年份/一级地标媒体归档与地图
```
