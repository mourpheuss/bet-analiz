import requests

class FirebaseSync:
    def __init__(self, database_url):
        self.database_url = database_url.rstrip('/')

    def push_analyzed_matches(self, matches):
        endpoint = f"{self.database_url}/analyzed_matches.json"
        try:
            res = requests.put(endpoint, json=matches, timeout=15)
            if res.status_code == 200:
                print(f"[BAŞARILI] {len(matches)} maç Firebase'e aktarıldı.")
            else:
                print(f"[UYARI] Firebase yazma hatası HTTP {res.status_code}")
        except Exception as e:
            print(f"[HATA] Firebase bağlantı hatası: {e}")