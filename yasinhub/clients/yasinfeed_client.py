import json
import urllib.request


class YasinFeedClient:

    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")


    def _get(self, path):
        url = f"{self.base_url}{path}"

        with urllib.request.urlopen(url) as response:
            return json.loads(
                response.read().decode()
            )


    def health(self):
        try:
            return self._get("/api/health")
        except Exception as e:
            return {
                "service": "YasinFeed",
                "status": "unhealthy",
                "error": f"خطا در ارتباط با کلاینت: {str(e)}"
            }


    def version(self):
        try:
            return self._get("/api/version")
        except Exception as e:
            return "unknown"


    def routes(self):
        try:
            return self._get("/api/routes")
        except Exception as e:
            return []


    def stats(self):
        try:
            return self._get("/api/stats")
        except Exception as e:
            return {}


    def articles(self, page=1, limit=10):
        return self._get(
            f"/api/articles?page={page}&limit={limit}"
        )


    def article(self, article_id):
        return self._get(
            f"/api/articles/{article_id}"
        )
