# utils/site_blocks.py — which parts of each client site the client can edit in "My website", in site order.
# The lists live in utils/site_blocks/<domain>.json and are made by tools/make_site_blocks.py, which also puts the
# same list in the site (static/hapitech/blocks.json) so unedited blocks render exactly as before.
import json
import os

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site_blocks")


def definitions_for(account, site_dir=None):
    p = os.path.join(HERE, f"{account.domain}.json") if account.domain else None
    if not p or not os.path.exists(p):
        return []
    return [d for d in json.load(open(p, encoding="utf-8"))]
