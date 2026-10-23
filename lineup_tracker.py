import requests

class LineupTracker:
    """
    ESPN Match Summary uç noktasını sorgulayarak resmi ilk 11'leri,
    sakat ve cezalı oyuncuları analiz eden ve xG katsayılarını hesaplayan modül.
    """

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    def inspect_match_lineup(self, league_slug, match_id):
        default_res = {
            "lineup_confirmed": False,
            "status_label": "Muhtemel Kadro",
            "home_attack_mod": 1.0,
            "home_defense_mod": 1.0,
            "away_attack_mod": 1.0,
            "away_defense_mod": 1.0,
            "missing_notices": []
        }

        if not league_slug or not match_id:
            return default_res

        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/summary?event={match_id}"

        try:
            res = requests.get(url, headers=self.headers, timeout=5)
            if res.status_code != 200:
                return default_res

            data = res.json()
            rosters = data.get("rosters", [])
            injuries = data.get("injuries", [])
            notices = []

            # 1. Sakatlık & Cezalı Analizi (Injuries Sekmesi)
            home_atk_mod, home_def_mod = 1.0, 1.0
            away_atk_mod, away_def_mod = 1.0, 1.0

            for inj in injuries:
                team_side = inj.get("team", {}).get("homeAway", "")
                team_name = inj.get("team", {}).get("displayName", "")
                
                for p in inj.get("injuries", []):
                    ath_name = p.get("athlete", {}).get("displayName", "Oyuncu")
                    pos = p.get("athlete", {}).get("position", {}).get("abbreviation", "")
                    status = p.get("status", "Kadro Dışı")

                    if any(term in str(status).lower() for term in ["out", "doubtful", "sakat", "cezalı", "injured"]):
                        notices.append(f"{team_name}: {ath_name} ({pos} - {status})")

                        # Forvet ve kaleci/defans eksikliği çarpanları
                        if team_side == "home":
                            if pos in ["FW", "F", "ST"]:
                                home_atk_mod = max(0.86, home_atk_mod - 0.08)
                            elif pos in ["GK", "CB", "D"]:
                                home_def_mod = min(1.14, home_def_mod + 0.06)
                        elif team_side == "away":
                            if pos in ["FW", "F", "ST"]:
                                away_atk_mod = max(0.86, away_atk_mod - 0.08)
                            elif pos in ["GK", "CB", "D"]:
                                away_def_mod = min(1.14, away_def_mod + 0.06)

            # 2. Resmi İlk 11 Kontrolü (Rosters Sekmesi)
            lineup_confirmed = False
            if rosters and len(rosters) >= 2:
                home_roster = rosters[0] if rosters[0].get("homeAway") == "home" else rosters[1]
                away_roster = rosters[1] if rosters[1].get("homeAway") == "away" else rosters[0]

                home_starters = [p for p in home_roster.get("roster", []) if p.get("starter")]
                away_starters = [p for p in away_roster.get("roster", []) if p.get("starter")]

                if len(home_starters) >= 11 and len(away_starters) >= 11:
                    lineup_confirmed = True

            return {
                "lineup_confirmed": lineup_confirmed,
                "status_label": "Resmi 11 Doğrulandı" if lineup_confirmed else "Muhtemel Kadro",
                "home_attack_mod": round(home_atk_mod, 2),
                "home_defense_mod": round(home_def_mod, 2),
                "away_attack_mod": round(away_atk_mod, 2),
                "away_defense_mod": round(away_def_mod, 2),
                "missing_notices": notices[:4]
            }

        except Exception:
            return default_res
