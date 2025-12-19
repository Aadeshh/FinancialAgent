import os
import json
from dotenv import load_dotenv
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
import yfinance as yf
from tavily import TavilyClient
from datetime import datetime


load_dotenv()
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY environment variable not set")


class AgentState(TypedDict):
    ticker: str                 # Input: stock symbol (NVDA)
    price_data: dict             # Storage: price from yfinance
    news_data: List[str]        # storage: news headlines


def get_price_node(state:AgentState):
    ticker = state["ticker"]
    print(f"--- Fetching price data for: {ticker} ---")

    stock = yf.Ticker(ticker)
    hist = stock.history(period="1mo")

    latest = hist.iloc[-1]
    last_date = latest.name.strftime("%Y-%m-%d")
    print(f"Latest data date: {last_date}")

    prev_close = hist.iloc[-2]['Close']
    current_close = latest['Close']
    pct_change = ((current_close - prev_close) / prev_close) * 100

    price_summary = {
        "date": last_date,
        "current_price": round(current_close, 2),
        "pct_change": round(pct_change, 2),
        "trend": "Bullish" if pct_change > 0 else "Bearish"
    }
    
    return {"price_data":price_summary}


def get_news_node(state:AgentState):
    ticker = state["ticker"]
    print(f"--- [2] Fetching News for {ticker} ---")

    today = datetime.now().strftime("%Y-%m-%d")

    query = f"{ticker} stock news {today} reason for price movement"
    search_res = tavily_client.search(query=query, topic="news", days=1)

    news_summaries = []

    if not search_res.get('results'):
        return {"news_data": ["No specific news found for today."]}
    
    for res in search_res['results'][:3]:
        news_summaries.append(f"{res['title']} - {res['url']}")
    
    return {"news_data": news_summaries}

workflow = StateGraph(AgentState)

workflow.add_node("market_data", get_price_node)
workflow.add_node("financial_news", get_news_node)

workflow.set_entry_point("market_data")
workflow.add_edge("market_data", "financial_news")
workflow.add_edge("financial_news", END)

app = workflow.compile()

if __name__ == "__main__":
    inp = {"ticker": "NVDA"}

    print("--- Starting Workflow Execution ---")
    result = app.invoke(inp)
    
    print("\n\n--- Workflow Execution Completed ---")
    print(f"Ticker: {result['ticker']}")
    print(f"Price: {result['price_data']}")
    print("Top News")
    for news in result['news_data']:
        print(f"- {news}")
    
    print("\n\n###############################################")