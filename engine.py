import math
import re

class SportsAnalyticsEngine:
    def __init__(self, rho=-0.13):
        self.rho = rho

    def _poisson(self, k, lamb):
        try:
            if lamb <= 0:
                return 1.0 if k == 0 else 0.0
            return (math.exp(-lamb) * (lamb ** k)) / math.factorial(k)
        except Exception:
            return 0.0

    def _dixon_coles_tau(self, x, y, lambda_h, mu_a):
        try:
            if x == 0 and y == 0: return 1.0 - (lambda_h * mu_a * self.rho)
            elif x == 0 and y == 1: return 1.0 + (lambda_h * self.rho)
            elif x == 1 and y == 0: return 1.0 + (mu_a * self.rho)
            elif x == 1 and y == 1: return 1.0 - self.rho
            return 1.0
        except Exception:
            return 1.0

    def _parse_minute(self, clock_str):
        if not clock_str: return 0
        m = re.search(r'\d+', str(clock_str))
        return int(m.group()) if m else 0

    def analyze_match(self, match_data):
        home_team = match_data.get("home_team") or "Ev Sahibi"
        away_team = match_data.get("away_team") or "Deplasman"
        
        h_stats = match_data.get("home_stats") or {}
        a_stats = match_data.get("away_stats") or {}

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

        try:
            h_xg_val = h_stats.get("calc_xg")
            h_xg = max(0.45, float(h_xg_val if h_xg_val is not None else 1.55))
        except (ValueError, TypeError):
            h_xg = 1.55

        try:
            a_xg_val = a_stats.get("calc_xg")
            a_xg = max(0.35, float(a_xg_val if a_xg_val is not None else 1.15))
        except (ValueError, TypeError):
            a_xg = 1.15

        # CANLI MAÇ KALİBRASYONU
        if is_live:
            minute = self._parse_minute(live_clock)
            rem_ratio = max(0.05, (95 - minute) / 90.0)
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

        h_1h, a_1h = rem_h_xg * 0.44, rem_a_xg * 0.44
        h_2h, a_2h = rem_h_xg * 0.56, rem_a_xg * 0.56

        ms_h, ms_d, ms_a = 0.0, 0.0, 0.0
        o15, o25, o35 = 0.0, 0.0, 0.0
        btts_yes = 0.0
        matrix = []

        for gh in range(6):
            for ga in range(6):
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

        # Devre Dağılımları
        iy_h, iy_d, iy_a = 0.0, 0.0, 0.0
        for h in range(5):
            for a in range(5):
                p = self._poisson(h, h_1h) * self._poisson(a, a_1h)
                if h > a: iy_h += p
                elif h == a: iy_d += p
                else: iy_a += p

        tot_ms = max(0.0001, ms_h + ms_d + ms_a)
        tot_iy = max(0.0001, iy_h + iy_d + iy_a)

        p_home = round((ms_h / tot_ms) * 100, 1)
        p_draw = round((ms_d / tot_ms) * 100, 1)
        p_away = round((ms_a / tot_ms) * 100, 1)

        volatility_warning = None
        if h_reds > 0 or a_reds > 0:
            red_team = home_team if h_reds > 0 else away_team
            volatility_warning = f"⚠️ KIRMIZI KART: {red_team} sahada eksik! Canlı olasılıklar 10 kişiye göre hesaplandı."
        elif abs(p_home - p_away) < 7.5:
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
                "y2_home": round((p_home * 0.8), 1),
                "y2_draw": round(p_draw, 1),
                "y2_away": round((p_away * 0.8), 1),
                "over_15": round((o15 / tot_ms) * 100, 1),
                "over_25": round((o25 / tot_ms) * 100, 1),
                "over_35": round((o35 / tot_ms) * 100, 1),
                "btts_yes": round((btts_yes / tot_ms) * 100, 1),
                "btts_no": round((1.0 - (btts_yes / tot_ms)) * 100, 1)
            },
            "top_scores": top_scores,
            "team_details": {
                "home_rank": h_stats.get("rank", "-"),
                "away_rank": a_stats.get("rank", "-"),
                "home_points": h_stats.get("points", "-"),
                "away_points": a_stats.get("points", "-"),
                "home_form": h_stats.get("form") or ["G", "B", "G", "M", "G"],
                "away_form": a_stats.get("form") or ["M", "B", "G", "M", "B"]
            }
        }