import requests
import re
import unicodedata
import random
from lineup_tracker import LineupTracker

class StatsFeeder:
    """
    Saf İç/Dış Saha averajlarını, ESPN'in displayValue formunu,
    fikstür yorgunluk katsayısını ve ilk 11 sakatlık analizini birleştiren veri besleyici.
    """

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        self.standings_cache = {}
        self.lineup_tracker = LineupTracker()

        self.league_slug_map = {
            "trendyol süper lig": "tur.1",
            "super lig": "tur.1",
            "trendyol 1. lig": "tur.2",
            "premier league": "eng.1",
            "ingiltere championship": "eng.2",
            "championship": "eng.2",
            "ingiltere league one": "eng.3",
            "ingiltere league two": "eng.4",
            "la liga": "esp.1",
            "la liga 2": "esp.2",
            "serie a": "ita.1",
            "serie b": "ita.2",
            "bundesliga": "ger.1",
            "bundesliga 2": "ger.2",
            "fransa ligue 1": "fra.1",
            "ligue 1": "fra.1",
            "fransa ligue 2": "fra.2",
            "ligue 2": "fra.2",
            "hollanda eredivisie": "ned.1",
            "eredivisie": "ned.1",
            "portekiz liga nos": "por.1",
            "belçika pro league": "bel.1",
            "iskoçya premiership": "sco.1",
            "avusturya bundesliga": "aut.1",
            "isviçre süper ligi": "sui.1",
            "danimarka superliga": "den.1",
            "yunanistan süper ligi": "gre.1",
            "suudi arabistan pro lig": "ksa.1",
            "saudi pro league": "ksa.1",
            "brezilya serie a": "bra.1",
            "brezilya serie b": "bra.2",
            "arjantin liga profesional": "arg.1",
            "meksika liga mx": "mex.1",
            "abd mls": "usa.1",
            "japonya j1 league": "jpn.1"
        }

        self.league_baselines = {
            "Premier League": {"home_gf": 1.65, "away_gf": 1.28},
            "Bundesliga": {"home_gf": 1.78, "away_gf": 1.40},
            "Bundesliga 2": {"home_gf": 1.68, "away_gf": 1.34},
            "Trendyol Süper Lig": {"home_gf": 1.52, "away_gf": 1.18},
            "La Liga": {"home_gf": 1.44, "away_gf": 1.06},
            "Serie A": {"home_gf": 1.48, "away_gf": 1.12},
            "Fransa Ligue 1": {"home_gf": 1.46, "away_gf": 1.14},
            "Fransa Ligue 2": {"home_gf": 1.32, "away_gf": 1.02},
            "Hollanda Eredivisie": {"home_gf": 1.82, "away_gf": 1.44},
            "Suudi Arabistan Pro Lig": {"home_gf": 1.62, "away_gf": 1.36},
            "Danimarka Superliga": {"home_gf": 1.54, "away_gf": 1.26},
            "Avusturya Bundesliga": {"home_gf": 1.60, "away_gf": 1.32}
        }

    def _normalize(self, text):
        if not text: return ""
        text = str(text).replace("İ", "I").replace("ı", "i")
        n = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
        return re.sub(r'[^a-zA-Z0-9]', '', n).lower()

    def _safe_int(self, val, default=0):
        try:
            return int(float(val)) if val is not None else default
        except (ValueError, TypeError):
            return default

    def _safe_float(self, val, default=0.0):
        try:
            return float(val) if val is not None else default
        except (ValueError, TypeError):
            return default

    def _resolve_league_slug(self, league_name):
        if not league_name: return None
        l_low = str(league_name).strip().lower()
        if l_low in self.league_slug_map:
            return self.league_slug_map[l_low]
        for k, slug in self.league_slug_map.items():
            if k in l_low or l_low in k:
                return slug
        return None

    def _generate_realistic_form_from_stats(self, wins, ties, losses, rank):
        total = wins + ties + losses
        if total == 0:
            return ["G", "B", "M", "B", "G"] if rank <= 8 else ["M", "B", "M", "G", "M"]

        p_win = wins / total
        p_tie = ties / total
        p_loss = losses / total

        form = []
        for _ in range(5):
            r = random.random()
            if r < p_win:
                form.append("G")
            elif r < (p_win + p_tie):
                form.append("B")
            else:
                form.append("M")
        return form

    def fetch_league_standings(self, league_name):
        slug = self._resolve_league_slug(league_name)
        if not slug:
            return {}

        if slug in self.standings_cache:
            return self.standings_cache[slug]

        url = f"https://site.web.api.espn.com/apis/v2/sports/soccer/{slug}/standings"
        table = {}

        try:
            res = requests.get(url, headers=self.headers, timeout=6)
            if res.status_code == 200:
                data = res.json()
                entries = []
                if "children" in data and len(data["children"]) > 0:
                    for ch in data["children"]:
                        st = ch.get("standings", {})
                        if isinstance(st, dict):
                            entries.extend(st.get("entries", []))
                elif "standings" in data:
                    st = data["standings"]
                    if isinstance(st, dict):
                        entries.extend(st.get("entries", []))

                for idx, entry in enumerate(entries):
                    t_info = entry.get("team", {})
                    t_name = t_info.get("displayName", "") or t_info.get("name", "")
                    norm_name = self._normalize(t_name)

                    stats_list = {}
                    raw_form_str = ""

                    for s in entry.get("stats", []):
                        if isinstance(s, dict) and "name" in s:
                            s_name = s["name"]
                            stats_list[s_name] = s.get("value")
                            if s_name == "form" and s.get("displayValue"):
                                raw_form_str = str(s.get("displayValue"))

                    rank = self._safe_int(stats_list.get("rank"), idx + 1)
                    points = self._safe_int(stats_list.get("points"), 0)
                    played = max(1, self._safe_int(stats_list.get("gamesPlayed"), 1))
                    wins = self._safe_int(stats_list.get("wins"), 0)
                    ties = self._safe_int(stats_list.get("ties"), 0)
                    losses = self._safe_int(stats_list.get("losses"), 0)
                    gf = self._safe_float(stats_list.get("pointsFor"), 0.0)
                    ga = self._safe_float(stats_list.get("pointsAgainst"), 0.0)

                    home_played = self._safe_int(stats_list.get("homeGamesPlayed"), max(1, played // 2))
                    away_played = self._safe_int(stats_list.get("awayGamesPlayed"), max(1, played - home_played))
                    
                    home_gf = self._safe_float(stats_list.get("homePointsFor"), gf * 0.58)
                    home_ga = self._safe_float(stats_list.get("homePointsAgainst"), ga * 0.44)
                    away_gf = self._safe_float(stats_list.get("awayPointsFor"), gf - home_gf)
                    away_ga = self._safe_float(stats_list.get("awayPointsAgainst"), ga - home_ga)

                    home_avg_scored = round(home_gf / max(1, home_played), 2)
                    home_avg_conceded = round(home_ga / max(1, home_played), 2)
                    away_avg_scored = round(away_gf / max(1, away_played), 2)
                    away_avg_conceded = round(away_ga / max(1, away_played), 2)

                    form_list = []
                    if raw_form_str:
                        for ch in raw_form_str.replace(",", "").upper()[:5]:
                            if ch == 'W': form_list.append('G')
                            elif ch == 'D': form_list.append('B')
                            elif ch == 'L': form_list.append('M')

                    if not form_list:
                        form_list = self._generate_realistic_form_from_stats(wins, ties, losses, rank)

                    table[norm_name] = {
                        "display_name": t_name,
                        "rank": rank,
                        "points": points,
                        "played": played,
                        "avg_scored": round(gf / played, 2),
                        "avg_conceded": round(ga / played, 2),
                        "home_avg_scored": max(0.5, home_avg_scored),
                        "home_avg_conceded": max(0.4, home_avg_conceded),
                        "away_avg_scored": max(0.4, away_avg_scored),
                        "away_avg_conceded": max(0.5, away_avg_conceded),
                        "form": form_list
                    }

                self.standings_cache[slug] = table
        except Exception:
            pass

        return table

    def _find_team(self, name, table):
        norm = self._normalize(name)
        if not norm or not table: return None
        if norm in table: return table[norm]
        for k, v in table.items():
            if len(norm) >= 4 and (norm in k or k in norm): return v
            if len(k) >= 4 and (k in norm or norm in k): return v
        return None

    def _calculate_exponential_form(self, form_list):
        weights = [0.35, 0.25, 0.20, 0.12, 0.08]
        score_map = {'G': 3.0, 'B': 1.0, 'M': 0.0}
        
        weighted_total = 0.0
        active_weights = 0.0
        for idx, match_res in enumerate(form_list[:5]):
            w = weights[idx]
            pt = score_map.get(match_res, 1.0)
            weighted_total += (w * pt)
            active_weights += w

        normalized_score = weighted_total / max(0.1, active_weights)
        boost = 1.0 + ((normalized_score - 1.30) * 0.12)
        return max(0.85, min(1.20, round(boost, 3)))

    def _calculate_fatigue_multiplier(self, match):
        rest_days = match.get("rest_days", 6)
        if rest_days <= 3:
            return 0.94, 1.04
        elif rest_days >= 8:
            return 1.02, 0.98
        return 1.0, 1.0

    def enrich_match_data(self, match):
        """
        Maçı lig baselines, saf iç/dış averajlar, üstel form,
        fikstür yorgunluğu ve ilk 11 sakatlık verileriyle zenginleştirir.
        """
        league = match.get("league", "")
        home_team = match.get("home_team", "")
        away_team = match.get("away_team", "")

        table = self.fetch_league_standings(league)
        h_data = self._find_team(home_team, table)
        a_data = self._find_team(away_team, table)

        baseline = self.league_baselines.get(league, {"home_gf": 1.52, "away_gf": 1.18})

        # 1. Saf İç / Dış Saha İstatistikleri
        if h_data:
            h_rank, h_points, h_form = h_data["rank"], h_data["points"], h_data["form"]
            h_scored = h_data["home_avg_scored"]
            h_conceded = h_data["home_avg_conceded"]
        else:
            h_rank, h_points = "-", "-"
            h_form = ["G", "B", "M", "G", "B"]
            h_scored = baseline["home_gf"]
            h_conceded = baseline["away_gf"] * 0.85

        if a_data:
            a_rank, a_points, a_form = a_data["rank"], a_data["points"], a_data["form"]
            a_scored = a_data["away_avg_scored"]
            a_conceded = a_data["away_avg_conceded"]
        else:
            a_rank, a_points = "-", "-"
            a_form = ["M", "B", "M", "G", "M"]
            a_scored = baseline["away_gf"]
            a_conceded = baseline["home_gf"] * 1.15

        # 2. Üstel Form Momentum
        h_form_boost = self._calculate_exponential_form(h_form)
        a_form_boost = self._calculate_exponential_form(a_form)

        # 3. Fikstür Dinlenme Yorgunluğu
        h_rest_atk, h_rest_def = self._calculate_fatigue_multiplier(match)
        a_rest_atk, a_rest_def = self._calculate_fatigue_multiplier(match)

        # 4. İlk 11 & Sakat/Cezalı Takip Motoru
        slug = self._resolve_league_slug(league)
        match_id = match.get("match_id")
        lineup_info = self.lineup_tracker.inspect_match_lineup(slug, match_id)

        # 5. Tüm Faktörlerin Dahil Edildiği Nihai xG Hesabı
        home_calc_xg = round(
            (h_scored * (a_conceded * a_rest_def) / 1.30)
            * 1.10
            * h_form_boost
            * h_rest_atk
            * lineup_info["home_attack_mod"]
            * lineup_info["away_defense_mod"],
            2
        )
        away_calc_xg = round(
            (a_scored * (h_conceded * h_rest_def) / 1.30)
            * 0.90
            * a_form_boost
            * a_rest_atk
            * lineup_info["away_attack_mod"]
            * lineup_info["home_defense_mod"],
            2
        )

        match["home_stats"] = {
            "rank": h_rank, "points": h_points, "form": h_form,
            "home_gf_avg": h_scored, "home_ga_avg": h_conceded,
            "calc_xg": max(0.40, home_calc_xg)
        }
        match["away_stats"] = {
            "rank": a_rank, "points": a_points, "form": a_form,
            "away_gf_avg": a_scored, "away_ga_avg": a_conceded,
            "calc_xg": max(0.35, away_calc_xg)
        }

        match["home_rank"] = h_rank
        match["away_rank"] = a_rank
        match["home_points"] = h_points
        match["away_points"] = a_points
        match["home_form"] = h_form
        match["away_form"] = a_form
        match["lineup_info"] = lineup_info

        return match
