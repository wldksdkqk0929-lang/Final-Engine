import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import re

class NewsCollector:
    def __init__(self):
        # Google News RSS URL (검색어 기반)
        self.base_url = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def _clean_html(self, raw_html):
        cleanr = re.compile('<.*?>')
        cleantext = re.sub(cleanr, '', raw_html)
        return cleantext

    def get_news(self, symbol: str, lookback_days: int = 3) -> list:
        """
        특정 티커의 최근 뉴스를 수집하여 반환
        """
        # 검색어 생성 (티커 + stock 키워드 조합)
        query = f"{symbol} stock news"
        url = self.base_url.format(query=query)
        
        print(f"📡 [Collector] Fetching news for: {symbol}...")
        
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code != 200:
                print(f"⚠️ [Collector] Failed to fetch news: {resp.status_code}")
                return []
            
            # XML 파싱
            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            
            news_list = []
            cutoff_date = datetime.now() - timedelta(days=lookback_days)
            
            for item in items[:5]: # 상위 5개만 (속도 최적화)
                title = item.find("title").text if item.find("title") is not None else "No Title"
                link = item.find("link").text if item.find("link") is not None else ""
                pub_date_str = item.find("pubDate").text if item.find("pubDate") is not None else ""
                
                # 날짜 파싱 (예: Mon, 01 Feb 2026 10:00:00 GMT)
                # 파싱 실패시 현재 시간으로 대체하여 에러 방지
                try:
                    pub_date = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z")
                except:
                    pub_date = datetime.now()

                if pub_date >= cutoff_date:
                    news_list.append({
                        "source": "GoogleNews",
                        "title": title,
                        "link": link,
                        "published": pub_date.strftime("%Y-%m-%d"),
                        "snippet": title # RSS는 본문이 없으므로 제목을 snippet으로 활용
                    })
            
            print(f"   ✅ Found {len(news_list)} recent articles.")
            return news_list

        except Exception as e:
            print(f"❌ [Collector] Error: {e}")
            return []

# 테스트 실행 코드
if __name__ == "__main__":
    collector = NewsCollector()
    news = collector.get_news("TSLA", lookback_days=2)
    for n in news:
        print(f" - [{n['published']}] {n['title']}")
