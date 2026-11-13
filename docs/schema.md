# 统一数据字段

| 字段 | 类型 | 含义 |
|---|---|---|
| `record_id` | string | `platform + post_url` 的稳定哈希 |
| `platform` | enum | `xhs/weibo/douyin/kuaishou/bilibili/baidu/amap/dianping/meituan/2bulu/kesong` |
| `query_keyword` | string | 命中内容的检索词 |
| `post_url` | string | 公开内容入口 |
| `content_text` | string | 标题、正文或描述 |
| `publish_time` | datetime/blank | 平台显示的发布时间，Asia/Shanghai；平台未提供时必须留空 |
| `crawl_time` | datetime | 本地采集时间，Asia/Shanghai |
| `media_type` | enum | `image/video/mixed/unknown` |
| `media_local_path` | string | 内部研究媒体文件路径 |
| `media_sha256` | string | 媒体去重与完整性校验值 |
| `platform_poi_name` | string | 用户挂载或平台返回的 POI 名称 |
| `platform_poi_address` | string | 平台返回地址 |
| `platform_lng` / `platform_lat` | float | 平台原始坐标 |
| `coordinate_system` | enum | `GCJ-02/WGS84/BD-09/unknown` |
| `visual_location` | string | 通过画面判断的地点 |
| `visual_location_confidence` | enum | `high/medium/low/unknown` |
| `location_match_class` | enum | `match/plausible/conflict/unknown` |
| `vegetation_type` | string | 可多选的植物或群落类型 |
| `growth_stage` | enum | `growth_start/fully_grown/decline_start/declined/unknown` |
| `cover_grade` | enum | `0/<10%/10-30%/30-60%/>60%/unknown` |
| `phenology_confidence` | enum | `high/medium/low/unknown` |
| `media_value` | enum | `meaningful/meaningless/unknown`；无意义只从展示中过滤，不物理删除原始记录 |
| `review_status` | enum | `pending/accepted/rejected/needs_review` |
| `notes` | string | 拍摄时间疑点、转发、遮挡等说明 |
| `media_paths` | string | 同一帖子多媒体的相对路径，以 `|` 分隔 |

位置综合证据单独保存在 `data/processed/location_evidence.csv`，避免把平台事实与推断混在同一字段中：

| 字段 | 含义 |
|---|---|
| `platform_location_text` | 平台直接提供的 POI 与地址 |
| `content_evidence_text` | 标题、正文、话题和描述 |
| `ocr_text` | 图片或视频抽帧中的嵌入文字 |
| `visual_evidence_text` | 人工目视记录的桥梁、岸线、建筑等地标 |
| `matched_broad_poi` | 综合证据指向的一级地标 |
| `matched_aliases` | 实际命中的地名或地标别名 |
| `location_evidence_sources` | 参与判断的证据来源，不包含检索词 |
| `location_evidence_score` | 证据汇总分，只用于排序和复核 |
| `location_decision` | `located_candidate/regional_candidate/needs_review` |
| `location_decision_reason` | 可读的判定理由 |

检索词只记录“为什么召回这条内容”，不能单独写入 `matched_broad_poi` 或作为地点证明。

原始作者 ID 和昵称只允许保存在 `data/raw/`，不得复制到 `data/processed/`。

