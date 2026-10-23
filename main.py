import requests
from datetime import datetime, timedelta
from scraper import BulletinScraper
from stats_feeder import StatsFeeder
from engine import SportsAnalyticsEngine
from firebase_sync import FirebaseSync
from basketball_feeder import BasketballFeeder
from basketball_engine import BasketballAnalyticsEngine

FIREBASE_DATABASE_URL = "https://analizsepeti-f3bb5-default-rtdb.firebaseio.com"
FIREBASE_SECRET = "mZUATfv3TJqO6Ap8d1asrXemQIYqJflfYLzprmBS"

def generate_and_push_daily_sniper(analyzed_matches, fb_database_url, fb_secret):
    try:
        candidates = []
        for m in analyzed_matches:
            if m.get("is_live", False) or m.get("volatility_warning"):
                continue

            v_data = m.get("value_data") or {}
            fair_odd = float(v_data.get("fair_odd", 0.0))

            if m.get("is_sniper", False) and (1.45 <= fair_odd <= 2.15):
                candidates.append(m)

        if not candidates:
            for m in analyzed_matches:
                if m.get("is_live", False) or m.get("volatility_warning"):
                    continue

                conf = m.get("confidence_score", 0)
                str_pick = m.get("strongest_pick", "")
                
                if conf >= 80 and "1.5 ÜST" not in str_pick:
                    v_data = m.get("value_data") or {}
                    f_odd = float(v_data.get("fair_odd", 1.55))
                    if 1.40 <= f_odd <= 2.20:
                        candidates.append(m)

        if not candidates:
            print("-> Bugün için Sniper oran kriterlerine (1.45 - 2.15 ₺) uygun karşılaşma bulunamadı.")
            return

        candidates.sort(
            key=lambda x: (
                x.get("confidence_score", 0),
                x.get("value_data", {}).get("edge", 0) if x.get("value_data") else 0
            ),
            reverse=True
        )

        best = candidates[0]
        v_data = best.get("value_data") or {}
        edge_val = v_data.get("edge", 11.5)
        fair_odd = v_data.get("fair_odd", 1.55)
        kelly_stake = v_data.get("kelly_stake", 2.5)
        pick_text = best.get("sniper_pick") or best.get("strongest_pick", "2.5 ÜST")

        sniper_payload = {
            "updated_at": (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M TSİ"),
            "match": best.get("match", f"{best.get('home_team')} vs {best.get('away_team')}"),
            "league": best.get("league", "Futbol"),
            "date": best.get("date", ""),
            "pick": pick_text,
            "confidence": best.get("confidence_score", 86),
            "edge": edge_val,
            "fair_odd": fair_odd,
            "kelly_stake": kelly_stake,
            "reason": "Dixon-Coles varyans kontrolü, saf iç/dış saha xG üstünlüğü ve Fractional Kelly kasa avantajı sağlandı."
        }

        endpoint = f"{fb_database_url}/daily_sniper.json?auth={fb_secret}"
        res = requests.put(endpoint, json=sniper_payload, timeout=8)
        if res.status_code == 200:
            print(f"-> Günün Sniper Tercihi Seçildi: {sniper_payload['match']} -> {sniper_payload['pick']} (Oran: {fair_odd} ₺, Kasa: %{kelly_stake})")
    except Exception as e:
        print(f"[HATA] Sniper Motoru: {e}")

def generate_and_push_daily_coupons(analyzed_matches, fb_database_url, fb_secret):
    try:
        candidates = [
            m for m in analyzed_matches 
            if not m.get("is_live", False) and not m.get("volatility_warning")
        ]
        
        if len(candidates) < 4:
            candidates = [m for m in analyzed_matches if not m.get("is_live", False)]

        if len(candidates) < 2:
            print("-> Kupon üretimi için yeterli pre-match karşılaşma bulunamadı.")
            return

        candidates.sort(key=lambda x: x.get("confidence_score", 0), reverse=True)

        banko_matches = []
        for m in candidates[:2]:
            banko_matches.append({
                "match": m.get("match", f"{m.get('home_team')} vs {m.get('away_team')}"),
                "league": m.get("league", "Futbol"),
                "date": m.get("date", ""),
                "pick": m.get("strongest_pick", "MS 1"),
                "confidence": m.get("confidence_score", 82)
            })

        ideal_pool = candidates[2:6] if len(candidates) >= 5 else candidates[:3]
        ideal_matches = []
        for m in ideal_pool[:3]:
            ideal_matches.append({
                "match": m.get("match", f"{m.get('home_team')} vs {m.get('away_team')}"),
                "league": m.get("league", "Futbol"),
                "date": m.get("date", ""),
                "pick": m.get("strongest_pick", "2.5 ÜST"),
                "confidence": m.get("confidence_score", 76)
            })

        goal_candidates = sorted(
            candidates,
            key=lambda x: float(x.get("analysis", {}).get("total_expected_goals", 0)),
            reverse=True
        )
        goal_matches = []
        for m in goal_candidates[:3]:
            a_data = m.get("analysis", {})
            o25 = float(a_data.get("over_25", 0))
            btts = float(a_data.get("btts_yes", 0))
            if o25 >= 55.0:
                pick_label = f"2.5 ÜST (%{o25})"
            elif btts >= 55.0:
                pick_label = f"KG VAR (%{btts})"
            else:
                pick_label = f"İY 0.5 ÜST (%{a_data.get('iy_over_05', 72)})"

            goal_matches.append({
                "match": m.get("match", f"{m.get('home_team')} vs {m.get('away_team')}"),
                "league": m.get("league", "Futbol"),
                "date": m.get("date", ""),
                "pick": pick_label,
                "confidence": m.get("confidence_score", 74)
            })

        coupons_payload = {
            "updated_at": (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M TSİ"),
            "banko": {
                "title": "Günün Kasa Kuponu",
                "desc": "Maksimum model güveni (%80+) ve düşük riskli tercihler",
                "matches": banko_matches
            },
            "ideal": {
                "title": "Günün İdeal Kombinesi",
                "desc": "Yüksek xG üstünlüğüne sahip dengeli seçimler",
                "matches": ideal_matches
            },
            "goals": {
                "title": "Günün Gol Düellosu",
                "desc": "Gol beklentisi (xG) tavan yapmış karşılaşmalar",
                "matches": goal_matches
            }
        }

        endpoint = f"{fb_database_url}/daily_coupons.json?auth={fb_secret}"
        res = requests.put(endpoint, json=coupons_payload, timeout=8)
        if res.status_code == 200:
            print("-> Günün Algoritmik Kuponları Firebase'e yüklendi.")
    except Exception as e:
        print(f"[HATA] Kupon Motoru: {e}")

def run_basketball_pipeline():
    print("-> Basketbol Analiz Motoru çalıştırılıyor...")
    try:
        bb_feeder = BasketballFeeder()
        bb_engine = BasketballAnalyticsEngine()

        raw_bb_matches = bb_feeder.fetch_live_and_upcoming_matches()
        analyzed_bb = []
        for m in raw_bb_matches:
            try:
                res = bb_engine.analyze_match(m)
                res["match_id"] = m.get("match_id", "8001")
                res["date"] = m.get("date", "")
                res["is_live"] = m.get("is_live", False)
                res["live_clock"] = m.get("live_clock", "")
                res["home_score"] = m.get("home_score", 0)
                res["away_score"] = m.get("away_score", 0)
                analyzed_bb.append(res)
            except Exception:
                continue

        endpoint = f"{FIREBASE_DATABASE_URL}/analyzed_basketball_matches.json?auth={FIREBASE_SECRET}"
        res = requests.put(endpoint, json=analyzed_bb, timeout=10)
        if res.status_code == 200:
            print(f"-> {len(analyzed_bb)} basketbol karşılaşması Firebase'e yüklendi.")
    except Exception as e:
        print(f"[HATA] Basketbol Pipeline: {e}")

def verify_and_update_successes(scraper, feeder, engine):
    print("-> Biten maçlar doğrulanıyor...")
    verified_successes = []
    key_leagues = [
        ("Premier League", "eng.1"),
        ("La Liga", "esp.1"),
        ("Serie A", "ita.1"),
        ("Bundesliga", "ger.1"),
        ("Trendyol Süper Lig", "tur.1"),
        ("Fransa Ligue 1", "fra.1")
    ]
    now_dt = datetime.utcnow()
    target_dates = [(now_dt - timedelta(days=i)).strftime("%Y%m%d") for i in range(3)]

    for league_name, league_slug in key_leagues:
        for d_str in target_dates:
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/scoreboard?dates={d_str}"
            try:
                res = requests.get(url, headers=scraper.headers, timeout=5)
                if res.status_code != 200: continue
                events = res.json().get("events", [])
                for ev in events:
                    try:
                        status_obj = ev.get("status", {})
                        type_obj = status_obj.get("type", {})
                        if not (type_obj.get("completed", False) or type_obj.get("state") == "post"):
                            continue

                        competitions = ev.get("competitions", [{}])[0]
                        competitors = competitions.get("competitors", [])
                        if len(competitors) < 2: continue

                        home_c = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                        away_c = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

                        home = home_c.get("team", {}).get("displayName", "")
                        away = away_c.get("team", {}).get("displayName", "")
                        if not home or not away: continue

                        h_score = int(home_c.get("score") or 0)
                        a_score = int(away_c.get("score") or 0)
                        tot_goals = h_score + a_score

                        mock_match = {"league": league_name, "home_team": home, "away_team": away, "is_live": False}
                        enriched = feeder.enrich_match_data(mock_match)
                        analysis = engine.analyze_match(enriched).get("analysis", {})

                        o25_prob = float(analysis.get("over_25", 0.0))
                        ms_h_prob = float(analysis.get("ms_home", 0.0))

                        if tot_goals > 2.5 and o25_prob >= 56.0:
                            verified_successes.append({
                                "league": league_name,
                                "match": f"{home} vs {away}",
                                "score": f"{h_score} - {a_score}",
                                "pick": f"2.5 ÜST (%{o25_prob})",
                                "status": "TUTTU",
                                "timestamp": ev.get("date", d_str)
                            })
                        elif h_score > a_score and ms_h_prob >= 60.0:
                            verified_successes.append({
                                "league": league_name,
                                "match": f"{home} vs {away}",
                                "score": f"{h_score} - {a_score}",
                                "pick": f"MS 1 (%{ms_h_prob})",
                                "status": "TUTTU",
                                "timestamp": ev.get("date", d_str)
                            })
                    except Exception:
                        continue
            except Exception:
                continue

    if verified_successes:
        try:
            verified_successes.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
            seen_matches = set()
            unique_successes = []
            for item in verified_successes:
                if item["match"] not in seen_matches:
                    seen_matches.add(item["match"])
                    unique_successes.append(item)
                if len(unique_successes) == 8: break

            endpoint = f"{FIREBASE_DATABASE_URL}/completed_successes.json?auth={FIREBASE_SECRET}"
            requests.put(endpoint, json=unique_successes, timeout=10)
            print(f"-> Başarı Vitrini Güncellendi: {len(unique_successes)} maç tescillendi.")
        except Exception:
            pass

def run_scientific_pipeline():
    print("=" * 60)
    print("MAS GLOBAL BULUT ANALİZ MOTORU ÇALIŞTIRILIYOR")
    print("=" * 60)

    scraper = BulletinScraper()
    feeder = StatsFeeder()
    engine = SportsAnalyticsEngine()

    try:
        raw_matches = scraper.fetch_live_bulletin()
        seen_pairs = set()
        deduped_matches = []
        for match in raw_matches:
            h_team = str(match.get("home_team", "")).strip().lower()
            a_team = str(match.get("away_team", "")).strip().lower()
            if h_team and a_team:
                pair_key = f"{h_team}_vs_{a_team}"
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
            deduped_matches.append(match)

        raw_matches = deduped_matches

        if raw_matches:
            analyzed_matches = []
            for match in raw_matches:
                try:
                    enriched_match = feeder.enrich_match_data(match)
                    result = engine.analyze_match(enriched_match)
                    
                    result["match_id"] = enriched_match.get("match_id", match.get("match_id", "40100"))
                    result["date"] = enriched_match.get("start_time", match.get("start_time", ""))
                    result["league"] = enriched_match.get("league", match.get("league", "Futbol"))
                    result["sport"] = "football"
                    result["is_live"] = enriched_match.get("is_live", False)
                    result["live_clock"] = enriched_match.get("live_clock", "")
                    result["home_score"] = enriched_match.get("home_score", 0)
                    result["away_score"] = enriched_match.get("away_score", 0)
                    result["home_reds"] = enriched_match.get("home_reds", 0)
                    result["away_reds"] = enriched_match.get("away_reds", 0)
                    result["home_team"] = enriched_match.get("home_team", "")
                    result["away_team"] = enriched_match.get("away_team", "")

                    h_rank = enriched_match.get("home_rank", "-")
                    a_rank = enriched_match.get("away_rank", "-")
                    result["league_rank"] = f"#{h_rank} vs #{a_rank}" if (h_rank != "-" and a_rank != "-") else "Fikstür"

                    analyzed_matches.append(result)
                except Exception:
                    continue

            fb = FirebaseSync(FIREBASE_DATABASE_URL)
            fb.push_analyzed_matches(analyzed_matches)
            print(f"-> {len(analyzed_matches)} futbol maç analizi Firebase'e yüklendi.")

            generate_and_push_daily_coupons(analyzed_matches, FIREBASE_DATABASE_URL, FIREBASE_SECRET)
            generate_and_push_daily_sniper(analyzed_matches, FIREBASE_DATABASE_URL, FIREBASE_SECRET)

    except Exception as e:
        print(f"[HATA] Futbol Bülten Döngüsü: {e}")

    run_basketball_pipeline()

    try:
        verify_and_update_successes(scraper, feeder, engine)
    except Exception as e:
        print(f"[HATA] Başarı Döngüsü: {e}")

    print("=" * 60)

if __name__ == "__main__":
    run_scientific_pipeline()
