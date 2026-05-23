#!/usr/bin/env python3
"""Build per-station FDSN StationXML for SAA/DU stations from the operator spreadsheet.

Default response is a **pass-through (overall sensitivity = 1.0, no stages)** — the same
structure as VW.TEMP — which lets a station be imported into SeisComP and start
serving/archiving immediately. The spreadsheet carries the real parameters (natural
frequency, damping, sensor `Volts per unit`, datalogger `counts per volt`), so proper
responses are a later refinement; broadband sensors (e.g. Nanometrics Trillium) should
instead get their real response from the NRL.

Reads these spreadsheet columns (case-insensitive; spaces ok):
  network code, station code, location code, channel code, latitude, longitude,
  elevation, depth, site name, sample rate, date deployed, date end, units
`channel code` may be a comma/space list (e.g. "EHE,EHN,EHZ"); a station may span
multiple rows (different location codes / instruments). Output: <NET>.<STA>.xml at root.

Usage:
  python build/build_stations.py "build/<sheet>.xlsx" --stations DNL MRAT CLV2 HMV1
  python build/build_stations.py <sheet>            # build every station in the sheet
"""
import os, sys, glob, argparse
import pandas as pd
from obspy import UTCDateTime
from obspy.core.inventory import Inventory, Network, Station, Channel, Site
from obspy.core.inventory.response import Response, InstrumentSensitivity

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ORIENT = {"Z": (0.0, -90.0), "N": (0.0, 0.0), "E": (90.0, 0.0)}

def sens_response(input_units, overall):
    """Sensitivity-only response: overall sensitivity, no PAZ stages. overall=None falls
    back to a gain-1 placeholder (cf. VW.TEMP). overall = sensor V/unit x datalogger counts/V."""
    return Response(instrument_sensitivity=InstrumentSensitivity(
        1.0 if overall is None else overall, 1.0, input_units, "COUNTS"))

def _val(row, *names, default=None):
    for n in names:
        if n in row and pd.notna(row[n]):
            return row[n]
    return default

def _date(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "NaT"):
        return None
    return UTCDateTime(str(v))

def _units(row):
    u = str(_val(row, "units", default="") or "").lower()
    return "M/S**2" if "m/s/s" in u or "m/s2" in u else "M/S"

def find_spreadsheet(path):
    if path:
        return path
    cands = [f for f in glob.glob(os.path.join(HERE, "*.xlsx")) + glob.glob(os.path.join(HERE, "*.csv"))
             if "template" not in os.path.basename(f).lower() and not os.path.basename(f).startswith("~$")]
    cands.sort(key=os.path.getmtime, reverse=True)
    return cands[0] if cands else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spreadsheet", nargs="?")
    ap.add_argument("--stations", nargs="*", help="only these station codes (default: all)")
    args = ap.parse_args()

    path = find_spreadsheet(args.spreadsheet)
    if not path or not os.path.exists(path):
        sys.exit("No spreadsheet found (build/*.xlsx|csv).")
    print(f"reading {os.path.basename(path)}")
    df = pd.read_excel(path) if path.lower().endswith((".xlsx", ".xls")) else pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]

    targets = {s.upper() for s in args.stations} if args.stations else None
    by_sta = {}
    for _, row in df.iterrows():
        code = str(_val(row, "station code", "station", default="") or "").strip().upper()
        if not code or (targets and code not in targets):
            continue
        by_sta.setdefault(code, []).append(row)

    if targets:
        for miss in sorted(targets - set(by_sta)):
            print(f"  WARNING: {miss} not found in spreadsheet — skipped")

    written = 0
    for code, rows in by_sta.items():
        r0 = rows[0]
        net = str(_val(r0, "network code", "network", default="DU")).upper()
        sta = Station(code=code, latitude=float(r0["latitude"]), longitude=float(r0["longitude"]),
                      elevation=float(r0["elevation"]),
                      site=Site(name=str(_val(r0, "site name", "site", default="") or "")))
        for row in rows:
            loc = str(_val(row, "location code", "location", default="00"))
            loc = "00" if loc.lower() in ("nan", "") else loc
            rate = float(_val(row, "sample rate", "sample_rate", default=100.0))
            depth = float(_val(row, "depth", default=0.0) or 0.0)
            iu = _units(row)
            vpu = _val(row, "volts per unit"); cpv = _val(row, "counts per volt")
            overall = float(vpu) * float(cpv) if vpu is not None and cpv is not None else None
            raw = str(_val(row, "channel code", "channels", default="") or "")
            for ch_code in [c.strip() for c in raw.replace(";", ",").split(",") if c.strip()]:
                az, dip = ORIENT.get(ch_code[-1].upper(), (0.0, 0.0))
                ch = Channel(code=ch_code, location_code=loc,
                             latitude=sta.latitude, longitude=sta.longitude,
                             elevation=sta.elevation, depth=depth, azimuth=az, dip=dip,
                             sample_rate=rate,
                             start_date=_date(_val(row, "date deployed", "start_date")),
                             end_date=_date(_val(row, "date end", "end_date")))
                ch.response = sens_response(iu, overall)
                sta.channels.append(ch)
        starts = [c.start_date for c in sta.channels if c.start_date]
        sta.start_date = min(starts) if starts else None
        if not sta.channels:
            print(f"  WARNING: {code} has no channel codes in the sheet — skipped")
            continue
        inv = Inventory(networks=[Network(code=net, stations=[sta])],
                        source="SAA-Stations/build/build_stations.py")
        out = os.path.join(REPO, f"{net}.{code}.xml")
        inv.write(out, format="STATIONXML")
        sv = sta.channels[0].response.instrument_sensitivity.value
        tag = " [PLACEHOLDER gain=1]" if sv == 1.0 else ""
        print(f"wrote {net}.{code}.xml — {len(sta.channels)} ch, overall sens={sv:g}{tag}")
        written += 1
    print(f"\n{written} station file(s) at repo root. Commit + push → combine-xml rebuilds all.xml.")

if __name__ == "__main__":
    main()
