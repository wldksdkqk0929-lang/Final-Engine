import yfinance as yf
from datetime import datetime
import time

class NewsCollector:
    def __init__(self):
        pass

    def fetch_news(self, symbol: str):
        """
        yfinance를 통해 해당 종목의 최신 뉴스를 가져옵니다.
        """
        try:
            # Ticker 객체 생성
            ticker = yf.Ticker(symbol)
            # 뉴스 데이터 가져오기 (리스트 형태)
            raw_news = ticker.news
            
            clean_news = []
            if raw_news:
                for n in raw_news:
                    # timestamp를 날짜로 변환
                    pub_time = n.get('providerPublishTime', 0)
                    date_str = datetime.fromtimestamp(pub_time).strftime('%Y-%m-%d')
                    
                    clean_news.append({
                        "title": n.get('title', 'No Title'),
                        "published": date_str,
                        "link": n.get('link', '#')
                    })
            return clean_news

        except Exception as e:
            # 에러 발생 시 빈 리스트 반환 (멈추지 않음)
            return []
