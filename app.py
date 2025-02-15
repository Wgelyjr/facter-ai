from flask import Flask, request, jsonify, render_template
import requests
from bs4 import BeautifulSoup
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

SEARXNG_URL = os.getenv('SEARXNG_URL', 'http://localhost:8080')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'mistral')


def query_ollama(prompt, model=OLLAMA_MODEL):
    """Send a prompt to Ollama and get the response."""
    try:
        print(f"Sending request to Ollama API at {OLLAMA_URL}")
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False
            }
        )
        print(f"Ollama API response status: {response.status_code}")
        # First 500 chars
        print(f"Ollama API response content: {response.text[:500]}")
        response_json = response.json()
        return response_json['response']
    except Exception as e:
        print(f"Error in query_ollama: {str(e)}")
        raise


def generate_search_query(user_input):
    """Use AI to generate an effective search query from user input."""
    prompt = f"""
    Convert the following fact-checking request into a clear, focused search query.
    Focus on the key elements that need verification.
    
    Request: {user_input}
    
    Provide only the search query, nothing else.
    """
    return query_ollama(prompt)


def search_searxng(query):
    """Search using SearxNG and return results."""
    try:
        print(f"Sending request to SearxNG at {SEARXNG_URL}")
        response = requests.get(
            f"{SEARXNG_URL}/search",
            params={
                'q': query,
                'format': 'json',
                'engines': 'google,bing,duckduckgo',
                'language': 'en'
            }
        )
        print(f"SearxNG response status: {response.status_code}")
        # First 500 chars
        print(f"SearxNG response content: {response.text[:500]}")
        response_json = response.json()
        return response_json['results']
    except Exception as e:
        print(f"Error in search_searxng: {str(e)}")
        raise


def extract_webpage_content(url):
    """Fetch and extract main content from a webpage."""
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get text content
        text = soup.get_text(separator=' ', strip=True)

        # Basic text cleaning
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = ' '.join(lines)

        return text[:8000]  # Limit content length
    except Exception as e:
        print(f"Error extracting content from {url}: {str(e)}")
        return f"Error extracting content: {str(e)}"


def analyze_relevance(content, user_input):
    """Use AI to analyze content relevance to the user's query."""
    prompt = f"""
    Analyze how relevant the following content is to fact-checking this claim:
    
    Claim to check: {user_input}
    
    Content: {content}
    
    Rate relevance from 0-10 and explain why. Provide response in JSON format:
    {{
        "score": <0-10>,
        "explanation": "<explanation>"
    }}
    """
    try:
        response = query_ollama(prompt)
        # First 200 chars
        print(f"Relevance analysis response: {response[:200]}")
        return json.loads(response)
    except json.JSONDecodeError as e:
        print(f"JSON parsing error in analyze_relevance: {str(e)}")
        print(f"Raw response: {response}")
        return {"score": 0, "explanation": f"Error parsing relevance analysis: {str(e)}"}
    except Exception as e:
        print(f"Error in analyze_relevance: {str(e)}")
        return {"score": 0, "explanation": f"Error in relevance analysis: {str(e)}"}


def generate_fact_check_response(user_input, sources):
    """Generate final fact-check response based on sources."""
    sources_text = "\n\n".join([
        f"Source {i+1}:\n{source['content']}"
        for i, source in enumerate(sources)
    ])

    prompt = f"""
    Fact check the following claim using the provided sources:
    
    Claim: {user_input}
    
    Sources:
    {sources_text}
    
    Provide a detailed analysis of the claim's veracity, citing specific information from the sources.
    Format your response in markdown with clear sections:
    
    1. Verdict (True/False/Partially True/Unverified)
    2. Explanation
    3. Key Evidence
    4. Sources Used
    """

    return query_ollama(prompt)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/fact-check', methods=['POST'])
def fact_check():
    try:
        print("Received fact-check request")
        data = request.get_json()
        print(f"Request data: {data}")
        user_input = data.get('claim', '')
        num_sources = data.get('num_sources', 3)

        # Generate search query
        print("Generating search query...")
        search_query = generate_search_query(user_input)
        print(f"Generated search query: {search_query}")

        # Get search results
        print("Fetching search results...")
        search_results = search_searxng(search_query)
        print(f"Found {len(search_results)} search results")

        # Process each result
        processed_sources = []
        print("Processing search results...")
        for i, result in enumerate(search_results):
            try:
                print(f"Processing result {i+1}: {result['url']}")
                content = extract_webpage_content(result['url'])
                print(f"Analyzing relevance for result {i+1}")
                relevance = analyze_relevance(content, user_input)

                processed_sources.append({
                    'url': result['url'],
                    'title': result['title'],
                    'content': content,
                    'relevance': relevance
                })
            except Exception as e:
                print(f"Error processing result {i+1}: {str(e)}")
                continue

        if not processed_sources:
            return jsonify({'error': 'No valid sources found'}), 500

        # Sort by relevance and take top N
        processed_sources.sort(
            key=lambda x: x['relevance']['score'], reverse=True)
        top_sources = processed_sources[:num_sources]

        print("Generating final response...")
        # Generate final response
        response = generate_fact_check_response(user_input, top_sources)

        result = {
            'result': response,
            'sources': [{'url': s['url'], 'title': s['title'], 'relevance': s['relevance']}
                        for s in top_sources]
        }
        print("Sending response back to client")
        return jsonify(result)
    except Exception as e:
        print(f"Error in fact_check endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
