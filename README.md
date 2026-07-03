# AI Government Scheme Checker

A Flask web app scaffold for an AI-powered government scheme eligibility checker.

## Features
- User auth (register, login, password reset, profile)
- Natural language profile intake
- AI eligibility reasoning with RAG and agents
- Scheme recommendation, documents, reports
- Agent-based live scheme search using Serper and Groq

## Setup
1. Create a Python virtual environment.
2. Install dependencies: `pip install -r requirements.txt`
3. Set environment variables:
   - `GROQ_API_KEY`
   - `SERPER_API_KEY`
4. Start the app: `flask run`

## Agent architecture
- `crewai.py` defines agent roles and CrewAI orchestration.
- `profile_extractor` handles natural language extraction into structured profile fields.
- `eligibility_checker` evaluates eligibility and recommends schemes.
- `search_retriever` performs live web search and summarizes government scheme sources.

## Notes
This scaffold uses live CrewAI-style agent orchestration instead of a static scheme database. Scheme matching is prototype-level and depends on current web search results.