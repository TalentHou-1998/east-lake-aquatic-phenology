# East Lake verification map

The static interface lives in `dist/` and uses Leaflet with a Baidu imagery base layer.

The GitHub version intentionally excludes:

- `dist/data/points.json` and `summary.json`;
- `dist/assets/media/`;
- `.openai/` deployment metadata;
- the local Site repository metadata.

Generate the excluded files from your own authorized local research data:

```bash
python3 src/export_map_site.py \
  --project-root . \
  --site-dist sites/east-lake-map/dist
```

Then preview from the project root:

```bash
python3 -m http.server 4173 --directory sites/east-lake-map/dist
```

