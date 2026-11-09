"""Cross-check FPL historical fixture values against an independent public archive.

Source: vaastav/Fantasy-Premier-League, data/2026-27/gws/gwN.csv.
These are match-week snapshots, NOT proven pre-deadline prices.
This script intentionally does not overwrite the simulation's input prices.
"""
import csv
import io
import json
from collections import defaultdict
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from fpl_backtest_hold_baseline import D


BASE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/2026-27/gws/gw{}.csv"


def download(gw):
    req = Request(BASE.format(gw), headers={"User-Agent": "fpl-analytics-price-audit"})
    try:
        with urlopen(req, timeout=40) as response:
            return list(csv.DictReader(io.StringIO(response.read().decode("utf-8-sig"))))
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def main():
    history = json.loads((D / "historical_players_gw1_10.json").read_text(encoding="utf-8"))["players"]
    summary = []
    mismatches = []
    archive_prices = {}
    missing_gws = []
    for gw in range(1, 11):
        rows = download(gw)
        if rows is None:
            missing_gws.append(gw)
            summary.append({"gw": gw, "status": "archive_not_published_http_404",
                            "archive_rows": 0, "players_with_prices": 0,
                            "players_compared": 0, "exact_fixture_value_matches": 0})
            continue
        indexed = defaultdict(list)
        for row in rows:
            try:
                indexed[int(row["element"])].append(int(row["value"]))
            except (KeyError, ValueError, TypeError):
                continue
        matches = 0
        compared = 0
        for pid, fixtures in history.items():
            own = [int(f["value_at_fixture"]) for f in fixtures
                   if int(f["gw"]) == gw and f.get("value_at_fixture") is not None]
            if not own or int(pid) not in indexed:
                continue
            compared += 1
            if sorted(own) == sorted(indexed[int(pid)]):
                matches += 1
            else:
                mismatches.append({"gw": gw, "player_id": int(pid),
                                   "fpl_values": own, "archive_values": indexed[int(pid)]})
        archive_prices[str(gw)] = {str(pid): vals for pid, vals in indexed.items()}
        summary.append({"gw": gw, "archive_rows": len(rows),
                        "players_with_prices": len(indexed),
                        "players_compared": compared, "exact_fixture_value_matches": matches})
    report = {
        "status": "independent_fixture_price_crosscheck_not_deadline_prices",
        "source": "vaastav/Fantasy-Premier-League",
        "archive_csv_template": BASE,
        "by_gw": summary,
        "missing_archive_gws": missing_gws,
        "archive_coverage_complete": not missing_gws,
        "total_compared": sum(r["players_compared"] for r in summary),
        "total_matched": sum(r["exact_fixture_value_matches"] for r in summary),
        "mismatch_count": len(mismatches),
        "mismatches_first_100": mismatches[:100],
        "warnings": [
            "Agreement between fixture values does not establish the deadline price.",
            "GW CSV snapshots may include changes after the transfer deadline.",
            "Players without a fixture may not be represented in both sources.",
            "No changes to the budget-constrained model were made by this audit.",
            "HTTP 404 from the public archive is recorded as missing data, not a failed FPL calculation."
        ]
    }
    (D / "historical_price_archive_crosscheck.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"compared": report["total_compared"],
                      "matched": report["total_matched"],
                      "mismatches": report["mismatch_count"],
                      "missing_archive_gws": missing_gws}))


if __name__ == "__main__":
    main()
