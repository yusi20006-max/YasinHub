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
        return self._get("/api/health")


    def version(self):
        return self._get("/api/version")


    def routes(self):
        return self._get("/api/routes")


    def stats(self):
        return self._get("/api/stats")


    def articles(self, page=1, limit=10):
        return self._get(
            f"/api/articles?page={page}&limit={limit}"
        )


    def article(self, article_id):
        return self._get(
            f"/api/articles/{article_id}"
        )
