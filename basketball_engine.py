import math

class BasketballAnalyticsEngine:
    """
    Basketbol Karşılaşmaları için Sayı Beklentisi, Baremler ve Handikap Analiz Motoru.
    Model: Pace (Tempo) ve Offensive/Defensive Rating tabanlı Gauss/Normal Dağılım Simülasyonu.
    """

    def __init__(self):
        # Ortalama lig parametreleri
        self.default_pace = 72.5      # 40 dakikalık FIBA maçı için ortalama pozisyon sayısı (NBA için ~98)
        self.default_efficiency = 1.08 # Pozisyon başına sayı üretimi (Offensive Rating)
        self.default_points_std = 11.5 # Sayı standart sapması

    def _normal_cdf(self, x, mean, std):
        """Kümülatif normal dağılım olasılığı (Gauss CDF)"""
        return 0.5 * (1.0 + math.erf((x - mean) / (std * math.sqrt(2.0))))

    def analyze_match(self, match_data):
        home_team = match_data.get("home_team", "Ev Sahibi")
        away_team = match_data.get("away_team", "Deplasman")
        league = match_data.get("league", "Basketbol")

        # NBA ise süre 48 dakika, FIBA/EuroLeague ise 40 dakika
        is_nba = "nba" in league.lower()
        base_pace = 98.5 if is_nba else 73.0
        base_std = 14.0 if is_nba else 11.2

        # Takım tempo ve verimlilikleri (Feeder'dan gelmezse dinamik varyans atanır)
        h_pace = float(match_data.get("home_pace", base_pace))
        a_pace = float(match_data.get("away_pace", base_pace))
        match_pace = (h_pace + a_pace) / 2.0

        h_ortg = float(match_data.get("home_ortg", 1.10))
        a_ortg = float(match_data.get("away_ortg", 1.05))
        h_drtg = float(match_data.get("home_drtg", 1.04))
        a_drtg = float(match_data.get("away_drtg", 1.09))

        # Ev sahibi avantajı (~3.2 sayı katkısı)
        home_court_boost = 1.025

        # Beklenen Sayılar (Expected Points)
        expected_home_pts = round(match_pace * ((h_ortg + a_drtg) / 2.0) * home_court_boost, 1)
        expected_away_pts = round(match_pace * ((a_ortg + h_drtg) / 2.0), 1)
        total_expected_pts = round(expected_home_pts + expected_away_pts, 1)
        point_diff = round(expected_home_pts - expected_away_pts, 1)

        # Referans İddaa Toplam Sayı Baremi
        ref_line = float(match_data.get("total_line", round(total_expected_pts * 2) / 2))

        # Alt / Üst Olasılıkları
        over_prob = round((1.0 - self._normal_cdf(ref_line, total_expected_pts, base_std)) * 100, 1)
        under_prob = round(100.0 - over_prob, 1)

        # Maç Sonu Galibiyet Olasılıkları
        home_win_prob = round(self._normal_cdf(point_diff, 0, base_std * 1.25) * 100, 1)
        away_win_prob = round(100.0 - home_win_prob, 1)

        # İlk Yarı (İY) Beklentisi (Toplam sayının ~%49'u)
        iy_expected_total = round(total_expected_pts * 0.49, 1)
        iy_line = round(ref_line * 0.49 * 2) / 2
        iy_over_prob = round((1.0 - self._normal_cdf(iy_line, iy_expected_total, base_std * 0.72)) * 100, 1)
        iy_under_prob = round(100.0 - iy_over_prob, 1)

        # En Güçlü İddaa Tercihi & Güven Skoru
        picks = []
        if over_prob >= 58.0:
            picks.append((over_prob, f"{ref_line} ÜST (%{over_prob})"))
        elif under_prob >= 58.0:
            picks.append((under_prob, f"{ref_line} ALT (%{under_prob})"))

        if home_win_prob >= 64.0:
            picks.append((home_win_prob, f"MS 1: {home_team} (%{home_win_prob})"))
        elif away_win_prob >= 64.0:
            picks.append((away_win_prob, f"MS 2: {away_team} (%{away_win_prob})"))

        if picks:
            picks.sort(key=lambda x: x[0], reverse=True)
            strongest_pick = picks[0][1]
            confidence_score = int(picks[0][0])
        else:
            strongest_pick = f"{ref_line} ÜST (%{over_prob})"
            confidence_score = 65

        return {
            "match": f"{home_team} vs {away_team}",
            "home_team": home_team,
            "away_team": away_team,
            "league": league,
            "sport": "basketball",
            "strongest_pick": strongest_pick,
            "confidence_score": confidence_score,
            "analysis": {
                "expected_home_pts": expected_home_pts,
                "expected_away_pts": expected_away_pts,
                "total_expected_pts": total_expected_pts,
                "point_diff": point_diff,
                "total_line": ref_line,
                "over_prob": over_prob,
                "under_prob": under_prob,
                "ms_home": home_win_prob,
                "ms_away": away_win_prob,
                "iy_line": iy_line,
                "iy_over": iy_over_prob,
                "iy_under": iy_under_prob
            }
        }