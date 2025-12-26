import time
import csv
import os
from datetime import datetime

# Pricing 
INPUT_COST_PER_1M = 0.25
OUTPUT_COST_PER_1M = 2.00

def log_metrics(ticker, start_time, result, tokens_in, tokens_out):
    duration = round(time.time() - start_time, 2)
    
    # Calculate Cost
    cost = ((tokens_in / 1_000_000) * INPUT_COST_PER_1M) + \
           ((tokens_out / 1_000_000) * OUTPUT_COST_PER_1M)
    
    # Did it succeed? (Check if we got a final report)
    success = 1 if "final_report" in result and result["final_report"] else 0
    
    # The Row Data
    row = [
        datetime.now().isoformat(),
        ticker,
        duration,
        tokens_in,
        tokens_out,
        round(cost, 6),
        success
    ]
    
    # Append to CSV
    file_exists = os.path.isfile("metrics_log.csv")
    with open("metrics_log.csv", "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Ticker", "Latency(s)", "InputTokens", "OutputTokens", "Cost($)", "Success"])
        writer.writerow(row)
        
    print(f"📊 Run Logged: ${cost:.5f} | {duration}s")