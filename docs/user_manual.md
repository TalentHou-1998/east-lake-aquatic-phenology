# 武汉东湖水生植被媒体核验系统——用户说明手册

版本：0.5.0  
适用范围：本地数据处理、百度遥感影像地图核验、人工标注与结果导出。

## 1. 系统用途

本系统把高德、抖音、快手、微博和百度地图地点相册等公开来源整理成统一记录，并将记录放到百度遥感影像底图上。研究人员可以查看媒体、平台位置和发布时间，判断：

1. 画面是否包含可用于研究的水生植被；
2. 植被处于哪个生长阶段；
3. 平台挂载地点是否与画面中的实际位置一致；
4. 发布时间能否作为近似物候时间证据。

平台位置是用户挂载的 POI，不等于拍摄机位；发布时间也不一定等于拍摄时间。本系统用于证据核验，不把单条记录自动视为真实观测。

## 2. 功能概览

- 多平台统一字段与去重。
- 图片、视频封面和地点相册关联。
- 百度遥感影像与道路标注叠加。
- 按平台、年份、位置精度、植被阶段和位置一致性筛选。
- 四阶段植被标注。
- “无意义”点位隐藏与恢复。
- 浏览器本地保存人工判断并导出 CSV。
- 发布前敏感信息和受限目录检查。

## 3. 植被阶段定义

| 界面名称 | 字段值 | 判断依据 |
|---|---|---|
| 植被开始生长 | `growth_start` | 新芽、新生小叶、稀疏新生植株或刚出水植株 |
| 植被生长完全 | `fully_grown` | 叶片充分展开、群落覆盖稳定；花蕾、开花和健康结实时也归入此类 |
| 植被开始衰败 | `decline_start` | 出现黄化、枯边、倒伏或叶片减少，但仍有明显活体植被 |
| 植被已经衰败 | `declined` | 大部分植株枯黄、倒伏或腐烂，只剩枯茎残体或几乎没有当年活体叶片 |
| 尚未判断 | `unknown` | 画面不清楚、目标太远或缺少足够证据 |

完整标注规则见 `docs/annotation_guide.md`。

## 4. 软件与硬件要求

### 4.1 必需组件

- macOS、Linux 或 Windows；采集脚本当前主要在 macOS + zsh 上验证。
- Python 3.11 或更高版本。
- 现代浏览器：Microsoft Edge、Chrome 或 Chromium。
- 本地静态服务器，例如 Python 自带的 `http.server`。

### 4.2 可选组件

- ImageMagick 7：地图导出时将图片压缩为 WebP；命令名必须为 `magick`。
- `uv`：运行第三方采集器。
- Git 与 GitHub CLI：版本管理和发布。

### 4.3 推荐资源

- 磁盘：原始媒体会快速增长，建议至少预留 10 GB。
- 内存：4 GB 可运行静态地图；大量图片压缩建议 8 GB 以上。

## 5. 安装

```bash
git clone https://github.com/<YOUR_GITHUB_USERNAME>/east-lake-aquatic-phenology.git
cd east-lake-aquatic-phenology
python3 --version
```

安装可选工具：

```bash
# macOS
brew install imagemagick uv

# Ubuntu/Debian（包名可能随发行版变化）
sudo apt-get install imagemagick
```

源码处理脚本以 Python 标准库为主，无需安装账号密码相关依赖。

## 6. 凭据与占位符

仓库不包含真实 API Key、Token、Cookie、浏览器登录状态或个人路径。需要官方地图 API 时：

```bash
cp .env.example .env
```

在本机 `.env` 中替换：

- `<YOUR_AMAP_API_KEY>`：可选高德 Web 服务 Key；
- `<YOUR_BAIDU_MAP_AK>`：可选百度地图 AK；
- `<YOUR_GITHUB_TOKEN>`：可选 GitHub Token，推荐改用 `gh auth login`；
- `<YOUR_HTTPS_PROXY_URL>`：可选代理地址。

当前静态地图和已有处理脚本不需要地图 API Key。不要把 `.env`、Cookie 或浏览器 profile 复制进仓库。

## 7. 本地目录

```text
config/                      检索关键词
data/raw/                    原始导出，仅本地保存
data/interim/                中间状态与断点
data/processed/              统一后的 CSV
data/annotations/            人工预标注
media/                       原始图片、视频和关键帧
media_collected/             原始可追溯媒体归档
media_by_landmark_year/      按一级地标/年份整理的当前检查归档
src/                         清洗、迁移、导出和检查脚本
scripts/                     采集运行脚本
sites/east-lake-map/dist/    静态核验地图
docs/                        用户、字段、标注和设计文档
```

`data/`、`media/` 和浏览器登录目录默认不进入 Git。

## 8. 数据采集工作流

### 8.1 采集原则

- 只处理公开可见内容。
- 遵守平台条款、robots 策略和访问频率限制。
- 使用低并发和人工登录，不绕过验证码或访问控制。
- 不收集研究无关的账号 ID、手机号、邮箱等身份信息。
- 原始媒体只用于内部研究，不公开再分发。

### 8.2 地点化媒体采集计划

先生成空间单元和关键词计划：

```bash
python3 src/build_media_collection_plan.py
```

查看一个任务但不执行：

```bash
python3 scripts/run_place_media_collection.py \
  --unit-id BP05 --platform dy --keyword-count 1 --max-notes 10
```

添加 `--execute` 后才会连接登录浏览器并采集。MediaCrawler 路线支持 `xhs/dy/ks/wb/bili`；百度、高德、大众点评、美团、两步路和可颂使用各自导出或通用清单导入。完整平台路由见 `config/platform_sources.json`。

### 8.3 抖音登录

在项目根目录启动专用 Edge profile：

```bash
zsh scripts/launch_edge_cdp.sh
```

在打开的浏览器窗口中扫码登录。登录状态保存在 `data/edge-profile/`，该目录包含敏感会话数据，严禁上传。

运行小样本检索：

```bash
zsh scripts/run_douyin_pilot.sh
```

补充检索：

```bash
zsh scripts/run_douyin_supplement.sh
```

下载已入选帖子的封面或媒体：

```bash
zsh scripts/run_douyin_covers_all.sh
zsh scripts/run_douyin_media_all.sh
```

这些脚本要求第三方采集器放在 `vendor/`。第三方代码不随本仓库重新分发，应按其原仓库许可证单独安装。

### 8.4 高德和百度地点相册

浏览器采集结果应先保存为平台原始 JSON，再运行对应处理器。示例：

```bash
python3 src/build_amap_dataset.py \
  --input data/raw/amap/<AMAP_EXPORT>.json \
  --output data/processed/amap_posts.csv \
  --media-root media/amap \
  --project-root .

python3 src/process_weibo_search.py \
  data/raw/weibo/<WEIBO_EXPORT>.json \
  --project-root . \
  --start 2018-01-01 \
  --end 2026-10-30

python3 src/process_baidu_albums.py \
  data/raw/baidu/<BAIDU_ALBUM_EXPORT>.json \
  --project-root .
```

尖括号内容是本机文件名占位符，不应原样执行。

百度相册页面没有显示单张照片时间时，处理器必须保持 `publish_time` 为空，不能根据 URL、下载时间或文件元数据猜测。

### 8.5 归档既有媒体

无专用适配器的平台先按 `config/platform_manifest.example.json` 生成 JSON 清单，然后导入：

```bash
python3 src/ingest_search_manifest.py \
  data/raw/<平台>/<导出清单>.json \
  --project-root . \
  --download-media
```

清单可以不带平台定位，但必须保留公开内容入口、发布时间（若平台可见）和媒体 URL 或本地媒体路径。导入后提取综合位置证据：

```bash
python3 src/build_location_evidence.py \
  --project-root . \
  --ocr vision \
  --ocr-unresolved-only
```

该步骤使用正文、图片文字和视频抽帧文字定位候选。自动结果只用于排序和地图提示，仍需人工核验。

```bash
python3 src/archive_existing_media.py --project-root .
python3 src/rebuild_poi_media_archive.py --project-root .
python3 src/import_poi_archive_to_posts.py --project-root .
```

媒体先归入听涛、磨山、落雁、白马、武汉植物园等一级地标，再进入 `2018`—`2026` 或 `年份未知` 子目录。文件名为“一级地标-发布时间-发布平台-三位序号”。地图列表使用一级地标聚合，但详情中的“平台定位”继续显示原始平台 POI。完整层级见 `docs/poi_hierarchy_design.md`。新目录采用硬链接，原文件不移动。

新采集结果进入正式目录前还会检查研究时段、当前空间单元具体 POI 和水生植被语义。误分批次使用 `src/quarantine_archive_batch.py` 移入可恢复隔离区，不直接删除原始证据。

## 9. 数据整理与标注迁移

统一字段见 `docs/schema.md`。重新整理平台数据后，可运行：

```bash
python3 src/migrate_annotation_schema.py --project-root .
```

该脚本会：

- 为平台表补充 `media_value`；
- 将旧阶段迁移到四阶段体系；
- 把旧标签写入备注；
- 重建 `data/processed/all_posts.csv`。

主图预标注可以通过：

```bash
python3 src/apply_visual_screen.py \
  --annotations data/annotations/<ANNOTATION_FILE>.csv \
  --data-dir data/processed
```

## 10. 生成地图

确认 `magick` 可用：

```bash
magick -version
```

导出地图数据和压缩媒体：

```bash
python3 src/export_map_site.py \
  --project-root . \
  --site-dist sites/east-lake-map/dist
```

启动本地服务器：

```bash
python3 -m http.server 4173 --directory sites/east-lake-map/dist
```

浏览器打开 `http://127.0.0.1:4173`。不要直接双击 `index.html`，浏览器的本地文件安全策略可能阻止 JSON 加载。

## 11. 地图界面操作

### 11.1 筛选

- 平台：点击高德、百度、抖音、快手或微博标签切换显示。
- 发布时间：选择起止年份；“包含平台未提供时间的相册”控制百度相册。
- 位置精度：“仅显示平台原始坐标”排除 POI 估计坐标和区域中心点。
- 视觉判断：按阶段或一致性筛选。
- 搜索框：检索地点、文案和关键词。

### 11.2 查看媒体

点击地图点位或左侧结果，详情面板将显示：

- 平台及时间；
- 平台 POI 与地址；
- 关联图片；
- 已有视觉预标注；
- 原始平台链接和百度地图核对链接。

图集使用左右按钮或缩略图切换。

### 11.3 人工判断

1. 先浏览全部相关图片或视频证据；
2. 判断位置一致、基本一致、冲突或无法判断；
3. 选择植被阶段；
4. 选择媒体价值；
5. 在备注中记录桥梁、建筑、岸线或冲突证据；
6. 点击“保存本地判断”。

“无意义并隐藏”会让该点位默认从地图和列表中消失，但记录没有被删除。勾选“显示已标为无意义的点位”即可恢复查看，并可改回“有意义”或“待判断”。

## 12. 判断保存和备份

判断保存在当前浏览器的 `localStorage`：

- 更换浏览器、清除网站数据或使用隐私模式会导致本地判断不可见；
- 每次较大批量标注后，应点击“导出人工判断”下载 CSV；
- 导出的 CSV 是备份和后续合并依据，不包含原始媒体二进制文件。

## 13. 位置与时间解释

- 平台坐标可能为 GCJ-02，网页底图渲染时会转换；坐标系未确认的记录须保留不确定性。
- POI 估算点仅表示关联地点，不代表相机位置。
- 发布地址与目视地址一致，只说明空间证据相容，不证明拍摄者当时位于该点。
- “库存、回忆、去年、补发、转载”等文案出现时，发布时间不能直接作为拍摄时间。
- 百度地点相册时间未知，不得用于物候日期判断。

## 14. 发布前安全检查

先生成一个只包含源码和文档的发布目录，再运行：

```bash
python3 src/check_public_release.py --root .
```

检查器会拒绝：

- 原始、处理后或标注数据；
- 浏览器登录 profile；
- 媒体文件；
- 站点私有部署元数据；
- 常见 API Key、GitHub Token、JWT、Bearer Token、私钥、个人绝对路径和邮箱。

检查器只是一道额外防线，不能替代人工审查和 Git 历史检查。

## 15. 常见问题

### 地图没有点位

确认 `sites/east-lake-map/dist/data/points.json` 已生成，并通过 HTTP 服务器访问页面。

### 图片显示为占位图

确认 `media_local_path` 指向存在的本地文件，再重新运行地图导出。

### ImageMagick 报错

确认安装的是 ImageMagick 7，并能运行 `magick -version`。旧版可能只有 `convert` 命令。

### 百度底图空白

检查网络、浏览器混合内容策略和底图服务是否可访问。遥感瓦片属于第三方服务，可能调整接口或限制访问。

### 保存后点位消失

若选择了“无意义并隐藏”，这是预期行为。打开“显示已标为无意义的点位”即可恢复。

### 登录状态失效

重新运行浏览器启动脚本并扫码登录。不要把登录 profile 发给他人。

## 16. 备份与恢复建议

- 源码：Git/GitHub。
- 原始数据和媒体：加密移动硬盘或受控对象存储，不放 GitHub。
- 人工判断：每次工作结束导出 CSV，并按日期命名。
- 处理结果：可从原始数据和脚本重建；保留运行日期和脚本版本。

## 17. 使用边界

本项目不提供绕过登录、验证码、付费墙或访问控制的方法。使用者应自行确认平台条款、地图服务许可、研究机构伦理要求和适用法律。第三方照片、视频和文案的版权仍归原权利人所有。

