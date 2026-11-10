import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGIN = os.environ.get("GH_LOGIN", "clemcube")
QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

request = urllib.request.Request(
    "https://api.github.com/graphql",
    data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
    headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Content-Type": "application/json",
        "User-Agent": "clemcube-profile-cards",
    },
)
with urllib.request.urlopen(request, timeout=30) as response:
    payload = json.load(response)

if payload.get("errors"):
    raise SystemExit(f"GitHub GraphQL a refusé la requête : {payload['errors']}")

calendar = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]
data = {
    "login": LOGIN,
    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "total": calendar["totalContributions"],
    "weeks": [
        [[day["date"], day["contributionCount"]] for day in week["contributionDays"]]
        for week in calendar["weeks"]
    ],
}
(ROOT / "data").mkdir(exist_ok=True)
(ROOT / "data" / "contributions.json").write_text(json.dumps(data, indent=1) + "\n")
print(f"{LOGIN} : {data['total']} contributions sur {len(data['weeks'])} semaines")
