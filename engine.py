import math
import re

class SportsAnalyticsEngine:
    def __init__(self, rho=-0.13):
        # Dixon-Coles düşük skor korelasyon sabiti
        self.rho = rho

        # Global Liglerin Gerçek Karakteristik Gol Ortalamaları (Ev Sahibi xG, Deplasman xG)
        self.league_baselines = {
            # TÜRKİYE
            "Trendyol Süper Lig": (1.52, 1.18),
            "Trendyol 1. Lig": (1.38, 1.05),
            "Ziraat Türkiye Kupası": (1.65, 1.25),

            # İNGİLTERE
            "Premier League": (1.65, 1.28),
            "İngiltere Championship": (1.42, 1.16),
            "İngiltere League One": (1.44, 1.18),
            "İngiltere League Two": (1.40, 1.15),
            "FA Cup": (1.60, 1.25),
            "EFL Carabao Cup": (1.58, 1.22),
            "EFL Trophy": (1.62, 1.30),

            # İSPANYA
            "La Liga": (1.46, 1.10),
            "La Liga 2": (1.20, 0.85),
            "Copa del Rey": (1.55, 1.15),

            # İTALYA
            "Serie A": (1.48, 1.14),
            "Serie B": (1.26, 0.94),
            "Coppa Italia": (1.55, 1.15),

            # ALMANYA
            "Bundesliga": (1.78, 1.36),
            "Bundesliga 2": (1.66, 1.32),
            "DFB-Pokal": (1.85, 1.35),

            # FRANSA
            "Fransa Ligue 1": (1.48, 1.16),
            "Fransa Ligue 2": (1.24, 0.92),
            "Coupe de France": (1.58, 1.18),

            # HOLLANDA & DİĞER AVRUPA
            "Hollanda Eredivisie": (1.82, 1.38),
            "Hollanda KNVB Beker": (1.85, 1.40),
            "Portekiz Liga NOS": (1.45, 1.08),
            "Portekiz Taça de Portugal": (1.52, 1.12),
            "Belçika Pro League": (1.60, 1.28),
            "Belçika Kupası": (1.65, 1.30),
            "İskoçya Premiership": (1.50, 1.15),
            "Avusturya Bundesliga": (1.62, 1.28),
            "İsviçre Süper Ligi": (1.68, 1.34),
            "Danimarka Superliga": (1.54, 1.22),
            "Yunanistan Süper Ligi": (1.38, 0.95),

            # UEFA & ULUSLARARASI
            "UEFA Şampiyonlar Ligi": (1.68, 1.26),
            "UEFA Avrupa Ligi": (1.62, 1.24),
            "UEFA Konferans Ligi": (1.60, 1.22),
            "UEFA Uluslar Ligi": (1.45, 1.10),
            "Dünya Kupası Elemeleri (Avrupa)": (1.65, 1.15),
            "Dünya Kupası Elemeleri (G.Amerika)": (1.35, 0.92),

            # GÜNEY AMERİKA & DÜNYA (Genelde Düşük Skor Karakterli)
            "Brezilya Serie A": (1.38, 0.98),
            "Brezilya Serie B": (1.22, 0.86),
            "Copa do Brasil": (1.42, 1.00),
            "Arjantin Liga Profesional": (1.18, 0.84),
            "Copa Argentina": (1.22, 0.88),
            "Copa Libertadores": (1.45, 0.95),
            "Copa Sudamericana": (1.42, 0.92),
            "Meksika Liga MX": (1.55, 1.18),
            "ABD MLS": (1.68, 1.30),
            "Suudi Arabistan Pro Lig": (1.64, 1.28),
            "Japonya J1 League": (1.42, 1.12)
        }

        # Global Elit / Güçlü Kulüpler (Ekstra Güç Çarpanı Alırlar)
        self.tier1_clubs = {
            "Real Madrid", "Barcelona", "Manchester City", "Arsenal", "Liverpool", 
            "Bayern Munich", "Bayer Leverkusen", "Paris Saint-Germain", "Inter Milan", 
            "Juventus", "Galatasaray", "Fenerbahçe", "Benfica", "Sporting CP", "Porto",
            "Flamengo", "Palmeiras", "Atlético Mineiro", "River Plate", "Boca Juniors",
            "Al Hilal", "Al Nassr"
        }

    def _poisson(self, k, lamb):
        try:
            if lamb <= 0:
                return 1.0 if k == 0 else 0.0
            return (math.exp(-lamb) * (lamb ** k)) / math.factorial(k)
        except Exception:
            return 0.0

    def _dixon_coles_tau(self, x, y, lambda_h, mu_a):
        try:
            if x == 0 and y == 0: val = 1.0 - (lambda_h * mu_a * self.rho)
            elif x == 0 and y == 1: val = 1.0 + (lambda_h * self.rho)
            elif x == 1 and y == 0: val = 1.0 + (mu_a * self.rho)
            elif x == 1 and y == 1: val = 1.0 - self.rho
            else: val = 1.0
            return max(0.01, val) # Negatif olasılık koruması
        except Exception:
            return 1.0

    def _parse_minute(self, clock_str):
        if not clock_str: return 0
        m = re.search(r'\d+', str(clock_str))
        return int(m.group()) if m else 0

    def _estimate_team_powers(self, home_team, away_team, league_name):
        base_h, base_a = self.league_baselines.get(league_name, (1.50, 1.15))
        h_mult, a_mult = 1.0, 1.0

        # Elit Kulüp Teşhisi
        if any(c.lower() in home_team.lower() for c in self.tier1_clubs):
            h_mult += 0.28
            a_mult -= 0.15

        if any(c.lower() in away_team.lower() for c in self.tier1_clubs):
            a_mult += 0.28
            h_mult -= 0.15

        h_xg = max(0.35, base_h * h_mult)
        a_xg = max(0.25, base_a * a_mult)
        return h_xg, a_xg

    def analyze_match(self, match_data):
        home_team = match_data.get("home_team") or "Ev Sahibi"
        away_team = match_data.get("away_team") or "Deplasman"
        league_name = match_data.get("league") or ""
        
        is_live = match_data.get("is_live", False)
        live_clock = match_data.get("live_clock", "0'")
        
        try: cur_h = int(match_data.get("home_score") or 0)
        except: cur_h = 0

        try: cur_a = int(match_data.get("away_score") or 0)
        except: cur_a = 0

        try: h_reds = int(match_data.get("home_reds") or 0)
        except: h_reds = 0

        try: a_reds = int(match_data.get("away_reds") or 0)
        except: a_reds = 0

        # Lig bazlı ve takım güçlerine göre dinamik xG hesabı
        h_xg, a_xg = self._estimate_team_powers(home_team, away_team, league_name)

        # CANLI MAÇ KALİBRASYONU (Zaman Sönümlemesi ve Kırmızı Kart)
        if is_live:
            minute = self._parse_minute(live_clock)
            rem_ratio = max(0.04, (95 - minute) / 90.0)
            if h_reds > 0:
                h_xg *= (0.65 ** h_reds)
                a_xg *= (1.30 ** h_reds)
            if a_reds > 0:
                a_xg *= (0.65 ** a_reds)
                h_xg *= (1.30 ** a_reds)
            rem_h_xg = h_xg * rem_ratio
            rem_a_xg = a_xg * rem_ratio
        else:
            rem_h_xg = h_xg
            rem_a_xg = a_xg

        # Devre Beklentileri
        h_1h, a_1h = rem_h_xg * 0.45, rem_a_xg * 0.45
        h_2h, a_2h = rem_h_xg * 0.55, rem_a_xg * 0.55

        ms_h, ms_d, ms_a = 0.0, 0.0, 0.0
        o15, o25, o35 = 0.0, 0.0, 0.0
        btts_yes = 0.0
        matrix = []

        # TAM 49 MATRİS DÖNGÜSÜ (0'dan 6'ya: 7x7 = 49 Skor)
        for gh in range(7):
            for ga in range(7):
                p = self._poisson(gh, rem_h_xg) * self._poisson(ga, rem_a_xg) * self._dixon_coles_tau(gh, ga, rem_h_xg, rem_a_xg)
                final_h = cur_h + gh
                final_a = cur_a + ga

                if final_h > final_a: ms_h += p
                elif final_h == final_a: ms_d += p
                else: ms_a += p

                tg = final_h + final_a
                if tg > 1.5: o15 += p
                if tg > 2.5: o25 += p
                if tg > 3.5: o35 += p
                if final_h > 0 and final_a > 0: btts_yes += p

                matrix.append((f"{final_h}-{final_a}", p))

        # 1. Yarı Olasılıkları
        iy_h, iy_d, iy_a = 0.0, 0.0, 0.0
        for h in range(5):
            for a in range(5):
                p = self._poisson(h, h_1h) * self._poisson(a, a_1h)
                if h > a: iy_h += p
                elif h == a: iy_d += p
                else: iy_a += p

        # 2. Yarı Gerçek Poisson Olasılıkları
        y2_h, y2_d, y2_a = 0.0, 0.0, 0.0
        for h in range(5):
            for a in range(5):
                p = self._poisson(h, h_2h) * self._poisson(a, a_2h)
                if h > a: y2_h += p
                elif h == a: y2_d += p
                else: y2_a += p

        tot_ms = max(0.0001, ms_h + ms_d + ms_a)
        tot_iy = max(0.0001, iy_h + iy_d + iy_a)
        tot_y2 = max(0.0001, y2_h + y2_d + y2_a)

        p_home = round((ms_h / tot_ms) * 100, 1)
        p_draw = round((ms_d / tot_ms) * 100, 1)
        p_away = round((ms_a / tot_ms) * 100, 1)

        volatility_warning = None
        if h_reds > 0 or a_reds > 0:
            red_team = home_team if h_reds > 0 else away_team
            volatility_warning = f"⚠️ KIRMIZI KART: {red_team} sahada eksik! Canlı olasılıklar 10 kişiye göre hesaplandı."
        elif abs(p_home - p_away) < 7.0:
            volatility_warning = "YÜKSEK VOLATİLİTE: İki takımın kazanma ihtimali birbirine çok yakın. Modelimiz taraf tercihi yerine Gol / Devre seçeneklerine odaklanmanızı önerir."

        matrix.sort(key=lambda x: x[1], reverse=True)
        top_scores = [
            {"score": s[0], "prob": f"%{round((s[1]/tot_ms)*100, 1)}"}
            for s in matrix[:3]
        ]

        return {
            "match": f"{home_team} vs {away_team}",
            "home_team": home_team,
            "away_team": away_team,
            "is_live": is_live,
            "live_clock": live_clock,
            "live_score": f"{cur_h} - {cur_a}" if is_live else "",
            "home_reds": h_reds,
            "away_reds": a_reds,
            "volatility_warning": volatility_warning,
            "analysis": {
                "ms_home": p_home,
                "ms_draw": p_draw,
                "ms_away": p_away,
                "iy_home": round((iy_h / tot_iy) * 100, 1),
                "iy_draw": round((iy_d / tot_iy) * 100, 1),
                "iy_away": round((iy_a / tot_iy) * 100, 1),
                "y2_home": round((y2_h / tot_y2) * 100, 1),
                "y2_draw": round((y2_d / tot_y2) * 100, 1),
                "y2_away": round((y2_a / tot_y2) * 100, 1),
                "over_15": round((o15 / tot_ms) * 100, 1),
                "over_25": round((o25 / tot_ms) * 100, 1),
                "over_35": round((o35 / tot_ms) * 100, 1),
                "btts_yes": round((btts_yes / tot_ms) * 100, 1),
                "btts_no": round((1.0 - (btts_yes / tot_ms)) * 100, 1)
            },
            "top_scores": top_scores,
            "team_details": {
                "home_rank": "-",
                "away_rank": "-",
                "home_points": "-",
                "away_points": "-",
                "home_form": ["G", "B", "G", "M", "G"],
                "away_form": ["M", "B", "G", "M", "B"]
            }
        }
