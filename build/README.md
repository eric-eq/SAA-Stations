# build/ — South Australia SAA station ingestion

SAA is a disparate network (Sydney, Canberra, South Australia) and UoM archives all of it,
so this fork is UoM's aggregation point. The **Sydney** stations come from the upstream
`eric-eq/SAA-Stations` (via `git merge`); the **South Australia** stations come from a
spreadsheet the SA operator sends, ingested here.

## Where to put the spreadsheet
- **`build/stations.xlsx`** (native Excel — preferred), or `build/stations.csv`

## Columns (case-insensitive — see `stations.template.csv`)
**Required:** `station, latitude, longitude, elevation, recorder, sensor`
**Optional:** `network` (default `DU`), `location` (default `00`), `sample_rate`
(default `100`), `channels` (e.g. `HHZ,HHN,HHE`; default `HH*`), `depth` (default `0`),
`site`, `start_date`, `end_date`

- `recorder` ∈ {`echopro`, `piesmo`}  ·  `sensor` ∈ {`cmg6t1`}  (extend the registry in
  `build_stations.py` for new types).

## Run
Needs `obspy` + `pandas` + `openpyxl` — e.g. the `uom_seismic_metadata` conda env:

```bash
python build/build_stations.py          # reads build/stations.xlsx|csv
```

It writes `DU.<STA>.xml` at the **repo root**. Commit those + push; the **Combine XML
Files** Action rebuilds `all.xml`, and downstream `uom_seismic_metadata` picks it up via
`git submodule update --remote external/du`.

## Provenance / not clobbering the Sydney set
This pipeline only writes the stations listed in the spreadsheet (the SA set). A `git merge`
from upstream only touches the Sydney files. Station codes are disjoint by region, so the
two feeds don't collide — keep it that way.

## Still to fill in (the script FAILS LOUDLY rather than emitting dummy responses)
- **PiesMo** datalogger sensitivity (counts/V) → `DATALOGGERS['piesmo']`.
- **CMG-6T-1** sensor poles/zeros → `SENSORS['cmg6t1']` (harvest from a known CMG-6T-1,
  e.g. `VW.MARD`, or take from the NRL).
- **Verify channel codes** against live seedlink (`slinktool -Q vip.kelunji.net`) before relying on them.
