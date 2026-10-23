import requests
from datetime import datetime, timedelta
from engine import SportsAnalyticsEngine
from stats_feeder import StatsFeeder

class MASBacktester:
    """
    Geçmişte oynanmış ve bitmiş maçları ESPN üzerinden çekerek
    Dixon-Coles modelini, isabet oranını (Win Rate) ve 100 Birim Kasa Getirisini (ROI) test eder.
    """

    def __init__(self, days_back=14):
        self.days_back = days_back
        self.engine = SportsAnalyticsEngine()
        self.feeder = StatsFeeder()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        # Test edilecek majör ligler (Hızlı ve güvenilir veri için)
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
        print(f"MAS PRO - GERİYE DÖNÜK TEST (BACKTEST) BAŞLATILIYOR (Son {self.days_back} Gün)")
        print("=" * 65)

        total_bets = 0
        won_bets = 0
        lost_bets = 0
        
        market_stats = {
            "2.5 ÜST": {"total": 0, "won": 0, "profit": 0.0},
            "2.5 ALT": {"total": 0, "won": 0, "profit": 0.0},
            "KG VAR": {"total": 0, "won": 0, "profit": 0.0},
            "MS 1": {"total": 0, "won": 0, "profit": 0.0},
            "MS 2": {"total": 0, "won": 0, "profit": 0.0},
            "İY 0.5 ÜST": {"total": 0, "won": 0, "profit": 0.0}
        }

        bankroll = 100.0  # 100 Birim Kasa
        stake = 1.0       # Her maça sabit 1 birim

        now_dt = datetime.utcnow()
        dates = [(now_dt - timedelta(days=i)).strftime("%Y%m%d") for i in range(1, self.days_back + 1)]

        for l_name, l_slug in self.test_leagues:
            print(f"-> Taranıyor: {l_name}...")
            for d_str in dates:
                url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{l_slug}/scoreboard?dates={d_str}"
                try:
                    res = requests.get(url, headers=self.headers, timeout=5)
                    if res.status_code != 200:
                        continue
                    
                    events = res.json().get("events", [])
                    for ev in events:
                        status_obj = ev.get("status", {})
                        type_obj = status_obj.get("type", {})
                        if not (type_obj.get("completed", False) or type_obj.get("state") == "post"):
                            continue

                        comp = ev.get("competitions", [{}])[0]
                        competitors = comp.get("competitors", [])
                        if len(competitors) < 2: continue

                        home_c = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                        away_c = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

                        home_team = home_c.get("team", {}).get("displayName", "")
                        away_team = away_c.get("team", {}).get("displayName", "")
                        h_score = int(home_c.get("score") or 0)
                        a_score = int(away_c.get("score") or 0)

                        # Modele maçı skorlar oynanmadan önceki haliyle soruyoruz
                        raw_match = {
                            "league": l_name,
                            "home_team": home_team,
                            "away_team": away_team,
                            "home_reds": 0,
                            "away_reds": 0,
                            "is_live": False
                        }

                        enriched = self.feeder.enrich_match_data(raw_match)
                        analysis = self.engine.analyze_match(enriched)
                        
                        a_data = analysis.get("analysis", {})
                        o25_pct = a_data.get("over_25", 0.0)
                        btts_pct = a_data.get("btts_yes", 0.0)
                        ms_h_pct = a_data.get("ms_home", 0.0)
                        ms_a_pct = a_data.get("ms_away", 0.0)
                        iy_o05_pct = a_data.get("iy_over_05", 0.0)

                        tot_goals = h_score + a_score

                        # Test edilecek model sinyalleri ve ortalama piyasa oranları
                        signals = []
                        if o25_pct >= 58.0:
                            signals.append(("2.5 ÜST", tot_goals > 2.5, 1.82))
                        elif (100.0 - o25_pct) >= 60.0:
                            signals.append(("2.5 ALT", tot_goals < 2.5, 1.78))

                        if btts_pct >= 58.0:
                            signals.append(("KG VAR", (h_score > 0 and a_score > 0), 1.74))

                        if ms_h_pct >= 62.0:
                            signals.append(("MS 1", h_score > a_score, 1.65))
                        elif ms_a_pct >= 52.0:
                            signals.append(("MS 2", a_score > h_score, 2.10))

                        if iy_o05_pct >= 75.0:
                            signals.append(("İY 0.5 ÜST", tot_goals >= 1, 1.36))

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

        self._print_results(total_bets, won_bets, lost_bets, bankroll, market_stats)

    def _print_results(self, total, won, lost, bankroll, stats):
        win_rate = round((won / total * 100), 1) if total > 0 else 0
        net_profit = round(bankroll - 100.0, 2)
        roi = round((net_profit / total * 100), 1) if total > 0 else 0

        print("\n" + "=" * 65)
        print("SIMÜLASYON RAPORU (HAKİKİ PERFORMANS)")
        print("=" * 65)
        print(f"Toplam Oynanan Bahis : {total}")
        print(f"Tutan Bahis (Win)     : {won} (%{win_rate})")
        print(f"Yatan Bahis (Loss)    : {lost}")
        print(f"Başlangıç Kasası      : 100.0 Birim")
        print(f"Bitiş Kasası          : {round(bankroll, 2)} Birim")
        print(f"Net Kâr / Zarar       : {net_profit} Birim (ROI: %{roi})")
        print("-" * 65)
        print(f"{'Piyasa / Tercih':<14} | {'Bahis':<6} | {'İsabet %':<9} | {'Net Kâr (Birim)'}")
        print("-" * 65)
        for m, d in stats.items():
            if d["total"] > 0:
                p_rate = round((d["won"] / d["total"] * 100), 1)
                p_profit = round(d["profit"], 2)
                print(f"{m:<14} | {d['total']:<6} | %{p_rate:<8} | {p_profit:+} Birim")
        print("=" * 65)

if __name__ == "__main__":
    tester = MASBacktester(days_back=14)
    tester.run_simulation()
