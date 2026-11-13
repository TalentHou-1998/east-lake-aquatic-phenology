const state = {
  points: [], filtered: [], markers: new Map(), active: null, mediaIndex: 0,
  userJudgments: JSON.parse(localStorage.getItem('eastLakeJudgments') || '{}')
};

const labels = {
  stages: {
    growth_start: '植被开始生长', fully_grown: '植被生长完全',
    decline_start: '植被开始衰败', declined: '植被已经衰败', unknown: '尚未判断'
  },
  matches: { match: '一致', plausible: '大致一致', conflict: '冲突', unknown: '尚未判断' },
  confidence: { high: '高置信度', medium: '中置信度', low: '低置信度', unknown: '未知' },
  platforms: {
    amap: { short: '高德', detail: '高德评价' },
    douyin: { short: '抖音', detail: '抖音帖子' },
    kuaishou: { short: '快手', detail: '快手帖子' },
    weibo: { short: '微博', detail: '微博帖子' },
    baidu: { short: '百度', detail: '百度地点相册' },
    xhs: { short: '小红书', detail: '小红书帖子' }
  }
};

function annotation(point) {
  const saved = state.userJudgments[point.id] || {};
  return {
    stage: saved.stage || point.growthStage || 'unknown',
    match: saved.locationValue || saved.value || point.locationMatchClass || 'unknown',
    mediaValue: saved.mediaValue || point.mediaValue || 'unknown'
  };
}

function updateHiddenMetric() {
  const hidden = state.points.filter(point => annotation(point).mediaValue === 'meaningless').length;
  setText('hiddenMetric', hidden);
}

const map = L.map('map', {
  crs: L.ChineseCRS.CRS_BaiduMercator, center: [30.561, 114.410], zoom: 13,
  minZoom: 6, maxZoom: 18, zoomControl: false, attributionControl: true
});
L.control.zoom({ position: 'bottomright' }).addTo(map);

const imagery = new L.ChineseCRS.BaiduTileLayer(
  'https://maponline{s}.bdimg.com/starpic/?qt=satepc&u=x={x};y={y};z={z};v=009;type=sate&fm=46&app=webearth2',
  { subdomains: '0123', minZoom: 6, maxZoom: 18, attribution: '影像 © 百度地图' }
);
const annotations = new L.ChineseCRS.BaiduTileLayer(
  'https://maponline{s}.bdimg.com/tile/?qt=tile&x={x}&y={y}&z={z}&styles=sl&v=020',
  { subdomains: '0123', minZoom: 6, maxZoom: 18, opacity: .88, attribution: '标注 © 百度地图' }
);
imagery.addTo(map); annotations.addTo(map);

const markerLayer = L.markerClusterGroup({
  showCoverageOnHover: false, spiderfyOnMaxZoom: true, maxClusterRadius: 42,
  disableClusteringAtZoom: 17
}).addTo(map);

function markerIcon(point) {
  const precision = point.coordinatePrecision === 'platform_observed_unknown_crs' ? 'observed' : 'estimated';
  return L.divIcon({
    className: `media-pin ${point.platform} ${precision}`,
    html: '<span></span>', iconSize: [18, 18], iconAnchor: [9, 9]
  });
}

function initFilters(summary) {
  const platformFilters = document.getElementById('platformFilters');
  platformFilters.innerHTML = Object.entries(summary.platforms).map(([platform, count]) => {
    const name = labels.platforms[platform]?.short || platform;
    return `<label><input type="checkbox" name="platform" value="${platform}" checked><span>${name} <b>${count}</b></span></label>`;
  }).join('');
  const years = [...new Set(state.points.map(p => p.year).filter(Boolean))].sort();
  for (const id of ['yearStart', 'yearEnd']) {
    const select = document.getElementById(id);
    select.innerHTML = years.map(y => `<option value="${y}">${y}</option>`).join('');
  }
  document.getElementById('yearStart').value = years[0];
  document.getElementById('yearEnd').value = years.at(-1);
}

function filters() {
  return {
    platforms: new Set([...document.querySelectorAll('input[name=platform]:checked')].map(x => x.value)),
    start: Number(document.getElementById('yearStart').value),
    end: Number(document.getElementById('yearEnd').value),
    observedOnly: document.getElementById('observedOnly').checked,
    includeUnknownTime: document.getElementById('includeUnknownTime').checked,
    showMeaningless: document.getElementById('showMeaningless').checked,
    stage: document.getElementById('stageFilter').value,
    match: document.getElementById('matchFilter').value,
    query: document.getElementById('searchInput').value.trim().toLowerCase()
  };
}

function applyFilters() {
  const f = filters();
  state.filtered = state.points.filter(point => {
    const a = annotation(point);
    const haystack = `${point.broadPoi || ''} ${point.poiName} ${point.poiAddress} ${point.text} ${point.vegetationType} ${point.visualLocation}`.toLowerCase();
    const timeMatches = point.year === null ? f.includeUnknownTime : point.year >= f.start && point.year <= f.end;
    return f.platforms.has(point.platform) && timeMatches &&
      (!f.observedOnly || point.coordinatePrecision === 'platform_observed_unknown_crs') &&
      (f.showMeaningless || a.mediaValue !== 'meaningless') &&
      (f.stage === 'all' || a.stage === f.stage) &&
      (f.match === 'all' || a.match === f.match) &&
      (!f.query || haystack.includes(f.query));
  });
  markerLayer.clearLayers();
  state.filtered.forEach(point => markerLayer.addLayer(state.markers.get(point.id)));
  document.getElementById('visibleCount').textContent = `${state.filtered.length} / ${state.points.length}`;
  updateHiddenMetric();
  renderResultList();
}

function renderResultList() {
  const list = document.getElementById('resultList');
  const visible = state.filtered.slice(0, 50);
  list.innerHTML = visible.map(point => {
    const a = annotation(point);
    return `
    <button class="result-item" data-id="${point.id}" type="button">
      <strong>${escapeHtml(point.broadPoi || point.poiName)}</strong>
      <span>${labels.platforms[point.platform]?.short || point.platform} · ${escapeHtml(point.timeKnown ? point.publishTime.slice(0,10) : '时间未知')} · ${labels.stages[a.stage] || a.stage}</span>
    </button>`;
  }).join('') + (state.filtered.length > 50 ? `<div class="result-more">地图中另有 ${state.filtered.length - 50} 条</div>` : '');
  list.querySelectorAll('button[data-id]').forEach(button => button.addEventListener('click', () => {
    const point = state.points.find(p => p.id === button.dataset.id);
    map.setView([point.lat, point.lng], 16); openDetail(point);
  }));
}

function escapeHtml(value='') {
  return value.replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
}

function setText(id, value) { document.getElementById(id).textContent = value; }

function openDetail(point) {
  state.active = point; state.mediaIndex = 0;
  const panel = document.getElementById('detailPanel');
  panel.classList.add('open'); panel.setAttribute('aria-hidden', 'false');
  const platform = document.getElementById('detailPlatform');
  platform.className = `platform-badge ${point.platform}`;
  platform.textContent = labels.platforms[point.platform]?.detail || `${point.platform} 帖子`;
  const a = annotation(point);
  setText('detailDate', point.timeKnown ? point.publishTime.slice(0, 10) : '时间未知');
  setText('detailPrecision', point.coordinatePrecision === 'platform_observed_unknown_crs' ? '平台坐标' : '估计坐标');
  setText('detailTitle', point.broadPoi || point.poiName);
  setText('detailAddress', point.poiAddress);
  setText('platformLocation', point.poiName);
  setText('platformAddress', point.poiAddress);
  setText('visualLocation', point.visualLocation);
  setText('visualConfidence', labels.confidence[point.visualLocationConfidence] || point.visualLocationConfidence);
  setText('vegetationType', point.vegetationType);
  setText('growthStage', labels.stages[a.stage] || a.stage);
  setText('coverGrade', point.coverGrade);
  setText('preMatch', labels.matches[a.match] || a.match);
  setText('detailText', point.text);
  document.getElementById('sourceLink').href = point.postUrl;
  document.getElementById('baiduLink').href = `https://api.map.baidu.com/marker?location=${point.lat},${point.lng}&title=${encodeURIComponent(point.broadPoi || point.poiName)}&content=${encodeURIComponent(point.poiAddress)}&output=html&src=east-lake-media-map`;
  renderMedia(); loadJudgment();
}

function renderMedia() {
  const point = state.active;
  const image = document.getElementById('detailImage');
  image.src = point.media[state.mediaIndex];
  setText('mediaCounter', `${state.mediaIndex + 1} / ${point.media.length}`);
  document.getElementById('mediaPrev').hidden = point.media.length < 2;
  document.getElementById('mediaNext').hidden = point.media.length < 2;
  const strip = document.getElementById('thumbnailStrip');
  strip.innerHTML = point.media.map((src, index) => `<button type="button" data-index="${index}" class="${index === state.mediaIndex ? 'active' : ''}"><img src="${src}" alt="第 ${index+1} 张"></button>`).join('');
  strip.querySelectorAll('button').forEach(button => button.addEventListener('click', () => { state.mediaIndex = Number(button.dataset.index); renderMedia(); }));
}

function changeMedia(delta) {
  const count = state.active.media.length;
  state.mediaIndex = (state.mediaIndex + delta + count) % count; renderMedia();
}

function loadJudgment() {
  const judgment = state.userJudgments[state.active.id] || { value: '', note: '' };
  const a = annotation(state.active);
  const locationValue = judgment.locationValue || judgment.value || a.match;
  document.querySelectorAll('#reviewOptions button').forEach(button => button.classList.toggle('active', button.dataset.value === locationValue));
  document.querySelectorAll('#valueOptions button').forEach(button => button.classList.toggle('active', button.dataset.value === a.mediaValue));
  document.getElementById('reviewStage').value = a.stage;
  document.getElementById('reviewNote').value = judgment.note || '';
  document.getElementById('saveHint').textContent = judgment.savedAt ? `已保存：${new Date(judgment.savedAt).toLocaleString()}` : '判断仅保存在此浏览器，可随时导出 CSV。';
}

function saveJudgment() {
  const activeButton = document.querySelector('#reviewOptions button.active');
  const valueButton = document.querySelector('#valueOptions button.active');
  state.userJudgments[state.active.id] = {
    locationValue: activeButton?.dataset.value || 'unknown',
    stage: document.getElementById('reviewStage').value,
    mediaValue: valueButton?.dataset.value || 'unknown',
    note: document.getElementById('reviewNote').value.trim(),
    savedAt: new Date().toISOString(), platform: state.active.platform,
    poiName: state.active.broadPoi || state.active.poiName, publishTime: state.active.publishTime
  };
  localStorage.setItem('eastLakeJudgments', JSON.stringify(state.userJudgments));
  loadJudgment();
  if (state.userJudgments[state.active.id].mediaValue === 'meaningless' && !document.getElementById('showMeaningless').checked) {
    document.getElementById('detailPanel').classList.remove('open');
  }
  applyFilters();
}

function exportJudgments() {
  const rows = Object.entries(state.userJudgments).map(([id, j]) => [id, j.platform, j.poiName, j.publishTime, j.locationValue || j.value || 'unknown', j.stage || 'unknown', j.mediaValue || 'unknown', j.note, j.savedAt]);
  if (!rows.length) { alert('尚未保存人工判断。'); return; }
  const csv = [['record_id','platform','poi_name','publish_time','location_judgment','growth_stage','media_value','note','saved_at'], ...rows]
    .map(row => row.map(cell => `"${String(cell ?? '').replaceAll('"','""')}"`).join(',')).join('\n');
  const blob = new Blob(['\ufeff' + csv], {type:'text/csv;charset=utf-8'});
  const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'east_lake_location_judgments.csv'; link.click(); URL.revokeObjectURL(link.href);
}

async function boot() {
  try {
    const [points, summary] = await Promise.all([fetch('data/points.json').then(r => r.json()), fetch('data/summary.json').then(r => r.json())]);
    state.points = points; state.filtered = points;
    setText('totalMetric', summary.total); setText('observedMetric', summary.platformObservedCoordinates); setText('screenedMetric', summary.preannotated); updateHiddenMetric();
    initFilters(summary);
    points.forEach(point => {
      const marker = L.marker([point.lat, point.lng], { icon: markerIcon(point), title: `${point.broadPoi || point.poiName} · ${point.publishTime.slice(0,10)}` });
      marker.on('click', () => openDetail(point)); state.markers.set(point.id, marker);
    });
    applyFilters();
    document.getElementById('loadingPanel').remove();
  } catch (error) {
    document.getElementById('loadingPanel').innerHTML = `<strong>地图数据载入失败</strong><span>${escapeHtml(error.message)}</span>`;
  }
}

document.querySelectorAll('#yearStart, #yearEnd, #observedOnly, #includeUnknownTime, #showMeaningless, #stageFilter, #matchFilter').forEach(el => el.addEventListener('change', applyFilters));
document.getElementById('platformFilters').addEventListener('change', applyFilters);
document.getElementById('searchInput').addEventListener('input', applyFilters);
document.getElementById('resetFilters').addEventListener('click', () => {
  document.querySelectorAll('input[name=platform]').forEach(x => x.checked = true);
  document.getElementById('yearStart').selectedIndex = 0;
  document.getElementById('yearEnd').selectedIndex = document.getElementById('yearEnd').options.length - 1;
  document.getElementById('observedOnly').checked = false;
  document.getElementById('includeUnknownTime').checked = true;
  document.getElementById('showMeaningless').checked = false;
  document.getElementById('stageFilter').value = 'all'; document.getElementById('matchFilter').value = 'all'; document.getElementById('searchInput').value = '';
  applyFilters();
});
document.getElementById('closeDetail').addEventListener('click', () => document.getElementById('detailPanel').classList.remove('open'));
document.getElementById('mediaPrev').addEventListener('click', () => changeMedia(-1));
document.getElementById('mediaNext').addEventListener('click', () => changeMedia(1));
document.getElementById('detailImage').addEventListener('click', () => { document.getElementById('lightboxImage').src = state.active.media[state.mediaIndex]; document.getElementById('lightbox').classList.add('open'); });
document.getElementById('closeLightbox').addEventListener('click', () => document.getElementById('lightbox').classList.remove('open'));
document.querySelectorAll('#reviewOptions button').forEach(button => button.addEventListener('click', () => { document.querySelectorAll('#reviewOptions button').forEach(x => x.classList.remove('active')); button.classList.add('active'); }));
document.querySelectorAll('#valueOptions button').forEach(button => button.addEventListener('click', () => { document.querySelectorAll('#valueOptions button').forEach(x => x.classList.remove('active')); button.classList.add('active'); }));
document.getElementById('saveReview').addEventListener('click', saveJudgment);
document.getElementById('exportButton').addEventListener('click', exportJudgments);

boot();
