# 统一数据字段

| 字段 | 类型 | 含义 |
|---|---|---|
| `record_id` | string | `platform + post_url` 的稳定哈希 |
| `platform` | enum | `amap/douyin/kesong/kuaishou/weibo/baidu` |
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

原始作者 ID 和昵称只允许保存在 `data/raw/`，不得复制到 `data/processed/`。

