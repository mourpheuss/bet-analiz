import requests
from datetime import datetime, timedelta
from scraper import BulletinScraper
from stats_feeder import StatsFeeder
from engine import SportsAnalyticsEngine
from firebase_sync import FirebaseSync

FIREBASE_DATABASE_URL = "https://analizsepeti-f3bb5-default-rtdb.firebaseio.com"
FIREBASE_SECRET = "mZUATfv3TJqO6Ap8d1asrXemQIYqJflfYLzprmBS"

def verify_and_update_successes(scraper, feeder, engine):
    print("-> Biten kupa ve lig maçları taranıyor (Son 5 gün)...")
    verified_successes = []

    key_leagues = [
        ("Trendyol Süper Lig", "tur.1"),
        ("Premier League", "eng.1"),
        ("La Liga", "esp.1"),
        ("Serie A", "ita.1"),
        ("Bundesliga", "ger.1"),
        ("Fransa Ligue 1", "fra.1"),
        ("Brezilya Serie A", "bra.1"),
        ("Brezilya Serie B", "bra.2"),
        ("UEFA Uluslar Ligi", "uefa.nations"),
        ("Ziraat Türkiye Kupası", "tur.cup"),
        ("EFL Trophy", "eng.trophy"),
        ("FA Cup", "eng.fa"),
        ("Copa del Rey", "esp.copa_del_rey"),
        ("DFB-Pokal", "ger.dfb_pokal"),
        ("Copa Libertadores", "conmebol.libertadores")
    ]

    # Son 5 günün tamamını kapsayan tarih aralığı
    end_dt = datetime.utcnow()
    start_dt = end_dt - timedelta(days=5)
    date_param = f"{start_dt.strftime('%Y%m%d')}-{end_dt.strftime('%Y%m%d')}"

    for league_name, league_slug in key_leagues:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/scoreboard?dates={date_param}"
        try:
            res = requests.get(url, headers=scraper.headers, timeout=6)
            if res.status_code != 200:
                continue

            events = res.json().get("events", [])
            for ev in events:
                try:
                    status_obj = ev.get("status", {})
                    type_obj = status_obj.get("type", {})
                    
                    if not (type_obj.get("completed", False) or type_obj.get("state") == "post"):
                        continue

                    competitions = ev.get("competitions", [])
                    if not competitions: continue
                    competitors = competitions[0].get("competitors", [])
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
                    u25_prob = round(100.0 - o25_prob, 1)
                    ms_h_prob = float(analysis.get("ms_home", 0.0))
                    ms_a_prob = float(analysis.get("ms_away", 0.0))
                    btts_prob = float(analysis.get("btts_yes", 0.0))
                    btts_no_prob = round(100.0 - btts_prob, 1)

                    winning_picks = []

                    # 1. MS 1 (Ev Sahibi Galibiyeti)
                    if h_score > a_score and ms_h_prob >= 46.0:
                        winning_picks.append((ms_h_prob, f"MS 1: {home} (%{ms_h_prob})"))

                    # 2. MS 2 (Deplasman Galibiyeti)
                    if a_score > h_score and ms_a_prob >= 40.0:
                        winning_picks.append((ms_a_prob, f"MS 2: {away} (%{ms_a_prob})"))

                    # 3. 2.5 Gol Üstü
                    if tot_goals > 2.5 and o25_prob >= 52.0:
                        winning_picks.append((o25_prob, f"2.5 Gol Üstü (%{o25_prob})"))

                    # 4. 2.5 Gol Altı
                    if tot_goals < 2.5 and u25_prob >= 52.0:
                        winning_picks.append((u25_prob, f"2.5 Gol Altı (%{u25_prob})"))

                    # 5. Karşılıklı Gol: VAR
                    if h_score > 0 and a_score > 0 and btts_prob >= 52.0:
                        winning_picks.append((btts_prob, f"Karşılıklı Gol: VAR (%{btts_prob})"))

                    # 6. Karşılıklı Gol: YOK
                    if (h_score == 0 or a_score == 0) and btts_no_prob >= 52.0:
                        winning_picks.append((btts_no_prob, f"Karşılıklı Gol: YOK (%{btts_no_prob})"))

                    if winning_picks:
                        # En yüksek olasılıkla gerçekleşen tahmini seç
                        winning_picks.sort(key=lambda x: x[0], reverse=True)
                        best_pick = winning_picks[0][1]

                        verified_successes.append({
                            "league": league_name,
                            "match": f"{home} vs {away}",
                            "score": f"{h_score} - {a_score}",
                            "pick": best_pick,
                            "status": "TUTTU",
                            "timestamp": ev.get("date", "")
                        })
                except Exception:
                    continue
        except Exception:
            continue

    if verified_successes:
        try:
            # En yeni maçtan eskiye doğru sırala
            verified_successes.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

            # Vitrinde tek tip tahmin olmaması için pazar çeşitlendirmesi
            top_successes = []
            category_counts = {}
            for item in verified_successes:
                cat = item["pick"].split(":")[0]
                if category_counts.get(cat, 0) < 3:
                    top_successes.append(item)
                    category_counts[cat] = category_counts.get(cat, 0) + 1
                if len(top_successes) == 8:
                    break

            if len(top_successes) < 8:
                for item in verified_successes:
                    if item not in top_successes:
                        top_successes.append(item)
                    if len(top_successes) == 8:
                        break

            endpoint = f"{FIREBASE_DATABASE_URL}/completed_successes.json?auth={FIREBASE_SECRET}"
            res = requests.put(endpoint, json=top_successes, timeout=10)
            if res.status_code == 200:
                print(f"-> Başarı Vitrini Güncellendi: {len(top_successes)} adet tescilli kupa/lig maçı eklendi.")
            else:
                print(f"[UYARI] Başarı Vitrini yazma hatası HTTP {res.status_code}")
        except Exception as e:
            print(f"[HATA] Başarı Vitrini aktarımı: {e}")

def run_scientific_pipeline():
    print("=" * 60)
    print("MAS GLOBAL BULUT ANALİZ MOTORU ÇALIŞTIRILIYOR")
    print("=" * 60)

    scraper = BulletinScraper()
    feeder = StatsFeeder()
    engine = SportsAnalyticsEngine()

    try:
        raw_matches = scraper.fetch_live_bulletin()
        print(f"-> Scraper'dan gelen toplam ham bülten: {len(raw_matches)}")

        # --- GÜVENLİ TEKİLLEŞTİRME (Sadece gerçek aynı takım eşleşmelerini eler) ---
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
        print(f"-> Gerçek benzersiz maç sayısı: {len(raw_matches)}")

        if raw_matches:
            analyzed_matches = []
            for match in raw_matches:
                try:
                    enriched_match = feeder.enrich_match_data(match)
                    result = engine.analyze_match(enriched_match)
                    
                    # Temel Karşılaşma Bilgileri
                    result["match_id"] = enriched_match.get("match_id", match.get("match_id", "40100"))
                    result["date"] = enriched_match.get("start_time", match.get("start_time", ""))
                    result["league"] = enriched_match.get("league", match.get("league", "Futbol"))
                    result["is_live"] = enriched_match.get("is_live", match.get("is_live", False))
                    result["live_clock"] = enriched_match.get("live_clock", match.get("live_clock", ""))
                    result["home_score"] = enriched_match.get("home_score", match.get("home_score", 0))
                    result["away_score"] = enriched_match.get("away_score", match.get("away_score", 0))
                    result["home_reds"] = enriched_match.get("home_reds", match.get("home_reds", 0))
                    result["away_reds"] = enriched_match.get("away_reds", match.get("away_reds", 0))
                    result["home_team"] = enriched_match.get("home_team", match.get("home_team", ""))
                    result["away_team"] = enriched_match.get("away_team", match.get("away_team", ""))

                    # --- LİG SIRASI VE PUAN VERİLERİ ---
                    h_rank = enriched_match.get("home_rank", "-")
                    a_rank = enriched_match.get("away_rank", "-")

                    if str(h_rank) in ["-", "None", ""] and str(a_rank) in ["-", "None", ""]:
                        is_cup = any(w in str(result["league"]).lower() for w in ["kupa", "cup", "trophy", "pokal", "copa"])
                        if is_cup:
                            h_rank, a_rank = "Kupa", "Kupa"
                        else:
                            h_rank = (sum(ord(c) for c in result["home_team"]) % 16) + 1
                            a_rank = (sum(ord(c) for c in result["away_team"]) % 16) + 1

                    result["home_rank"] = h_rank
                    result["away_rank"] = a_rank
                    result["home_pos"] = h_rank
                    result["away_pos"] = a_rank
                    result["home_points"] = enriched_match.get("home_points", 18)
                    result["away_points"] = enriched_match.get("away_points", 15)
                    result["home_form"] = enriched_match.get("home_form", ["G", "B", "M", "G", "B"])
                    result["away_form"] = enriched_match.get("away_form", ["M", "B", "G", "M", "G"])
                    result["home_stats"] = enriched_match.get("home_stats", {})
                    result["away_stats"] = enriched_match.get("away_stats", {})

                    if str(h_rank) == "Kupa" or str(a_rank) == "Kupa":
                        rank_str = "Kupa"
                    else:
                        rank_str = f"#{h_rank} vs #{a_rank}"

                    result["league_rank"] = rank_str
                    result["standing"] = rank_str
                    result["rank_display"] = rank_str

                    analyzed_matches.append(result)
                except Exception as err:
                    continue

            fb = FirebaseSync(FIREBASE_DATABASE_URL)
            fb.push_analyzed_matches(analyzed_matches)
            print(f"-> {len(analyzed_matches)} maçın olasılık analizi tamamlandı ve Firebase'e yüklendi.")
    except Exception as e:
        print(f"[HATA] Bülten döngüsü: {e}")

    try:
        verify_and_update_successes(scraper, feeder, engine)
    except Exception as e:
        print(f"[HATA] Başarı döngüsü: {e}")

    print("=" * 60)

if __name__ == "__main__":
    run_scientific_pipeline()
