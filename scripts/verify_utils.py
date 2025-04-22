import os
from collections import defaultdict


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def filter_successful_procedures(results):
    success_map = defaultdict(list)
    for r in results:
        success_map[r["procedure_id"]].append(r["success"])
    return [pid for pid, success_list in success_map.items() if all(success_list)]