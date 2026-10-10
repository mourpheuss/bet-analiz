import math

class SportsAnalyticsEngine:
    def __init__(self):
        # Dixon-Coles düşük skor bağımlılık parametresi (Dünya futbolu medyan değeri)
        self.rho = -0.11
        # Yarı gol dağılım katsayıları
        self.first_half_ratio = 0.44
        self.second_half_ratio = 0.56

    def _poisson_pmf(self, k, lambd):
        """Temel Poisson Olasılık Kütle Fonksiyonu: P(X=k) = (lambda^k * e^-lambda) / k!"""
        if lambd <= 0:
            return 1.0 if k == 0 else 0.0
        return (math.pow(lambd, k) * math.exp(-lambd)) / math.factorial(k)

    def _dixon_coles_tau(self, x, y, lambda_val, mu_val):
        """
        Dixon & Coles (1997) Düşük Skor Düzeltme Matrisi
        0-0, 1-0, 0-1 ve 1-1 skorlarının gerçek dünya korelasyonunu ayarlar.
        """
        if x == 0 and y == 0:
            return max(0.0, 1.0 - (lambda_val * mu_val * self.rho))
        elif x == 0 and y == 1:
            return max(0.0, 1.0 + (lambda_val * self.rho))
        elif x == 1 and y == 0:
            return max(0.0, 1.0 + (mu_val * self.rho))
        elif x == 1 and y == 1:
            return max(0.0, 1.0 - self.rho)
        else:
            return 1.0

    def _build_dixon_coles_matrix(self, lambda_home, lambda_away, max_goals=7):
        """
        Ev sahibi ve Deplasman için ortak Dixon-Coles olasılık matrisini kurar.
        """
        matrix = [[0.0 for _ in range(max_goals + 1)] for _ in range(max_goals + 1)]
        total_prob = 0.0

        for h in range(max_goals + 1):
            p_h = self._poisson_pmf(h, lambda_home)
            for a in range(max_goals + 1):
                p_a = self._poisson_pmf(a, lambda_away)
                tau = self._dixon_coles_tau(h, a, lambda_home, lambda_away)
                
                cell_prob = p_h * p_a * tau
                matrix[h][a] = cell_prob
                total_prob += cell_prob

        # Matrisi %100'e normalize et (kesme payı düzeltmesi)
        if total_prob > 0:
            for h in range(max_goals + 1):
                for a in range(max_goals + 1):
                    matrix[h][a] /= total_prob

        return matrix

    def _calculate_confidence_score(self, ms_h, ms_x, ms_a, total_xg):
        """
        Model Entropisi ve Olasılık Keskinliği Analizi (0 - 100 arası Güven Skoru)
        """
        # En yüksek ihtimalin büyüklüğü (Dağılım ne kadar tek bir tarafa meylediyorsa güven o kadar yüksektir)
        max_outcome = max(ms_h, ms_x, ms_a)
        
        # 33-33-33 gibi yazı-tura benzeri maçlarda güveni düşürür
        edge_score = (max_outcome - 33.3) * 2.1
        
        # Çok aşırı xG uç değerlerine karşı filtre
        xg_penalty = 0.0
        if total_xg < 1.2 or total_xg > 4.2:
            xg_penalty = 8.0

        raw_conf = 50.0 + edge_score - xg_penalty
        return max(35, min(96, round(raw_conf)))

    def analyze_match(self, match):
        h_stats = match.get("home_stats", {})
        a_stats = match.get("away_stats", {})

        # Gol beklentileri (xG)
        lambda_h = max(0.40, float(h_stats.get("calc_xg", 1.35)))
        lambda_a = max(0.35, float(a_stats.get("calc_xg", 1.15)))

        # Canlı maç kırmızı kart çarpanı (In-Play kuralı)
        h_reds = int(match.get("home_reds", 0))
        a_reds = int(match.get("away_reds", 0))
        if h_reds > 0:
            lambda_h *= max(0.4, 1.0 - (h_reds * 0.32))
            lambda_a *= (1.0 + (h_reds * 0.22))
        if a_reds > 0:
            lambda_a *= max(0.4, 1.0 - (a_reds * 0.32))
            lambda_h *= (1.0 + (a_reds * 0.22))

        # 1. 90 DAKİKA DİXON-COLES MATRİSİ
        matrix_90 = self._build_dixon_coles_matrix(lambda_h, lambda_a, max_goals=7)

        ms_home_prob = 0.0
        ms_draw_prob = 0.0
        ms_away_prob = 0.0

        o15_prob = 0.0
        o25_prob = 0.0
        o35_prob = 0.0
        btts_yes_prob = 0.0

        scores_list = []

        for h in range(8):
            for a in range(8):
                prob = matrix_90[h][a]

                # Maç Sonu
                if h > a: ms_home_prob += prob
                elif h == a: ms_draw_prob += prob
                else: ms_away_prob += prob

                # Gol Baremleri
                tot = h + a
                if tot > 1.5: o15_prob += prob
                if tot > 2.5: o25_prob += prob
                if tot > 3.5: o35_prob += prob

                # Karşılıklı Gol
                if h > 0 and a > 0:
                    btts_yes_prob += prob

                scores_list.append((f"{h}-{a}", prob))

        # 2. İLK YARI (İY) DİXON-COLES MATRİSİ
        lambda_h_iy = lambda_h * self.first_half_ratio
        lambda_a_iy = lambda_a * self.first_half_ratio
        matrix_iy = self._build_dixon_coles_matrix(lambda_h_iy, lambda_a_iy, max_goals=4)

        iy_home_prob, iy_draw_prob, iy_away_prob, iy_o05_prob = 0.0, 0.0, 0.0, 0.0
        for h in range(5):
            for a in range(5):
                prob_iy = matrix_iy[h][a]
                if h > a: iy_home_prob += prob_iy
                elif h == a: iy_draw_prob += prob_iy
                else: iy_away_prob += prob_iy
                if (h + a) > 0.5: iy_o05_prob += prob_iy

        # 3. İKİNCİ YARI (2Y) MATRİSİ
        lambda_h_2y = lambda_h * self.second_half_ratio
        lambda_a_2y = lambda_a * self.second_half_ratio
        matrix_2y = self._build_dixon_coles_matrix(lambda_h_2y, lambda_a_2y, max_goals=4)

        y2_home_prob, y2_draw_prob, y2_away_prob = 0.0, 0.0, 0.0
        for h in range(5):
            for a in range(5):
                prob_2y = matrix_2y[h][a]
                if h > a: y2_home_prob += prob_2y
                elif h == a: y2_draw_prob += prob_2y
                else: y2_away_prob += prob_2y

        # Yüzdeleri yuvarla
        def pct(v): return round(v * 100.0, 1)

        ms_h_pct = pct(ms_home_prob)
        ms_x_pct = pct(ms_draw_prob)
        ms_a_pct = pct(ms_away_prob)

        o15_pct = pct(o15_prob)
        o25_pct = pct(o25_prob)
        o35_pct = pct(o35_prob)
        btts_pct = pct(btts_yes_prob)

        # En olası ilk 3 skor
        scores_list.sort(key=lambda x: x[1], reverse=True)
        top_scores = [
            {"score": s[0], "prob": f"%{pct(s[1])}"} for s in scores_list[:3]
        ]

        # Güven Endeksi
        total_xg = lambda_h + lambda_a
        confidence = self._calculate_confidence_score(ms_h_pct, ms_x_pct, ms_a_pct, total_xg)

        # En güçlü istatistiksel tercih (Telegram sinyalleri için çekirdek alan)
        picks_ranking = [
            ("MS 1", ms_h_pct, ms_h_pct >= 48.0),
            ("MS 2", ms_a_pct, ms_a_pct >= 42.0),
            ("2.5 ÜST", o25_pct, o25_pct >= 53.0),
            ("2.5 ALT", round(100.0 - o25_pct, 1), (100.0 - o25_pct) >= 53.0),
            ("KG VAR", btts_pct, btts_pct >= 53.0),
            ("İY 0.5 ÜST", pct(iy_o05_prob), pct(iy_o05_prob) >= 65.0),
            ("1X ÇŞ", round(ms_h_pct + ms_x_pct, 1), (ms_h_pct + ms_x_pct) >= 72.0)
        ]
        valid_picks = [p for p in picks_ranking if p[2]]
        valid_picks.sort(key=lambda x: x[1], reverse=True)
        strongest_pick = f"{valid_picks[0][0]} (%{valid_picks[0][1]})" if valid_picks else f"2.5 ÜST (%{o25_pct})"

        # Volatilite uyarısı
        volatility_warning = None
        if h_reds > 0 or a_reds > 0:
            volatility_warning = f"DİKKAT: Sahada kırmızı kart var ({h_reds}K - {a_reds}K). Sayısal dengeler yeniden hesaplandı."
        elif abs(ms_h_pct - ms_a_pct) < 4.0 and o25_pct > 58.0:
            volatility_warning = "YÜKSEK VOLATİLİTE: İki takımın kazanma ihtimali birbirine çok yakın, taraf yerine barem tercih edilebilir."

        result = dict(match)
        result["confidence_score"] = confidence
        result["strongest_pick"] = strongest_pick
        result["top_scores"] = top_scores
        result["volatility_warning"] = volatility_warning
        result["analysis"] = {
            "lambda_home": round(lambda_h, 2),
            "lambda_away": round(lambda_a, 2),
            "total_expected_goals": round(total_xg, 2),
            "ms_home": ms_h_pct,
            "ms_draw": ms_x_pct,
            "ms_away": ms_a_pct,
            "cs_1x": round(ms_h_pct + ms_x_pct, 1),
            "cs_x2": round(ms_x_pct + ms_a_pct, 1),
            "iy_home": pct(iy_home_prob),
            "iy_draw": pct(iy_draw_prob),
            "iy_away": pct(iy_away_prob),
            "iy_over_05": pct(iy_o05_prob),
            "y2_home": pct(y2_home_prob),
            "y2_draw": pct(y2_draw_prob),
            "y2_away": pct(y2_away_prob),
            "over_15": o15_pct,
            "over_25": o25_pct,
            "over_35": o35_pct,
            "under_25": round(100.0 - o25_pct, 1),
            "btts_yes": btts_pct,
            "btts_no": round(100.0 - btts_pct, 1)
        }
        return result
