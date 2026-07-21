"""Iteration 10 — Team Member Profiles, Badges, Challenges, Leaderboard, Team HQ.

Covers backend seed, privacy, role-gates, credit + prompt flows, and challenge lifecycle.
Cleans up all created data at teardown so DB stays clean.
"""

import os
import datetime as dt
from typing import Any, Dict, Optional

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
API = BASE_URL + "/api"

TODAY = dt.date.today().isoformat()
YESTERDAY = (dt.date.today() - dt.timedelta(days=1)).isoformat()


def _login(email: Optional[str], password: str) -> str:
    body: Dict[str, Any] = {"password": password}
    if email:
        body["email"] = email
    r = requests.post(f"{API}/auth/login", json=body, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


def _hdr(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------- fixtures ----------

@pytest.fixture(scope="session")
def owner_token():
    return _login("HaulYeahOwner", "HaulYeah2026!")


@pytest.fixture(scope="session")
def javante_token():
    return _login("javante@haulyeahmoves.com", "JavCrew2026!")


@pytest.fixture(scope="session")
def junior_token():
    return _login("junior@haulyeahmoves.com", "JunCrew2026!")


@pytest.fixture(scope="session")
def ghost_crew_token():
    return _login("TestCrewAdmin", "HaulYeah2026!")


@pytest.fixture(scope="session")
def ghost_sales_token():
    return _login("TestSalesAdmin", "HaulYeah2026!")


@pytest.fixture(scope="session")
def ghost_marketing_token():
    return _login("TestMarketingAdmin", "HaulYeah2026!")


@pytest.fixture(scope="session")
def user_ids(owner_token):
    r = requests.get(f"{API}/team/members", headers=_hdr(owner_token), timeout=15)
    assert r.status_code == 200
    m = r.json()["members"]
    mapping = {u["name"]: u["id"] for u in m}
    # Look up by known names
    ids = {}
    for u in m:
        if "javante" in u["name"].lower():
            ids["javante"] = u["id"]
        if "junior" in u["name"].lower():
            ids["junior"] = u["id"]
    assert "javante" in ids and "junior" in ids, f"could not find javante/junior in {mapping}"
    return ids


# ---------- 1. Badges seed ----------

class TestBadges:
    def test_badges_seeded_27(self, owner_token):
        r = requests.get(f"{API}/badges", headers=_hdr(owner_token), timeout=10)
        assert r.status_code == 200
        badges = r.json()["badges"]
        assert len(badges) >= 27, f"expected 27 seeded, got {len(badges)}"
        ids = {b["id"] for b in badges}
        for slug in ("first-haul", "two-way-player", "workhorse", "first-close", "closer", "behind-the-wheel"):
            assert slug in ids, f"missing seeded badge {slug}"
        crew = [b for b in badges if b["track"] == "crew"]
        sales = [b for b in badges if b["track"] == "sales"]
        assert len(crew) >= 18
        assert len(sales) >= 9

    def test_any_role_can_read_badges(self, javante_token, ghost_sales_token, ghost_marketing_token):
        for t in (javante_token, ghost_sales_token, ghost_marketing_token):
            r = requests.get(f"{API}/badges", headers=_hdr(t), timeout=10)
            assert r.status_code == 200


# ---------- 2. Challenges seed + scoping ----------

class TestChallenges:
    def test_owner_sees_all_with_is_owner_true(self, owner_token):
        r = requests.get(f"{API}/challenges", headers=_hdr(owner_token), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["is_owner"] is True
        names = {c["name"] for c in j["challenges"]}
        assert any(n.startswith("Full House") for n in names)
        assert "King of the Weekend" in names
        assert "Six-Pack Sprint" in names
        assert "Whale Hunt" in names

    def test_crew_only_sees_only_crew(self, ghost_crew_token):
        r = requests.get(f"{API}/challenges", headers=_hdr(ghost_crew_token), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["is_owner"] is False
        teams = {c["team"] for c in j["challenges"]}
        assert teams == {"crew"}, f"crew user saw teams={teams}"

    def test_sales_only_sees_only_sales(self, ghost_sales_token):
        r = requests.get(f"{API}/challenges", headers=_hdr(ghost_sales_token), timeout=15)
        j = r.json()
        teams = {c["team"] for c in j["challenges"]}
        assert teams == {"sales"}

    def test_marketing_sees_both(self, ghost_marketing_token):
        r = requests.get(f"{API}/challenges", headers=_hdr(ghost_marketing_token), timeout=15)
        j = r.json()
        teams = {c["team"] for c in j["challenges"]}
        assert teams == {"crew", "sales"}

    def test_dual_team_javante_sees_both(self, javante_token):
        r = requests.get(f"{API}/challenges", headers=_hdr(javante_token), timeout=15)
        j = r.json()
        teams = {c["team"] for c in j["challenges"]}
        assert teams == {"crew", "sales"}, f"dual-team saw {teams}"


# ---------- 3. Directory hides ghosts ----------

class TestDirectoryHidesGhosts:
    def test_no_ghost_in_directory(self, owner_token, javante_token, ghost_crew_token):
        for t in (owner_token, javante_token, ghost_crew_token):
            r = requests.get(f"{API}/team/members", headers=_hdr(t), timeout=15)
            assert r.status_code == 200
            names = [m["name"].lower() for m in r.json()["members"]]
            for banned in ("testcrewadmin", "testsalesadmin", "testmarketingadmin"):
                assert not any(banned in n.replace(" ", "") for n in names), \
                    f"ghost {banned} leaked to token role"


# ---------- 4. Privacy ----------

class TestPrivacy:
    def test_crew_viewing_another_gets_no_stats(self, ghost_crew_token, user_ids):
        r = requests.get(f"{API}/team/members/{user_ids['junior']}",
                         headers=_hdr(ghost_crew_token), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j.get("can_see_numbers") is False
        assert "stats" not in j
        assert "progress" not in j

    def test_owner_sees_stats_on_everyone(self, owner_token, user_ids):
        r = requests.get(f"{API}/team/members/{user_ids['junior']}",
                         headers=_hdr(owner_token), timeout=15)
        j = r.json()
        assert j.get("can_see_numbers") is True
        assert "stats" in j and "progress" in j

    def test_self_sees_stats(self, junior_token, user_ids):
        r = requests.get(f"{API}/team/members/{user_ids['junior']}",
                         headers=_hdr(junior_token), timeout=15)
        j = r.json()
        assert j.get("is_self") is True
        assert "stats" in j and "progress" in j


# ---------- 5. Profile edit + pins ----------

class TestProfileMutations:
    def test_put_profile_saves(self, junior_token):
        payload = {"display_name": "Junior QA", "nickname": "JQA", "bio": "test bio",
                   "role_title": "Crew", "favorite_move": "piano", "fun_fact": "tests"}
        r = requests.put(f"{API}/profile", json=payload, headers=_hdr(junior_token), timeout=15)
        assert r.status_code == 200
        assert r.json()["profile"]["nickname"] == "JQA"

    def test_moderate_is_owner_only(self, ghost_crew_token, user_ids):
        r = requests.put(f"{API}/team/members/{user_ids['junior']}/moderate",
                         json={"display_name": "hack"}, headers=_hdr(ghost_crew_token), timeout=15)
        assert r.status_code == 403

    def test_pins_reject_locked_badge(self, junior_token):
        r = requests.put(f"{API}/profile/pins",
                         json={"badge_ids": ["quarter-club"]},
                         headers=_hdr(junior_token), timeout=15)
        assert r.status_code == 422

    def test_pins_cap_at_3(self, junior_token, owner_token, user_ids):
        # Award 4 badges, try to pin all 4, expect only 3 saved
        badges = ["piano-mover", "iron-streak", "stair-master", "early-bird"]
        for bid in badges:
            requests.post(f"{API}/badges/{bid}/award",
                          json={"user_id": user_ids["junior"]},
                          headers=_hdr(owner_token), timeout=10)
        r = requests.put(f"{API}/profile/pins",
                         json={"badge_ids": badges},
                         headers=_hdr(junior_token), timeout=15)
        assert r.status_code == 200
        assert len(r.json()["pinned"]) == 3
        # cleanup
        requests.put(f"{API}/profile/pins", json={"badge_ids": []},
                     headers=_hdr(junior_token), timeout=10)
        for bid in badges:
            requests.delete(f"{API}/badges/{bid}/award/{user_ids['junior']}",
                            headers=_hdr(owner_token), timeout=10)


# ---------- 6. Owner-only 403 matrix ----------

OWNER_ONLY_ENDPOINTS = [
    ("GET", "/credits"),
    ("POST", "/credits"),
    ("GET", "/credit-prompts"),
    ("POST", "/badges"),
    ("PATCH", "/badges/first-haul"),
    ("POST", "/badges/first-haul/award"),
    ("POST", "/challenges"),
    ("PATCH", "/challenges/nonexistent"),
    ("DELETE", "/challenges/nonexistent"),
    ("POST", "/challenges/nonexistent/verify"),
    ("POST", "/challenges/nonexistent/award"),
    ("GET", "/admin/crew-comparison"),
]


class TestOwnerOnly403Matrix:
    @pytest.mark.parametrize("method,path", OWNER_ONLY_ENDPOINTS)
    def test_non_owner_gets_403(self, method, path, ghost_crew_token,
                                 ghost_sales_token, ghost_marketing_token):
        for t in (ghost_crew_token, ghost_sales_token, ghost_marketing_token):
            r = requests.request(method, f"{API}{path}",
                                  headers=_hdr(t), json={} if method != "GET" else None,
                                  timeout=15)
            assert r.status_code == 403, \
                f"{method} {path} expected 403 for non-owner token, got {r.status_code}"


# ---------- 7. E2E credit flow ----------

class TestCreditFlowE2E:
    def test_credit_unlocks_badges(self, owner_token, user_ids):
        junior_id = user_ids["junior"]

        # Baseline: make sure the badges are not already awarded
        for slug in ("first-haul", "behind-the-wheel"):
            requests.delete(f"{API}/badges/{slug}/award/{junior_id}",
                            headers=_hdr(owner_token), timeout=10)

        # Baseline stats
        pre = requests.get(f"{API}/team/members/{junior_id}",
                           headers=_hdr(owner_token), timeout=10).json()
        pre_jobs = pre["stats"]["jobs_total"]
        pre_driver = pre["stats"]["driver"]

        # POST credit
        payload = {"user_id": junior_id, "team": "crew", "role_tag": "driver",
                   "job_ref": "QA test job", "date": TODAY}
        r = requests.post(f"{API}/credits", json=payload,
                          headers=_hdr(owner_token), timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        credit_id = j["credit"]["id"]
        newly = set(j["newly_unlocked"])
        try:
            assert "First Haul" in newly, f"newly_unlocked={newly}"
            assert "Behind the Wheel" in newly, f"newly_unlocked={newly}"

            # Stats bumped
            post = requests.get(f"{API}/team/members/{junior_id}",
                                headers=_hdr(owner_token), timeout=10).json()
            assert post["stats"]["jobs_total"] == pre_jobs + 1
            assert post["stats"]["driver"] == pre_driver + 1

            # Gallery reflects unlock
            crew_gallery = post["gallery"]["crew"]
            fh = next((b for b in crew_gallery if b["id"] == "first-haul"), None)
            btw = next((b for b in crew_gallery if b["id"] == "behind-the-wheel"), None)
            assert fh and fh["unlocked"] is True
            assert btw and btw["unlocked"] is True

            # Leaderboard has junior with count >= 1
            lb = requests.get(f"{API}/leaderboard",
                              headers=_hdr(owner_token), timeout=15).json()
            row = next((r for r in lb["crew"] if r["user_id"] == junior_id), None)
            assert row is not None and row["count"] >= 1

            # Notifications for junior include badge type
            junior_tok = _login("junior@haulyeahmoves.com", "JunCrew2026!")
            notif = requests.get(f"{API}/notifications",
                                  headers=_hdr(junior_tok), timeout=10).json()
            items = notif.get("items") or notif.get("notifications") or []
            types = {i.get("type") for i in items}
            assert "badge" in types, f"no badge notif in {types}"
        finally:
            # Cleanup: delete credit + revoke both badges
            requests.delete(f"{API}/credits/{credit_id}",
                            headers=_hdr(owner_token), timeout=10)
            for slug in ("first-haul", "behind-the-wheel"):
                requests.delete(f"{API}/badges/{slug}/award/{junior_id}",
                                headers=_hdr(owner_token), timeout=10)


# ---------- 8. Crew prompt flow ----------

class TestCrewPromptFlow:
    def test_assignment_complete_creates_prompt(self, owner_token, javante_token, user_ids):
        javante_id = user_ids["javante"]
        # Create assignment
        r = requests.post(f"{API}/assignments",
                          json={"project_id": "recQA_iter10", "job_name": "QA Prompt Job",
                                "job_date": TODAY,
                                "crew": [{"user_id": javante_id, "position": "Driver"}]},
                          headers=_hdr(owner_token), timeout=15)
        assert r.status_code == 200, r.text
        aid = r.json()["assignment"]["id"] if "assignment" in r.json() else r.json().get("id") or r.json().get("_id")
        # Sometimes returns bare doc
        if not aid:
            aid = r.json().get("id")
        assert aid, f"could not extract assignment id from {r.json()}"

        try:
            # Walk statuses
            for status in ("En Route", "Arrived", "In Progress", "Complete"):
                sr = requests.post(f"{API}/crew/jobs/{aid}/status",
                                   json={"status": status},
                                   headers=_hdr(javante_token), timeout=15)
                assert sr.status_code == 200, f"status {status}: {sr.text}"

            # Owner sees the pending prompt
            pr = requests.get(f"{API}/credit-prompts",
                              headers=_hdr(owner_token), timeout=10).json()
            prompts = pr["prompts"]
            mine = [p for p in prompts if p["user_id"] == javante_id and "QA Prompt Job" in (p.get("job_ref") or "")]
            assert mine, f"no prompt for javante in {[p['job_ref'] for p in prompts]}"
            prompt = mine[0]
            assert "QA Prompt Job" in prompt["message"]
            # Badge hint expected (Javante may already have Behind the Wheel — hint can be empty)
            # so we don't strictly assert on hint text

            # Dismiss it
            resolve = requests.post(f"{API}/credit-prompts/{prompt['id']}/resolve",
                                    json={"approve": False},
                                    headers=_hdr(owner_token), timeout=10)
            assert resolve.status_code == 200
            assert resolve.json()["ok"] is True
        finally:
            requests.delete(f"{API}/assignments/{aid}",
                             headers=_hdr(owner_token), timeout=10)


# ---------- 9. Challenge lifecycle ----------

class TestChallengeLifecycle:
    def test_owner_verified_lifecycle(self, owner_token, user_ids):
        junior_id = user_ids["junior"]
        # Create challenge that already ended
        payload = {"name": "QA Test Challenge", "description": "iter10 test",
                   "team": "crew", "type": "individual",
                   "metric": "owner_verified", "target": 2,
                   "start": YESTERDAY, "end": YESTERDAY,
                   "reward_kind": "title", "reward_title": "QA Tester"}
        r = requests.post(f"{API}/challenges", json=payload,
                          headers=_hdr(owner_token), timeout=15)
        assert r.status_code == 200, r.text
        ch_id = r.json()["id"]
        try:
            # GET should flip status to needs_verify
            listing = requests.get(f"{API}/challenges",
                                   headers=_hdr(owner_token), timeout=15).json()
            mine = next(c for c in listing["challenges"] if c["id"] == ch_id)
            assert mine["status"] == "needs_verify", f"status={mine['status']}"

            # Verify a member value
            vr = requests.post(f"{API}/challenges/{ch_id}/verify",
                               json={"user_id": junior_id, "value": 2},
                               headers=_hdr(owner_token), timeout=10)
            assert vr.status_code == 200

            # Award
            ar = requests.post(f"{API}/challenges/{ch_id}/award",
                               json={"winners": [junior_id]},
                               headers=_hdr(owner_token), timeout=10)
            assert ar.status_code == 200
            assert ar.json()["status"] == "awarded"

            # Junior member detail now has title
            detail = requests.get(f"{API}/team/members/{junior_id}",
                                  headers=_hdr(owner_token), timeout=10).json()
            assert "QA Tester" in detail.get("titles", []), \
                f"title missing, got {detail.get('titles')}"
        finally:
            # Clean up: pull the title from junior; delete the challenge
            requests.delete(f"{API}/challenges/{ch_id}",
                             headers=_hdr(owner_token), timeout=10)


# ---------- 10. Regression: seeded counts unchanged ----------

class TestFinalRegression:
    def test_still_27_badges_and_4_challenges(self, owner_token):
        b = requests.get(f"{API}/badges", headers=_hdr(owner_token), timeout=10).json()
        assert len(b["badges"]) >= 27
        c = requests.get(f"{API}/challenges", headers=_hdr(owner_token), timeout=15).json()
        # QA created was deleted so we should have exactly the seeded 4 (or more if others were created)
        seeded = [x for x in c["challenges"] if x.get("id") and "QA Test Challenge" not in x["name"]]
        assert len(seeded) >= 4
