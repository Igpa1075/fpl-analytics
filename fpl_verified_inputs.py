"""Optional manually verified FPL transfer inputs; never infer private account values."""
import json
from pathlib import Path

CONFIG = Path("config/transfer_inputs.json")


def load_verified_inputs(target_gw, owned_ids):
    if not CONFIG.exists():
        return None
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    if type(data.get("target_gw")) is not int or data["target_gw"] != target_gw:
        return None
    bank = data.get("bank_tenths_million")
    free = data.get("free_transfers")
    if type(bank) is not int or bank < 0 or type(free) is not int or not 0 <= free <= 5:
        raise ValueError("Invalid user-confirmed bank or free transfers")
    squad = data.get("squad_player_ids")
    squad_confirmed = (data.get("current_squad_confirmed_from_screenshot") is True
                       and isinstance(squad, list) and len(squad) == 15
                       and len(set(squad)) == 15 and set(squad) == set(owned_ids))
    partial = {"bank": bank, "free_transfers": free, "selling_prices": None,
               "verified_current_squad": False,
               "current_squad_confirmed": squad_confirmed}
    if not data.get("verified_current_squad"):
        return partial
    if type(data.get("target_gw")) is not int or data["target_gw"] != target_gw:
        return None
    squad = data.get("squad_player_ids")
    if not isinstance(squad, list) or len(squad) != 15 or len(set(squad)) != 15:
        raise ValueError("Manual current squad must list exactly 15 distinct player IDs")
    if set(squad) != set(owned_ids):
        return partial  # A different current squad requires a new complete squad integration.
    bank = data.get("bank_tenths_million")
    free = data.get("free_transfers")
    sales = data.get("selling_prices_tenths_million")
    if type(bank) is not int or bank < 0 or type(free) is not int or not 0 <= free <= 5:
        raise ValueError("Invalid bank or free transfer count in manual inputs")
    if not isinstance(sales, dict) or set(sales) != {str(i) for i in owned_ids}:
        raise ValueError("Provide verified selling prices for all 15 owned players")
    if any(type(v) is not int or v < 0 for v in sales.values()):
        raise ValueError("Selling prices must be nonnegative integers in 0.1m units")
    return {"bank": bank, "free_transfers": free,
            "selling_prices": {int(k): v for k, v in sales.items()},
            "verified_current_squad": True,
            "current_squad_confirmed": True}


def transfer_hit(count, free_transfers):
    return 4 * max(0, count - free_transfers)
