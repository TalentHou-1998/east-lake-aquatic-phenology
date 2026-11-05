# Dataset Card: Wuhan East Lake Aquatic Vegetation Social Media Dataset

## 1. Overview

- **dataset_name**: Wuhan East Lake Aquatic Vegetation Social Media Dataset
- **version**: 0.5-multiplatform-baidu-albums
- **domain**: aquatic vegetation phenology / volunteered geographic information
- **task**: multimodal phenology and location consistency annotation
- **data_type**: image, video, text, time and POI metadata
- **current size**: 756 records
- **format**: CSV plus restricted local media files
- **license**: source content retains original copyright; no redistribution license is asserted

## 2. Motivation

从公开社交媒体内容观察武汉东湖不同地点水生植被的季节性生长状态，并评估用户发布位置与目视地点判断的一致性。

## 3. Composition

每条实例代表一条公开帖子、高德地点评价或百度地图地点相册。百度地点相册以地点为实例，关联多张图片。字段定义见 `docs/schema.md`。物候、覆盖度和位置一致性标签定义见 `docs/annotation_guide.md`。

## 4. Collection Process

- 区域：武汉东湖及东湖生态旅游风景区。
- 内容发布时间范围：2018-01-01 至 2026-10-30。
- 平台：高德、抖音、快手、微博、百度地图地点相册；可颂暂未采集。
- 使用关键词检索和地点页采样；初始样本按平台控制规模，后续增量不设硬性条数上限。
- 检索排序、账号个性化和平台删除机制会带来选择偏差。

## 5. Preprocessing / Cleaning

- 按平台帖子 URL/帖子 ID 去重，媒体按 SHA-256 去重。
- 统一时间为 Asia/Shanghai。
- 原始坐标保留并显式记录坐标系；不在坐标系未知时计算距离。
- 处理数据中删除作者 ID、昵称等非研究必要信息。

## 6. Quality Assessment

当前共 756 条：高德 100、抖音 100、快手候选 6、微博候选 547、百度地点相册 3。百度地点相册关联 33 张图片但没有平台可见的单图发布时间。24 条已完成主图级视觉预标注并迁移到四阶段体系。详见 `quality_report.md`。

## 7. Known Issues & Risks

- 发布地点可能是推荐地点而非拍摄地点。
- 发布时间可能晚于真实拍摄时间。
- 百度地点相册没有可用发布时间，不能纳入时间物候推断。
- 搜索结果受平台排序与账号行为影响，不能代表东湖全部公众观察。
- 原始媒体可能包含人脸、车牌和其他个人信息。

## 7b. Access Level

- **access_level**: raw
- **redaction_actions**: 处理版删除作者身份字段；公开图表只使用聚合结果或经人工核验的脱敏样例。
- **gated_sinks**: 原始媒体、账号信息和原始评论不得进入公开仓库、论文附件或公共数据集。

## 8. Recommended Use & Splits

用于探索性物候研究和方法验证。若训练模型，应按地点和时间分组划分，避免同一帖子、同一作者或同一事件跨训练/测试集泄漏。

## 9. Maintenance

版本以 `0.1-pilot`、`0.2-douyin-collected`、`0.3-amap-douyin-collected`、`0.4-multiplatform`、`1.0-verified` 递进；原始数据不公开发布。

## 10. Provenance & Verification

- 上游采集器：TYP1227/Douyin_keyword_crawler、NanmiCoder/MediaCrawler。
- `last_checked_date`: 2026-11-06
- 平台字段标记为 observed；视觉地点和物候字段标记为 inferred，并保留置信度。

