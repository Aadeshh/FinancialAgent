import os
import json
import requests
from dotenv import load_dotenv
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from langchain_tavily import TavilySearch
import yfinance as yf
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from metrics import log_metrics
import time


load_dotenv()
#tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY environment variable not set")


class AgentState(TypedDict):
    ticker: str                 # Input: stock symbol (NVDA)
    price_data: dict             # Storage: price from yfinance
    news_data: List[str]        # storage: news headlines
    analyst_reasoning: str   # storage: reasoning for price movement
    critic_feedback: str      # storage: feedback on reasoning
    final_report: str        # Output: final summarized report
    revision_number: int


def critic_node(state: AgentState):
    print(f"--- Critic: Reviewing analyst reasoning for {state['ticker']} ---")

    analysis = state["analyst_reasoning"]
    news = state["news_data"]
    price = state["price_data"]

    system_msg = "You are a Senior Editor. Critically review the financial analysis provided. Identify any potential flaws or missing considerations based on the stock price data and recent news."
    user_msg = f"""
    Original Analysis: {analysis}

    Data Provided:
    Price Data: {price}
    Recent News: {news}

    Task:
    Check if the analysis is grounded in the data. Provide constructive feedback in 2-3 sentences, highlighting any areas for improvement or additional factors to consider.
    - If the analysis mentions a trend not supported by price, reject it.
    - If the analysis lacks a news citation, reject it.

    Output exactly one word: "APPROVE" or "REJECT" followed by a short explanation if rejected.
    Example: "REJECT: You said bullish, but the price is down 5%."
    """

    response = llm.invoke([SystemMessage(content=system_msg), HumanMessage(content=user_msg)])
    feedback = response.content

    rev_num = state.get("revision_number", 0) + 1

    return {"critic_feedback": feedback, "revision_number": rev_num}


def should_continue(state: AgentState):
    feedback = state["critic_feedback"]
    rev_num = state.get("revision_number", 0)

    #1. safety valve, stop if logged too many times
    if rev_num >2:
        print(f"--- Critic: Maximum revisions reached ({rev_num}). Stopping further revisions. ---")
        return END
    
    # 2. check critics decision
    if "APPROVE" in feedback.upper():
        print("Decision: Analysis approved.")
        return END
    else:
        print("Decision: Analysis rejected, retrying...")
        return "analyst"

def fetch_stock_price(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d")
        if hist.empty:
            return {"error": "no data found"}
    
        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else latest

        return {
            "current_price": round(latest['Close'],2),
            "open": round(latest['Open'],2),
            "volume": int(latest['Volume']),
            "percent_change": round(((latest['Close'] - prev['Close']) / prev['Close']) * 100, 2)
        }
    except Exception as e:
        return {"error": str(e)}
    
def fetch_news(ticker: str):
    tool = TavilySearch(max_results=3, topic="news") # 'topic="news"' is optimized for this!
    
    try:
        resp = tool.invoke({"query": f"{ticker} stock news and analysis for the last 24 hours"})
        
        if 'results' in resp:
            news_items = [item['content'] for item in resp['results']]
        else:
            news_items = [str(resp)]
            
        return news_items
        
    except Exception as e:
        return [f"Error fetching news: {str(e)}"]
    
def price_node(state: AgentState):
    ticker = state["ticker"]
    print(f"--- Data Worker: Fetching stock price for {ticker} ---")
    price_info = fetch_stock_price(ticker)
    return {"price_data": price_info}

def news_node(state: AgentState):
    ticker = state["ticker"]
    print(f"--- News Worker: Fetching news for {ticker} ---")
    news_info = fetch_news(ticker)
    return {"news_data": news_info}

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

def analyst_node(state:AgentState):
    ticker = state["ticker"]
    price = state["price_data"]
    news = state["news_data"]

    feedback = state.get("critic_feedback", "None")

    print(f"--- Analyst: Synthesizing data(Revision {state.get('revision_number',1)}) for {ticker} ---")

    system_msg = "You are a financial analyst. Specify the current trend (bullish/bearish/neutral) based on the stock price and recent news. Provide reasoning with the provided data."
    user_msg = f"""
    Ticker: {ticker}
    Price Data: {price}
    Recent News: {news}

    Previous Critique(if any): {feedback}

    If there is a critique, you must fix the issues mentioned.
    """

    response = llm.invoke([SystemMessage(content=system_msg), HumanMessage(content=user_msg)])

    return {"analyst_reasoning": response.content}

def publisher_node(state: AgentState):
    print(f"--- Publisher: Sending final report to Slack for {state['ticker']} ---")

    ticker = state["ticker"]
    analysis = state["analyst_reasoning"]
    price = state["price_data"]

    slack_message = {
        "text": f"🚀 *Daily Insight: {ticker}*",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚀 Daily Brief: {ticker}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Price:* ${price['current_price']}"},
                    {"type": "mrkdwn", "text": f"*Change:* {price['percent_change']}%"}
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Analyst Verdict:*\n{analysis}"
                }
            },
            {
                "type": "divider"
            }
        ]
    }

    webhook_url = os.getenv("SLACK_WEBHOOK_API")
    if webhook_url:
        try:
            requests.post(webhook_url, json=slack_message)
        except Exception as e:
            print(f"Error sending Slack message: {str(e)}")
    else:
        print("SLACK_WEBHOOK_URL not set. Skipping Slack notification.")

    return {"final_report": "Sent to Slack"}


workflow = StateGraph(AgentState)

workflow.add_node("data_agent", price_node)
workflow.add_node("news_agent", news_node)

def planner_node(state: AgentState):
    print(f"--- Planner: Organizing tasks for {state['ticker']} ---")
    return {}

workflow.add_node("planner", planner_node)
workflow.set_entry_point("planner")

workflow.add_node("critic", critic_node)
workflow.add_node("publisher", publisher_node)
workflow.add_node("analyst", analyst_node)

workflow.add_edge("planner", "news_agent")
workflow.add_edge("planner", "data_agent")

workflow.add_edge("news_agent", "analyst")
workflow.add_edge("data_agent", "analyst")

workflow.add_edge("analyst", "critic")

workflow.add_conditional_edges(
    "critic",
    should_continue,
    {
        "analyst": "analyst",
        END: "publisher"
    }
)

workflow.add_edge("publisher", END)

app = workflow.compile()

def lambda_handler(event, context):
    """
    AWS Lambda Entry Point.
    event: The JSON payload sent by EventBridge.
    context: Runtime info(time remaining, etc).
    """
    start = time.time()
    # Extract ticker from event, or default to NVDA for testing
    portfolio = event.get("portfolio", ["NVDA"])

    print(f"Lambda invoked for ticker: {portfolio}")

    results = []

    for ticker in portfolio:
        try:
            init_state = {"ticker": ticker}
            out = app.invoke(init_state)
            results.append(f"{ticker}: Success")
        except Exception as e:
            print(f"Error processing {ticker}: {str(e)}")
            results.append(f"{ticker}: Failed")

    full_text = str(results)
    est_tokens = len(full_text.split())*1.3

    log_metrics(ticker, start, results, est_tokens * 0.8, est_tokens * 0.2) # 80/20 split

    return {
        "statusCode": 200,
        "body": json.dumps(results)
    }