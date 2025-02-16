from flask import Flask, request, jsonify, render_template, Response
import time
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

def query_ollama(prompt, model=OLLAMA_MODEL, stream=False):
    """Send a prompt to Ollama and get the response."""
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": stream
            },
            stream=stream
        )
       
        if response.status_code != 200:
            return f"Error: Ollama API returned status code {response.status_code}"
            
        if stream:
            return response
            
        response_json = response.json()
        if not response_json.get('response'):
            return "Error: No response field in Ollama API response"
            
        return response_json['response']
    except Exception as e:
        return f"Error: {str(e)}"

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
                'engines': 'google,bing',
                'language': 'en'
            }
        )
        print(f"SearxNG response content: {response.text}")
        
        if response.status_code != 200:
            raise Exception(f"SearxNG API returned status code {response.status_code}")
            
        response_json = response.json()
        if 'results' not in response_json:
            raise Exception("No results field in SearxNG API response")
            
        return response_json['results']
    except Exception as e:
        raise

def extract_webpage_content(url):
    """Fetch and extract main content from a webpage."""
    try:
        response = requests.get(url, timeout=10, headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'})
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

        # Check if response starts with "Error:"
        if response.startswith("Error:"):
            return {"score": 0, "explanation": response}
            
        parsed_response = json.loads(response)
        if not isinstance(parsed_response, dict):
            return {"score": 0, "explanation": "Invalid response format"}
            
        score = parsed_response.get('score')
        explanation = parsed_response.get('explanation')
        
        if not isinstance(score, (int, float)) or not isinstance(explanation, str):
            return {"score": 0, "explanation": "Invalid response format"}
            
        return {"score": score, "explanation": explanation}
    except json.JSONDecodeError:
        return {"score": 0, "explanation": "Error parsing relevance analysis"}
    except Exception as e:
        return {"score": 0, "explanation": f"Error in relevance analysis: {str(e)}"}

def generate_fact_check_response(user_input, sources):
    """Generate final fact-check response based on sources."""
    if not sources:
        return "Error: No sources available for fact checking"
        
    sources_text = "\n\n".join([
        f"Source {i+1}:\n{source['content']}"
        for i, source in enumerate(sources)
    ])
    
    prompt = f"""
    Fact check the following claim using the provided sources:
    
    Claim: {user_input}
    
    Sources:
    {sources_text}

    Reiterate the claim and expand its assumptions, briefly.
    Provide a detailed analysis of the claim's veracity, citing specific information from the sources.
    Format your response in markdown with clear sections:
    
    1. One sentence reiteration of the claim (removing political or charged language)
    2. Verdict (True/False/Partially True/Unverified)
    3. Explanation
    4. Key Evidence
    """
    
    response = query_ollama(prompt, stream=True)
    if isinstance(response, str) and response.startswith("Error:"):
        return "Unable to generate fact check response. " + response
        
    full_response = ""
    for line in response.iter_lines():
        if line:
            json_response = json.loads(line)
            if 'response' in json_response:
                full_response += json_response['response']
                yield {'partial_response': full_response}
    
    return full_response

@app.route('/')
def home():
    return render_template('index.html')

def generate_sse_response(data):
    """Helper function to generate SSE response"""
    return b"data: " + json.dumps(data).encode('utf-8') + b"\n\n"

@app.route('/fact-check', methods=['GET', 'POST'])
def fact_check():
    try:
        # Capture request data before entering generator
        if request.method == 'POST':
            data = request.get_json()
        else:
            data = {
                'claim': request.args.get('claim'),
                'num_sources': request.args.get('num_sources', type=int, default=3)
            }

        def generate():
            if not data or not data.get('claim'):
                yield generate_sse_response({'error': 'No claim provided'})
                return
                
            user_input = data.get('claim', '')
            if not user_input:
                yield generate_sse_response({'error': 'No claim provided'})
                return
                
            num_sources = data.get('num_sources', 3)
            if not isinstance(num_sources, int) or num_sources < 1:
                yield generate_sse_response({'error': 'Invalid number of sources'})
                return

            # Update progress: Generating search query
            yield generate_sse_response({'status': 'Generating optimized search query...'})
            search_query = generate_search_query(user_input)
            if search_query.startswith("Error:"):
                yield generate_sse_response({'error': search_query})
                return

            # Update progress: Searching
            yield generate_sse_response({'status': 'Searching for relevant sources...'})
            try:
                search_results = search_searxng(search_query)
            except Exception as e:
                yield generate_sse_response({'error': f'Search failed: {str(e)}'})
                return

            # Process results
            processed_sources = []
            for i, result in enumerate(search_results):
                try:
                    yield generate_sse_response({'status': f'Analyzing source {i+1} of {min(len(search_results), num_sources)}...'})
                    content = extract_webpage_content(result['url'])
                    relevance = analyze_relevance(content, user_input)
                    
                    processed_sources.append({
                        'url': result['url'],
                        'title': result['title'],
                        'content': content,
                        'relevance': relevance
                    })
                except Exception as e:
                    continue

                if len(processed_sources) >= num_sources:
                    break

            if not processed_sources:
                yield generate_sse_response({'error': 'No valid sources found'})
                return

            # Sort by relevance
            processed_sources.sort(key=lambda x: x['relevance']['score'], reverse=True)
            top_sources = processed_sources[:num_sources]

            # Generate final response
            yield generate_sse_response({'status': 'Generating fact-check analysis...'})
            
            # Stream the fact check response
            for partial_result in generate_fact_check_response(user_input, top_sources):
                if 'partial_response' in partial_result:
                    yield generate_sse_response({
                        'result': partial_result['partial_response'],
                        'sources': [{'url': s['url'], 'title': s['title'], 'relevance': s['relevance']} 
                                  for s in top_sources],
                        'streaming': True
                    })

            # Send completion signal
            yield generate_sse_response({
                'complete': True
            })

        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no'
            }
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
