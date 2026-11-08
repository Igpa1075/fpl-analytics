
import json
import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")
DATA.mkdir(exist_ok=True)

OUT = DATA / "control_sample_pilot.json"
API = "https://fantasy.premierleague.com/api"

SEED = 20261108
BATCH = 150
MAX_ATTEMPTS = 3
DELAY = 0.4


def fetch(path):
    for attempt in range(MAX_ATTEMPTS):
        try:
            req = urllib.request.Request(
                API + path,
                headers={
                    "User-Agent": "FPL-research-pilot/1.0",
                    "Accept": "application/json"
                }
            )

            with urllib.request.urlopen(
                req, timeout=20
            ) as response:
                return json.load(response), "ok"

        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                return None, str(exc.code)

            if exc.code == 429:
                print("Rate limit detected")
                return None, "rate_limited"

            print(f"HTTP {exc.code}: {path}")

        except (
            urllib.error.URLError,
            TimeoutError
        ) as exc:
            print(f"Network error: {exc}")

        time.sleep(2 * (attempt + 1))

    return None, "error"


def save(state):
    temp = OUT.with_suffix(".tmp")

    temp.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    temp.replace(OUT)


def main():
    bootstrap = DATA / "bootstrap.json"

    if bootstrap.exists():
        boot = json.loads(
            bootstrap.read_text(encoding="utf-8")
        )
    else:
        boot, status = fetch("/bootstrap-static/")

        if status != "ok":
            raise RuntimeError(
                "Bootstrap unavailable"
            )

    total_players = int(
        boot.get("total_players", 0)
    )

    if total_players < 1000:
        raise RuntimeError(
            "Invalid total_players"
        )

    if OUT.exists():
        state = json.loads(
            OUT.read_text(encoding="utf-8")
        )

        if state.get("seed") != SEED:
            raise RuntimeError(
                "Sampling seed mismatch"
            )

    else:
        state = {
            "study": "random_id_feasibility_pilot",
            "seed": SEED,
            "total_players_at_start": total_players,
            "id_upper_bound": total_players * 2,
            "attempted": {},
            "notes": [
                "Random IDs are not guaranteed "
                "to represent all FPL managers.",
                "Registration order may cause bias.",
                "No rank or activity filters applied.",
                "Pilot is not for causal conclusions."
            ]
        }

    rng = random.Random(SEED)

    upper = state["id_upper_bound"]
    tested = set(state["attempted"])

    selected = []
    selected_set = set()

    while len(selected) < BATCH:
        entry_id = str(
            rng.randint(1, upper)
        )

        if (
            entry_id not in tested
            and entry_id not in selected_set
        ):
            selected.append(entry_id)
            selected_set.add(entry_id)

    for index, entry_id in enumerate(
        selected, 1
    ):
        entry, status = fetch(
            f"/entry/{entry_id}/"
        )

        if status == "rate_limited":
            save(state)
            break

        record = {
            "status": status
        }

        if (
            status == "ok"
            and isinstance(entry, dict)
        ):
            record.update({
                "overall_points": entry.get(
                    "summary_overall_points"
                ),
                "overall_rank": entry.get(
                    "summary_overall_rank"
                ),
                "started_event": entry.get(
                    "started_event"
                ),
                "current_event": entry.get(
                    "current_event"
                )
            })

        state["attempted"][entry_id] = record

        if index % 25 == 0:
            save(state)
            print(
                f"Checked {index}/{BATCH}"
            )

        time.sleep(DELAY)

    state["last_checked_utc"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    state["tested_count"] = len(
        state["attempted"]
    )

    state["valid_count"] = sum(
        record["status"] == "ok"
        for record in state["attempted"].values()
    )

    state["valid_fraction"] = round(
        state["valid_count"]
        / max(1, state["tested_count"]),
        4
    )

    save(state)

    print(
        json.dumps(
            {
                "tested_count": state[
                    "tested_count"
                ],
                "valid_count": state[
                    "valid_count"
                ],
                "valid_fraction": state[
                    "valid_fraction"
                ]
            },
            indent=2
        )
    )


if __name__ == "__main__":
    main()
