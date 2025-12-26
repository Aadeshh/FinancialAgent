# ADR 001: Serverless Containerization vs. EC2 for Financial Agent

## Context
We needed a deployment strategy for a daily financial agent. The system has "spiky" traffic (runs once at 6 AM) and heavy dependencies (Pandas, LangGraph).

## Decision
We chose **AWS Lambda (Container Image)** over a standard **EC2 instance**.

## Trade-off Analysis

| Feature | AWS Lambda (Chosen) | EC2 (t3.micro) |
| :--- | :--- | :--- |
| **Cost** | **$0.00/mo** (Free Tier covers <2 min/day) | ~$8.00/mo (Running 24/7 idle) |
| **Maintenance** | Zero (No OS patching) | High (Security patches, SSH management) |
| **Cold Start** | ~5s (Acceptable for background job) | Instant |
| **Complexity** | High (Requires Dockerizing & ECR) | Low (Just `git pull`) |

## Rationale
While EC2 is simpler to set up, paying for 23 hours and 58 minutes of idle time daily is inefficient. We accepted the **complexity of Dockerizing** the application to achieve **near-zero operating costs**. The 5-second cold start latency is irrelevant for an asynchronous background job triggered by EventBridge.