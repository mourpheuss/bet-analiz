import requests
from datetime import datetime, timedelta
from engine import SportsAnalyticsEngine
from stats_feeder import StatsFeeder

FIREBASE_DATABASE_URL = "https://analizsepeti-f3bb5-default-rtdb.firebaseio.com"
FIREBASE_SECRET = "mZUATfv3TJqO6Ap8d1asrXemQIYqJflfYLzprmBS"

class MASBacktester:
    """
    Oynanmış ve bitmiş yüzlerce maçı ESPN üzerinden tarayarak
    Dixon-Coles modelini, isabet oranını ve 100 Birim Kasa Getirisini test eder.
    """

    def __init__(self, days_back=14):
        self.days_back = days_back
        self.engine = SportsAnalyticsEngine()
        self.feeder = StatsFeeder()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        self.test_leagues = [
            ("Premier League", "eng.1"),
            ("La Liga", "esp.1"),
            ("Serie A", "ita.1"),
            ("Bundesliga", "ger.1"),
            ("Trendyol Süper Lig", "tur.1"),
            ("Fransa Ligue 1", "fra.1"),
            ("Hollanda Eredivisie", "ned.1")
        ]

    def run_simulation(self):
        print("=" * 65)
        print(f"MAS PRO // GERİYE DÖNÜK TEST (BACKTEST) BAŞLATILDI (Son {self.days_back} Gün)")
        print("=" * 65)

        total_bets, won_bets, lost_bets = 0, 0, 0
        market_stats = {
            "1.5 ÜST": {"total": 0, "won": 0, "profit": 0.0},
            "2.5 ÜST": {"total": 0, "won": 0, "profit": 0.0},
            "2.5 ALT": {"total": 0, "won": 0, "profit": 0.0},
            "KG VAR": {"total": 0, "won": 0, "profit": 0.0},
            "İY 0.5 ÜST": {"total": 0, "won": 0, "profit": 0.0},
            "MS 1": {"total": 0, "won": 0, "profit": 0.0},
            "1X ÇŞ": {"total": 0, "won": 0, "profit": 0.0}
        }

        bankroll = 100.0
        stake = 1.0

        now_dt = datetime.utcnow()
        dates = [(now_dt - timedelta(days=i)).strftime("%Y%m%d") for i in range(1, self.days_back + 1)]

        for l_name, l_slug in self.test_leagues:
            print(f"-> Lig Taranıyor: {l_name}...")
            for d_str in dates:
                url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{l_slug}/scoreboard?dates={d_str}"
                try:
                    res = requests.get(url, headers=self.headers, timeout=5)
                    if res.status_code != 200: continue
                    events = res.json().get("events", [])
                    for ev in events:
                        status_obj = ev.get("status", {})
                        type_obj = status_obj.get("type", {})
                        if not (type_obj.get("completed", False) or type_obj.get("state") == "post"):
                            continue

                        comps = ev.get("competitions", [{}])[0]
                        competitors = comps.get("competitors", [])
                        if len(competitors) < 2: continue

                        home_c = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                        away_c = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

                        home_team = home_c.get("team", {}).get("displayName", "")
                        away_team = away_c.get("team", {}).get("displayName", "")
                        if not home_team or not away_team: continue

                        h_score = int(home_c.get("score") or 0)
                        a_score = int(away_c.get("score") or 0)
                        tot_goals = h_score + a_score

                        # İlk yarı golü kontrolü (Linescores üzerinden)
                        h_lines = home_c.get("linescores", [])
                        a_lines = away_c.get("linescores", [])
                        if len(h_lines) > 0 and len(a_lines) > 0:
                            iy_goals = int(h_lines[0].get("value") or 0) + int(a_lines[0].get("value") or 0)
                        else:
                            iy_goals = 1 if tot_goals > 0 else 0

                        raw_match = {
                            "league": l_name,
                            "home_team": home_team,
                            "away_team": away_team,
                            "home_reds": 0,
                            "away_reds": 0,
                            "is_live": False
                        }

                        enriched = self.feeder.enrich_match_data(raw_match)
                        res_engine = self.engine.analyze_match(enriched)
                        analysis = res_engine.get("analysis", {})

                        o15_pct = analysis.get("over_15", 0.0)
                        o25_pct = analysis.get("over_25", 0.0)
                        u25_pct = analysis.get("under_25", 0.0)
                        btts_pct = analysis.get("btts_yes", 0.0)
                        ms_h_pct = analysis.get("ms_home", 0.0)
                        cs_1x_pct = analysis.get("cs_1x", 0.0)
                        iy_o05_pct = analysis.get("iy_over_05", 0.0)

                        signals = []
                        # Modelin yüksek güvenle ürettiği sinyaller ve piyasa medyan oranları:
                        if o15_pct >= 76.0:
                            signals.append(("1.5 ÜST", tot_goals > 1.5, 1.34))
                        if o25_pct >= 57.0:
                            signals.append(("2.5 ÜST", tot_goals > 2.5, 1.84))
                        elif u25_pct >= 58.0:
                            signals.append(("2.5 ALT", tot_goals < 2.5, 1.80))
                        if btts_pct >= 56.0:
                            signals.append(("KG VAR", (h_score > 0 and a_score > 0), 1.76))
                        if iy_o05_pct >= 71.0:
                            signals.append(("İY 0.5 ÜST", iy_goals > 0, 1.38))
                        if ms_h_pct >= 64.0:
                            signals.append(("MS 1", h_score > a_score, 1.62))
                        if cs_1x_pct >= 74.0:
                            signals.append(("1X ÇŞ", h_score >= a_score, 1.32))

                        for pick_name, is_won, avg_odd in signals:
                            total_bets += 1
                            market_stats[pick_name]["total"] += 1
                            if is_won:
                                won_bets += 1
                                market_stats[pick_name]["won"] += 1
                                profit = (stake * avg_odd) - stake
                                market_stats[pick_name]["profit"] += profit
                                bankroll += profit
                            else:
                                lost_bets += 1
                                market_stats[pick_name]["profit"] -= stake
                                bankroll -= stake
                except Exception:
                    continue

        win_rate = round((won_bets / total_bets * 100), 1) if total_bets > 0 else 0
        net_profit = round(bankroll - 100.0, 2)
        roi = round((net_profit / total_bets * 100), 1) if total_bets > 0 else 0

        print("\n" + "=" * 65)
        print("SIMÜLASYON RAPORU (HAKİKİ PERFORMANS)")
        print("=" * 65)
        print(f"Toplam Oynanan Bahis : {total_bets}")
        print(f"Tutan Bahis (Win)     : {won_bets} (%{win_rate})")
        print(f"Yatan Bahis (Loss)    : {lost_bets}")
        print(f"Başlangıç Kasası      : 100.0 Birim")
        print(f"Bitiş Kasası          : {round(bankroll, 2)} Birim")
        print(f"Net Kâr / Zarar       : {net_profit:+} Birim (ROI: %{roi})")
        print("-" * 65)
        print(f"{'Piyasa / Tercih':<14} | {'Bahis':<6} | {'İsabet %':<9} | {'Net Kâr (Birim)'}")
        print("-" * 65)
        for m, d in market_stats.items():
            if d["total"] > 0:
                p_rate = round((d["won"] / d["total"] * 100), 1)
                p_profit = round(d["profit"], 2)
                print(f"{m:<14} | {d['total']:<6} | %{p_rate:<8} | {p_profit:+} Birim")
        print("=" * 65)

        # Firebase'e Raporu Yükle
        payload = {
            "updated_at": (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M TSİ"),
            "total_bets": total_bets,
            "won_bets": won_bets,
            "lost_bets": lost_bets,
            "win_rate": win_rate,
            "bankroll": round(bankroll, 2),
            "net_profit": net_profit,
            "roi": roi,
            "markets": market_stats
        }

        try:
            url = f"{FIREBASE_DATABASE_URL}/backtest_results.json?auth={FIREBASE_SECRET}"
            requests.put(url, json=payload, timeout=10)
            print("-> [BAŞARILI] Backtest sonuçları Firebase'e yüklendi!")
        except Exception as e:
            print(f"[HATA] Firebase yüklenemedi: {e}")

if __name__ == "__main__":
    tester = MASBacktester(days_back=14)
    tester.run_simulation()
