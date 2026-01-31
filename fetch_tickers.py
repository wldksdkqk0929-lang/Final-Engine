import pandas as pd
import ssl

# SSL 인증서 문제 우회
ssl._create_default_https_context = ssl._create_unverified_context

def get_sp500():
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        df = tables[0]
        tickers = df['Symbol'].tolist()
        # 점(.)이 있는 티커 수정 (예: BRK.B -> BRK-B)
        tickers = [t.replace('.', '-') for t in tickers]
        return tickers
    except Exception as e:
        print(f"❌ Error fetching S&P 500: {e}")
        return []

if __name__ == "__main__":
    tickers = get_sp500()
    if tickers:
        df = pd.DataFrame(tickers, columns=['symbol'])
        df.to_csv('universe.csv', index=False)
        print(f"✅ Successfully saved {len(tickers)} targets to 'universe.csv'")
    else:
        # 실패 시 비상용 주요 종목 50개 생성
        print("⚠️ Fetch failed. Using backup list.")
        backup = ["AAPL","MSFT","GOOGL","AMZN","NVDA","TSLA","META","BRK-B","V","UNH","XOM","JNJ","JPM","WMT","PG","MA","LLY","CVX","HD","MRK","KO","PEP","ABBV","BAC","AVGO","COST","PFE","TMO","CSCO","MCD","DIS","ABT","DHR","ACN","LIN","VZ","NEE","WFC","CRM","PM","BMY","TXN","CMCSA","RTX","ADBE","NKE","NFLX","QCOM","ORCL","INTC"]
        pd.DataFrame(backup, columns=['symbol']).to_csv('universe.csv', index=False)
