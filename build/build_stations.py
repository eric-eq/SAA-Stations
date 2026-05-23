#!/usr/bin/env python3
"""Build per-station FDSN StationXML for SA-operator SAA/DU stations from a spreadsheet.

This is the South-Australia ingestion for the SAA-Stations fork. The SA operator sends a
spreadsheet of station updates; this turns each row into a `DU.<STA>.xml` at the REPO ROOT,
where `.github/workflows/combine-xml.yml` picks it up and rebuilds `all.xml`.

Input:  build/stations.xlsx (native Excel, preferred) or build/stations.csv
Output: <NET>.<STA>.xml at the repo root (one per row)

Run from an env with obspy + pandas + openpyxl (e.g. the `uom_seismic_metadata` conda env):
    python build/build_stations.py                 # auto-finds build/stations.xlsx|csv
    python build/build_stations.py path/to/file.xlsx

Responses are assembled from the small registry below (sensor poles/zeros ⊗ datalogger
flat-gain). The script FAILS LOUDLY on an unknown or not-yet-filled instrument rather than
emitting a placeholder response — see DU.HML1 for why dummy responses are harmful.

STATUS / still to fill in:
  * DATALOGGERS['piesmo']['counts_per_volt']  — SRC PiesMo sensitivity (counts/V).
  * SENSORS['cmg6t1'] poles/zeros/norm        — to be harvested from a known CMG-6T-1
                                                 (VW.MARD) or taken from the NRL.
  * Verify channel codes against live seedlink (slinktool -Q vip.kelunji.net) first.
"""
import os, sys
import pandas as pd
from obspy import UTCDateTime
from obspy.core.inventory import Inventory, Network, Station, Channel, Site
from obspy.core.inventory.response import (
    Response, InstrumentSensitivity, PolesZerosResponseStage, CoefficientsTypeResponseStage,
)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)   # fork root (where DU.<STA>.xml live)

# --- instrument registry -----------------------------------------------------
# Sensor: velocity -> volts (poles/zeros). Datalogger: volts -> counts (flat gain).
# Leave a value None to force a clear error instead of a dummy response.
SENSORS = {
    "cmg6t1": {                       # Guralp CMG-6T-1 (1 Hz corner), ground velocity
        "sensitivity_v_per_ms": 2400.0,
        "poles": None,                # TODO: harvest from VW.MARD (a CMG-6T-1) or NRL
        "zeros": None,
        "normalization_factor": None,
        "normalization_frequency": 1.0,
    },
}
DATALOGGERS = {
    "echopro": {"counts_per_volt": 838860.8},   # SRC EchoPro (cf. Gempa-smp.md)
    "piesmo":  {"counts_per_volt": None},        # TODO: SRC PiesMo sensitivity (counts/V)
}

DEFAULT_CHANNELS = ["HHZ", "HHN", "HHE"]
ORIENT = {"Z": (0.0, -90.0), "N": (0.0, 0.0), "E": (90.0, 0.0)}

def build_response(recorder, sensor, sample_rate):
    s = SENSORS.get(sensor.lower())
    d = DATALOGGERS.get(recorder.lower())
    if s is None:
        raise ValueError(f"unknown sensor '{sensor}' — add it to SENSORS")
    if d is None:
        raise ValueError(f"unknown recorder '{recorder}' — add it to DATALOGGERS")
    if any(s.get(k) is None for k in ("poles", "zeros", "normalization_factor")):
        raise NotImplementedError(f"sensor '{sensor}' poles/zeros not filled in (no dummy responses)")
    if d.get("counts_per_volt") is None:
        raise NotImplementedError(f"recorder '{recorder}' counts_per_volt not set (no dummy responses)")

    v_per_ms, cpv = s["sensitivity_v_per_ms"], d["counts_per_volt"]
    f0 = s["normalization_frequency"]
    sensor_stage = PolesZerosResponseStage(
        1, v_per_ms, f0, "M/S", "V", "LAPLACE (RADIANS/SECOND)", f0,
        s["zeros"], s["poles"], normalization_factor=s["normalization_factor"],
    )
    digi_stage = CoefficientsTypeResponseStage(
        2, cpv, f0, "V", "COUNTS", "DIGITAL", numerator=[], denominator=[],
        decimation_input_sample_rate=sample_rate, decimation_factor=1,
        decimation_offset=0, decimation_delay=0, decimation_correction=0,
    )
    return Response(
        instrument_sensitivity=InstrumentSensitivity(v_per_ms * cpv, f0, "M/S", "COUNTS"),
        response_stages=[sensor_stage, digi_stage],
    )

def _date(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return None
    return UTCDateTime(str(v))

def build_channels(row, rate):
    raw = str(row.get("channels") or "").strip()
    codes = [c.strip() for c in raw.split(",") if c.strip()] or DEFAULT_CHANNELS
    chans = []
    for code in codes:
        az, dip = ORIENT.get(code[-1].upper(), (0.0, 0.0))
        ch = Channel(
            code=code, location_code=str(row.get("location") or "00"),
            latitude=row["latitude"], longitude=row["longitude"],
            elevation=row["elevation"], depth=float(row.get("depth") or 0.0),
            azimuth=az, dip=dip, sample_rate=rate,
            start_date=_date(row.get("start_date")), end_date=_date(row.get("end_date")),
        )
        ch.response = build_response(str(row["recorder"]), str(row["sensor"]), rate)
        chans.append(ch)
    return chans

def main(path=None):
    if path is None:
        for cand in ("stations.xlsx", "stations.csv"):
            if os.path.exists(os.path.join(HERE, cand)):
                path = os.path.join(HERE, cand); break
    if not path or not os.path.exists(path):
        sys.exit("No spreadsheet found. Put it at build/stations.xlsx (or .csv).")

    df = pd.read_excel(path) if path.lower().endswith((".xlsx", ".xls")) else pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    required = {"station", "latitude", "longitude", "elevation", "recorder", "sensor"}
    missing = required - set(df.columns)
    if missing:
        sys.exit(f"spreadsheet missing required columns: {sorted(missing)}")

    n = 0
    for _, row in df.iterrows():
        net = str(row.get("network") or "DU").upper()
        sta_code = str(row["station"]).strip().upper()
        rate = float(row.get("sample_rate") or 100.0)
        sta = Station(code=sta_code, latitude=row["latitude"], longitude=row["longitude"],
                      elevation=row["elevation"], site=Site(name=str(row.get("site") or "")))
        sta.channels = build_channels(row, rate)
        starts = [c.start_date for c in sta.channels if c.start_date]
        sta.start_date = min(starts) if starts else None
        inv = Inventory(networks=[Network(code=net, stations=[sta])],
                        source="SAA-Stations/build/build_stations.py")
        out = os.path.join(REPO, f"{net}.{sta_code}.xml")
        inv.write(out, format="STATIONXML")
        print(f"wrote {net}.{sta_code}.xml  ({len(sta.channels)} channels @ {rate:.0f} Hz)")
        n += 1
    print(f"\ndone: {n} station file(s) at repo root. Commit + push → combine-xml rebuilds all.xml.")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
