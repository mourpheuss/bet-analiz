import requests

class LineupTracker:
    """
    ESPN üzerinden resmi ilk 11'leri, kadro dışı/eksik oyuncuları sorgulayan
    ve hücum/savunma xG çarpanlarını belirleyen modül.
    """

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    def inspect_match_lineup(self, league_slug, match_id):
        """
        Maçın kadro durumunu sorgular.
        Dönüş:
        {
            "lineup_confirmed": True/False,
            "home_lineup_status": "Resmi 11 Açıklandı" / "Muhtemel Kadro",
            "away_lineup_status": "Resmi 11 Açıklandı" / "Muhtemel Kadro",
            "home_attack_mod": 1.0,  # As golcü yoksa 0.86'ya iner
            "home_defense_mod": 1.0, # As defans/kaleci yoksa 1.10'a çıkar
            "away_attack_mod": 1.0,
            "away_defense_mod": 1.0,
            "missing_notices": []
        }
        """
        default_res = {
            "lineup_confirmed": False,
            "home_lineup_status": "Muhtemel Kadro",
            "away_lineup_status": "Muhtemel Kadro",
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

            # Kadrolar henüz girilmemişse
            if not rosters or len(rosters) < 2:
                # Injuries (Sakatlıklar) sekmesi varsa kontrol et
                injuries = data.get("injuries", [])
                notices = []
                for inj in injuries:
                    t_name = inj.get("team", {}).get("displayName", "")
                    for p in inj.get("injuries", []):
                        athlete = p.get("athlete", {}).get("displayName", "Oyuncu")
                        status = p.get("status", "Sakat")
                        notices.append(f"{t_name}: {athlete} ({status})")

                default_res["missing_notices"] = notices[:3]
                return default_res

            # Kadrolar açıklandı
            home_roster = rosters[0] if rosters[0].get("homeAway") == "home" else rosters[1]
            away_roster = rosters[1] if rosters[1].get("homeAway") == "away" else rosters[0]

            home_starters = [p.get("athlete", {}).get("displayName", "") for p in home_roster.get("roster", []) if p.get("starter")]
            away_starters = [p.get("athlete", {}).get("displayName", "") for p in away_roster.get("roster", []) if p.get("starter")]

            lineup_confirmed = len(home_starters) >= 11 and len(away_starters) >= 11

            notices = []
            home_atk_mod, home_def_mod = 1.0, 1.0
            away_atk_mod, away_def_mod = 1.0, 1.0

            # ESPN injuries kontrolü
            for inj in data.get("injuries", []):
                t_side = inj.get("team", {}).get("homeAway", "")
                for p in inj.get("injuries", []):
                    ath = p.get("athlete", {}).get("displayName", "")
                    pos = p.get("athlete", {}).get("position", {}).get("abbreviation", "")
                    status = p.get("status", "Kadro Dışı")
                    
                    if "Out" in status or "Doubtful" in status or "Sakat" in status:
                        notices.append(f"{ath} ({pos} - {status})")
                        if t_side == "home":
                            if pos in ["FW", "F", "ST"]: home_atk_mod = 0.88
                            elif pos in ["GK", "CB", "D"]: home_def_mod = 1.10
                        elif t_side == "away":
                            if pos in ["FW", "F", "ST"]: away_atk_mod = 0.88
                            elif pos in ["GK", "CB", "D"]: away_def_mod = 1.10

            return {
                "lineup_confirmed": lineup_confirmed,
                "home_lineup_status": "Resmi 11 Doğrulandı" if lineup_confirmed else "Muhtemel Kadro",
                "away_lineup_status": "Resmi 11 Doğrulandı" if lineup_confirmed else "Muhtemel Kadro",
                "home_attack_mod": home_atk_mod,
                "home_defense_mod": home_def_mod,
                "away_attack_mod": away_atk_mod,
                "away_defense_mod": away_def_mod,
                "missing_notices": notices[:4]
            }

        except Exception:
            return default_res
