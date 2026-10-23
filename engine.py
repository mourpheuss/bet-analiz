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
        """Ev sahibi ve Deplasman için ortak Dixon-Coles olasılık matrisini kurar."""
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

        if total_prob > 0:
            for h in range(max_goals + 1):
                for a in range(max_goals + 1):
                    matrix[h][a] /= total_prob

        return matrix

    def _calculate_confidence_score(self, ms_h, ms_x, ms_a, total_xg):
        """Model Entropisi ve Olasılık Keskinliği Analizi (0 - 100 arası Güven Skoru)"""
        max_outcome = max(ms_h, ms_x, ms_a)
        edge_score = (max_outcome - 33.3) * 1.85
        xg_penalty = 8.0 if (total_xg < 1.2 or total_xg > 4.4) else 0.0
        raw_conf = 52.0 + edge_score - xg_penalty
        return max(35, min(97, round(raw_conf)))

    def _detect_value_and_sniper(self, picks_data, total_xg, confidence):
        """
        Piyasa Değer Açığı (+EV Value) ve Sniper Uygunluğunu Belirler.
        """
        # Piyasa medyan varsayılan yüzdeleri (Büroların ortalama açtığı barem tabanları)
        market_benchmarks = {
            "2.5 ÜST": 50.5,
            "2.5 ALT": 49.5,
            "KG VAR": 51.0,
            "İY 0.5 ÜST": 68.0,
            "1.5 ÜST": 74.0,
            "1X ÇŞ": 66.0,
            "X2 ÇŞ": 60.0
        }

        value_bets = []
        for pick_name, model_prob in picks_data:
            base_prob = market_benchmarks.get(pick_name)
            if base_prob:
                edge = round(model_prob - base_prob, 1)
                # Model piyasadan en az %9.5 daha yüksek ihtimal görüyorsa VALUE vardır
                if edge >= 9.5:
                    fair_odd = round(100.0 / model_prob, 2) if model_prob > 0 else 2.0
                    value_bets.append({
                        "market": pick_name,
                        "model_prob": model_prob,
                        "edge": edge,
                        "fair_odd": fair_odd
                    })

        value_bets.sort(key=lambda x: x["edge"], reverse=True)
        top_value = value_bets[0] if value_bets else None

        # SNIPER ADAYI KONTROLÜ (Günün Tek Vuruşu Kriterleri)
        # 1. En az %74 olasılık
        # 2. Minimum 80 Güven Skoru
        # 3. Dengeli gol beklentisi (1.4 - 3.8 xG)
        is_sniper = False
        sniper_pick = None

        if confidence >= 80 and 1.4 <= total_xg <= 3.8:
            for p_name, p_prob in picks_data:
                if p_prob >= 74.0:
                    is_sniper = True
                    sniper_pick = f"{p_name} (%{p_prob})"
                    break

        return top_value, is_sniper, sniper_pick

    def analyze_match(self, match):
        h_stats = match.get("home_stats", {})
        a_stats = match.get("away_stats", {})

        lambda_h = max(0.40, float(h_stats.get("calc_xg", 1.35)))
        lambda_a = max(0.35, float(a_stats.get("calc_xg", 1.15)))

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

        ms_home_prob, ms_draw_prob, ms_away_prob = 0.0, 0.0, 0.0
        o15_prob, o25_prob, o35_prob, btts_yes_prob = 0.0, 0.0, 0.0, 0.0
        scores_list = []

        for h in range(8):
            for a in range(8):
                prob = matrix_90[h][a]
                if h > a: ms_home_prob += prob
                elif h == a: ms_draw_prob += prob
                else: ms_away_prob += prob

                tot = h + a
                if tot > 1.5: o15_prob += prob
                if tot > 2.5: o25_prob += prob
                if tot > 3.5: o35_prob += prob
                if h > 0 and a > 0: btts_yes_prob += prob

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

        def pct(v): return round(v * 100.0, 1)

        ms_h_pct = pct(ms_home_prob)
        ms_x_pct = pct(ms_draw_prob)
        ms_a_pct = pct(ms_away_prob)

        o15_pct = pct(o15_prob)
        o25_pct = pct(o25_prob)
        o35_pct = pct(o35_prob)
        u25_pct = round(100.0 - o25_pct, 1)
        btts_pct = pct(btts_yes_prob)
        iy_o05_pct = pct(iy_o05_prob)
        cs_1x_pct = round(ms_h_pct + ms_x_pct, 1)
        cs_x2_pct = round(ms_x_pct + ms_a_pct, 1)

        scores_list.sort(key=lambda x: x[1], reverse=True)
        top_scores = [{"score": s[0], "prob": f"%{pct(s[1])}"} for s in scores_list[:3]]

        total_xg = lambda_h + lambda_a
        confidence = self._calculate_confidence_score(ms_h_pct, ms_x_pct, ms_a_pct, total_xg)

        # AKILLI TERCİH HAVUZU (Riskli %45'lik tek maçlar elendi)
        candidates = [
            ("1X ÇŞ", cs_1x_pct, cs_1x_pct >= 74.0),
            ("X2 ÇŞ", cs_x2_pct, cs_x2_pct >= 72.0),
            ("İY 0.5 ÜST", iy_o05_pct, iy_o05_pct >= 71.0),
            ("1.5 ÜST", o15_pct, o15_pct >= 76.0),
            ("2.5 ÜST", o25_pct, o25_pct >= 57.0),
            ("2.5 ALT", u25_pct, u25_pct >= 58.0),
            ("KG VAR", btts_pct, btts_pct >= 56.0),
            ("MS 1", ms_h_pct, ms_h_pct >= 64.0),
            ("MS 2", ms_a_pct, ms_a_pct >= 54.0)
        ]

        valid_picks = [(p[0], p[1]) for p in candidates if p[2]]
        valid_picks.sort(key=lambda x: x[1], reverse=True)

        if valid_picks:
            strongest_pick = f"{valid_picks[0][0]} (%{valid_picks[0][1]})"
        else:
            strongest_pick = f"1.5 ÜST (%{o15_pct})"

        # VALUE VE SNIPER ANALİZİ
        all_market_probs = [
            ("2.5 ÜST", o25_pct),
            ("2.5 ALT", u25_pct),
            ("KG VAR", btts_pct),
            ("İY 0.5 ÜST", iy_o05_pct),
            ("1.5 ÜST", o15_pct),
            ("1X ÇŞ", cs_1x_pct),
            ("X2 ÇŞ", cs_x2_pct)
        ]
        top_value, is_sniper, sniper_pick = self._detect_value_and_sniper(all_market_probs, total_xg, confidence)

        # Volatilite Analizi
        volatility_warning = None
        if h_reds > 0 or a_reds > 0:
            volatility_warning = f"DİKKAT: Sahada kırmızı kart var ({h_reds}K - {a_reds}K). Sayısal dengeler yeniden hesaplandı."
        elif abs(ms_h_pct - ms_a_pct) < 5.0 and o25_pct > 56.0:
            volatility_warning = "DENGELİ GÜÇLER: Taraf bahsi yerine gol baremleri (1.5 / 2.5 Üst) daha güvenlidir."

        result = dict(match)
        result["confidence_score"] = confidence
        result["strongest_pick"] = strongest_pick
        result["top_scores"] = top_scores
        result["volatility_warning"] = volatility_warning
        
        # Yeni Eşsiz Alanlar
        result["is_sniper"] = is_sniper
        result["sniper_pick"] = sniper_pick if is_sniper else None
        result["is_value"] = bool(top_value)
        result["value_data"] = top_value

        result["analysis"] = {
            "lambda_home": round(lambda_h, 2),
            "lambda_away": round(lambda_a, 2),
            "total_expected_goals": round(total_xg, 2),
            "ms_home": ms_h_pct,
            "ms_draw": ms_x_pct,
            "ms_away": ms_a_pct,
            "cs_1x": cs_1x_pct,
            "cs_x2": cs_x2_pct,
            "iy_home": pct(iy_home_prob),
            "iy_draw": pct(iy_draw_prob),
            "iy_away": pct(iy_away_prob),
            "iy_over_05": iy_o05_pct,
            "y2_home": pct(y2_home_prob),
            "y2_draw": pct(y2_draw_prob),
            "y2_away": pct(y2_away_prob),
            "over_15": o15_pct,
            "over_25": o25_pct,
            "over_35": o35_pct,
            "under_25": u25_pct,
            "btts_yes": btts_pct,
            "btts_no": round(100.0 - btts_pct, 1)
        }
        return result
