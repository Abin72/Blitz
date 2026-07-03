import os
import json
import re
import requests
from dotenv import load_dotenv
import groq
import bs4
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv(override=True)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
SERPER_API_KEY = os.environ.get("SERPER_API_KEY")
client = None

def get_groq_client():
    global client
    if client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not configured. Set it in your environment or .env file."
            )
        client = groq.Groq(api_key=api_key)
    return client


def parse_ai_exception(exc):
    message = str(exc)
    code = getattr(exc, "code", None)
    if "quota" in message.lower() or "insufficient_quota" in message.lower() or "rate limit" in message.lower() or "429" in message:
        return {
            "error": "AI quota exceeded or billing issue. Check your plan, billing, and API key.",
            "code": code or "insufficient_quota",
            "details": message,
        }
    return {"error": message, "code": code, "details": message}


def extract_json_candidate(text):
    stack = []
    start = None
    for index, char in enumerate(text):
        if char in '{[':
            if start is None:
                start = index
            stack.append(char)
        elif char in ']}' and stack:
            opening = stack.pop()
            if (opening == '{' and char != '}') or (opening == '[' and char != ']'):
                stack = []
                start = None
                continue
            if not stack and start is not None:
                return text[start:index + 1]
    return None


def parse_json_response(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```", 2)
        if len(parts) >= 3:
            cleaned = parts[1].strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    if cleaned.startswith("{") or cleaned.startswith("["):
        try:
            return json.loads(cleaned[: cleaned.rfind(cleaned[-1]) + 1])
        except json.JSONDecodeError:
            pass
    candidate = extract_json_candidate(cleaned)
    if candidate:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError("Unable to parse JSON from assistant response.", text, 0)


def filter_official_govt_results(results):
    if not isinstance(results, dict) or "organic" not in results:
        return results
    filtered = []
    for item in results.get("organic", []):
        link = item.get("link", "") or ""
        if re.search(r"\.(gov|nic)\.(in|[a-z]{2})/|/gov\.|/nic\.in|\.gov/", link, re.IGNORECASE):
            filtered.append(item)
    if filtered:
        results = dict(results)
        results["organic"] = filtered
    return results


def normalize_list_field(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item is not None]
    if isinstance(value, dict):
        return [f"{k}: {v}" for k, v in value.items()]
    if isinstance(value, str):
        parts = [part.strip() for part in re.split(r"[\n;•\-–,]", value) if part.strip()]
        return parts
    return [value]


def normalize_scheme_entry(scheme):
    if not isinstance(scheme, dict):
        return scheme
    if "eligibility_score" not in scheme and "confidence_score" in scheme:
        scheme["eligibility_score"] = scheme["confidence_score"]
    if "required_documents" not in scheme:
        if "documents" in scheme:
            scheme["required_documents"] = scheme["documents"]
        else:
            scheme["required_documents"] = []
    scheme["required_documents"] = normalize_list_field(scheme.get("required_documents"))
    scheme["benefits"] = normalize_list_field(scheme.get("benefits") or scheme.get("benefit") or [])
    scheme["eligibility_criteria"] = normalize_list_field(scheme.get("eligibility_criteria") or scheme.get("eligibility") or scheme.get("eligibility_requirements") or [])
    scheme["application_procedure"] = scheme.get("application_procedure") or scheme.get("application_process") or scheme.get("how_to_apply") or ""
    scheme["more_info"] = scheme.get("more_info") or scheme.get("notes") or scheme.get("extra_info") or ""
    if isinstance(scheme["application_procedure"], list):
        scheme["application_procedure"] = "\n".join(str(item) for item in scheme["application_procedure"])
    if isinstance(scheme["more_info"], list):
        scheme["more_info"] = "\n".join(str(item) for item in scheme["more_info"])
    return scheme

AGENT_ROLES = {
    "profile_extractor": {
        "name": "Profile Extraction Agent",
        "role": "extractor",
        "description": "Converts user-written profile descriptions into structured JSON data for eligibility checks.",
        "system_prompt": (
            "You are a CrewAI profile extraction agent for an Indian government scheme checker. "
            "Extract age, occupation, annual income in INR, category (SC/ST/OBC/General), location/state, and land holding from the user's description. "
            "Return only valid JSON with keys: age, occupation, income, category, location, land_holding. Use null for missing values."
        ),
    },
    "eligibility_checker": {
        "name": "Eligibility Checker Agent",
        "role": "analyst",
        "description": "Evaluates a structured citizen profile and recommends applicable government schemes with reasoning and document requirements.",
        "system_prompt": (
            "You are a CrewAI eligibility checker agent. "
            "Given a structured Indian citizen profile, identify up to 10 relevant government schemes the person is likely eligible for with a confidence score above 60%. "
            "Return only valid JSON in the following format:\n"
            "{\n"
            "  \"schemes\": [\n"
            "    {\n"
            "      \"name\": \"...\",\n"
            "      \"eligibility_reason\": \"...\",\n"
            "      \"confidence_score\": 75,\n"
            "      \"required_documents\": [\"...\"],\n"
            "      \"application_link\": \"https://...\",\n"
            "      \"near_miss_criteria\": \"...\"\n"
            "    }\n"
            "  ]\n"
            "}. Use null or empty arrays if values are missing."
        ),
    },
    "search_retriever": {
        "name": "Search Retriever Agent",
        "role": "searcher",
        "description": "Performs live web search on government scheme details and summarizes authoritative results.",
        "system_prompt": (
            "You are a CrewAI web search summarizer for Indian government schemes. "
            "Use the provided search results and scraped contents to extract details. "
            "However, for well-known national/state schemes (such as Rashtriya Gokul Mission, National Livestock Mission, PM-KISAN, Animal Husbandry Infrastructure Development Fund, etc.), if the provided text lacks details, you MUST use your general knowledge to supply the real, correct, and typical eligibility criteria, benefits, and required documents. "
            "Do not return empty arrays, 'not available' text, or placeholders for well-known schemes. "
            "Return only valid JSON with keys: summary and schemes. "
            "schemes must be an array of objects with name, description, application_link, last_date, source, authoritative, eligibility_score, required_documents, benefits, eligibility_criteria, and application_procedure. "
            "If you cannot verify an application link, set it to null. "
            "eligibility_score should be a number from 0 to 100. "
            "required_documents should be a list of documents needed to apply. "
            "Do not include any non-JSON text outside the valid JSON object."
        ),
    },
}


def run_crewai_agent(agent_name, user_input):
    if agent_name not in AGENT_ROLES:
        raise ValueError(f"Unknown agent: {agent_name}")

    agent = AGENT_ROLES[agent_name]
    messages = [
        {"role": "system", "content": agent["system_prompt"]},
        {"role": "user", "content": user_input},
    ]

    client = get_groq_client()
    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=messages,
            temperature=0.2,
            max_completion_tokens=2048,
            tool_choice="none",
            disable_tool_validation=True,
        )
    except Exception as exc:
        return parse_ai_exception(exc)

    text = response.choices[0].message.content.strip()

    if agent_name == "profile_extractor":
        try:
            return parse_json_response(text)
        except json.JSONDecodeError:
            return {
                "age": None,
                "occupation": None,
                "income": None,
                "category": None,
                "location": None,
                "land_holding": None,
            }

    if agent_name == "eligibility_checker":
        if isinstance(text, dict) and text.get("error"):
            return text
        try:
            parsed = parse_json_response(text)
            if isinstance(parsed, dict):
                return parsed
            return {"schemes": parsed}
        except json.JSONDecodeError:
            return {"error": text}

    if isinstance(text, dict) and text.get("error"):
        return text

    return text


def scrape_url(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        response.raise_for_status()
        
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' not in content_type and 'application/xhtml+xml' not in content_type:
            return ""
            
        soup = bs4.BeautifulSoup(response.text, 'html.parser')
        
        # Remove unwanted layout parts
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.decompose()
            
        text = soup.get_text(separator=' ')
        
        # Clean lines
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text[:4000]
    except Exception:
        return ""


def run_crewai_search(query):
    if not SERPER_API_KEY:
        return {"error": "SERPER_API_KEY is not configured."}

    endpoints = [
        "https://google.serper.dev/search",
        "https://api.serper.dev/search",
    ]
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "q": (
            f"{query} site:gov.in OR site:nic.in OR site:gov.kerala.gov.in"
        ),
        "gl": "in",
        "hl": "en",
        "num": 10,
    }

    results = None
    last_exc = None
    for search_url in endpoints:
        try:
            response = requests.post(search_url, headers=headers, json=payload, timeout=20)
            response.raise_for_status()
            results = response.json()
            break
        except Exception as exc:
            last_exc = exc
            continue

    if results is None:
        return {"error": f"Search failed: {last_exc}"}

    results = filter_official_govt_results(results)
    organic_results = results.get("organic", []) if isinstance(results, dict) else []

    # Scrape top 2 government links (smaller content to reduce token usage)
    scraped_data = []
    scraped_count = 0
    for item in organic_results:
        if scraped_count >= 2:
            break
        link = item.get("link", "")
        if link and any(d in link.lower() for d in [".gov.in", ".nic.in", ".gov", "gov.", "nic."]):
            # skip PDFs
            if link.lower().endswith(".pdf"):
                continue
            content = scrape_url(link)
            if content:
                scraped_data.append({
                    "title": item.get("title") or "Scheme Portal",
                    "link": link,
                    "content": content[:1500],
                })
                scraped_count += 1

    # Build a compact snippet summary for the prompt
    snippets = []
    for item in organic_results[:8]:
        snippets.append({
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "snippet": item.get("snippet", ""),
        })

    # Stage 1: Parse scheme list from search snippets
    stage1_prompt = (
        "You are a JSON API. Extract Indian government schemes from the search results below.\n"
        "Return ONLY a valid JSON object (no markdown, no explanation) with this exact structure:\n"
        "{\"summary\": \"one sentence\", \"schemes\": ["
        "{\"name\": \"...\", \"description\": \"...\", \"application_link\": \"url or null\", "
        "\"source\": \"domain\", \"authoritative\": true, \"last_date\": null, \"eligibility_score\": 75, "
        "\"benefits\": [\"benefit 1\", \"benefit 2\", \"benefit 3\"], "
        "\"eligibility_criteria\": [\"criterion 1\", \"criterion 2\", \"criterion 3\"], "
        "\"required_documents\": [\"Aadhaar card\", \"PAN card\", \"Income certificate\", \"Bank passbook\", \"Passport photo\", \"Residence proof\"], "
        "\"application_procedure\": \"steps to apply\"}"
        "]}\n\n"
        "IMPORTANT: For benefits and eligibility_criteria, use your knowledge about the scheme to provide REAL, SPECIFIC information. "
        "Never use null, 'N/A', 'not available', or empty arrays for benefits and eligibility_criteria.\n\n"
        f"Search query: {query}\n"
        f"Search results: {json.dumps(snippets, indent=2)}\n"
        f"Scraped page content: {json.dumps(scraped_data, indent=2)}"
    )

    summary_text = None
    schemes = None
    human_summary = None
    try:
        client = get_groq_client()
        models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
        last_error = None

        for model in models:
            try:
                summary_response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "user", "content": stage1_prompt},
                    ],
                    temperature=0.2,
                    max_completion_tokens=4096,
                    tool_choice="none",
                    disable_tool_validation=True,
                )
                text = summary_response.choices[0].message.content.strip()
                if not text:
                    last_error = RuntimeError(f"Model {model} returned empty text.")
                    continue

                try:
                    parsed = parse_json_response(text)
                    if isinstance(parsed, dict):
                        schemes = parsed.get("schemes")
                        human_summary = parsed.get("summary")
                        if isinstance(schemes, str):
                            try:
                                schemes = parse_json_response(schemes)
                            except json.JSONDecodeError:
                                pass
                        if isinstance(schemes, dict):
                            schemes = [schemes]
                    elif isinstance(parsed, list):
                        schemes = parsed
                    summary_text = human_summary or text
                    break
                except json.JSONDecodeError as json_exc:
                    last_error = json_exc
                    continue
            except Exception as exc:
                last_error = exc
                continue

        if schemes is not None and isinstance(schemes, list):
            schemes = [normalize_scheme_entry(s) for s in schemes if isinstance(s, dict)]

            # Stage 2: Enrich missing benefits/eligibility_criteria with a targeted LLM call
            schemes_needing_enrichment = [
                s for s in schemes
                if not s.get("benefits") or not s.get("eligibility_criteria")
            ]
            if schemes_needing_enrichment:
                names = [s.get("name", "") for s in schemes_needing_enrichment]
                enrich_prompt = (
                    "You are a government scheme expert for India. "
                    "For each scheme listed below, provide the REAL benefits and eligibility criteria.\n"
                    "Return ONLY a valid JSON array (no markdown) like:\n"
                    "[{\"name\": \"exact scheme name\", \"benefits\": [\"...\", \"...\"], \"eligibility_criteria\": [\"...\", \"...\"]}]\n\n"
                    f"Schemes to enrich:\n{json.dumps(names, indent=2)}\n"
                    f"Context (search query): {query}"
                )
                try:
                    enrich_response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "user", "content": enrich_prompt}],
                        temperature=0.1,
                        max_completion_tokens=2048,
                        tool_choice="none",
                        disable_tool_validation=True,
                    )
                    enrich_text = enrich_response.choices[0].message.content.strip()
                    enrichments = parse_json_response(enrich_text)
                    if isinstance(enrichments, list):
                        enrich_map = {e.get("name"): e for e in enrichments if isinstance(e, dict)}
                        for scheme in schemes:
                            name = scheme.get("name", "")
                            enriched = enrich_map.get(name)
                            if enriched:
                                if not scheme.get("benefits") and enriched.get("benefits"):
                                    scheme["benefits"] = normalize_list_field(enriched["benefits"])
                                if not scheme.get("eligibility_criteria") and enriched.get("eligibility_criteria"):
                                    scheme["eligibility_criteria"] = normalize_list_field(enriched["eligibility_criteria"])
                except Exception:
                    pass  # enrichment is best-effort

    except Exception as exc:
        ai_error = parse_ai_exception(exc)
        summary_text = f"Unable to summarize search results: {ai_error['details']}"
        return {
            "query": query,
            "summary": summary_text,
            "raw_results": results,
            "schemes": schemes,
            "error": ai_error["error"],
            "code": ai_error.get("code"),
            "details": ai_error.get("details"),
        }

    if not schemes and isinstance(results, dict):
        organic = results.get("organic") or []
        if organic:
            schemes = []
            for item in organic:
                url = item.get("link")
                host = None
                if url:
                    try:
                        host = re.sub(r"^https?://", "", url).split("/")[0]
                    except Exception:
                        host = url
                schemes.append({
                    "name": item.get("title") or item.get("link"),
                    "description": item.get("snippet") or "No description available.",
                    "application_link": url,
                    "last_date": None,
                    "source": host,
                    "authoritative": False,
                    "eligibility_score": None,
                    "required_documents": [
                        "Aadhaar card",
                        "PAN card",
                        "Income certificate",
                        "Residence proof",
                        "Caste certificate (if applicable)",
                    ],
                    "benefits": [],
                    "eligibility_criteria": [],
                    "application_procedure": "Visit the official website for the latest application process and documents.",
                    "more_info": item.get("snippet") or "",
                })
            summary_text = summary_text or "Here are government scheme results matching your search. Click on the official links to learn more about eligibility and application details."

    return {
        "query": query,
        "summary": summary_text,
        "raw_results": results,
        "schemes": schemes,
    }


