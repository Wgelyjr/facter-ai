# Self-hosted AI fact checking pipeline - inspired by factually.co

## Getting Started

### Prerequisites:
 - Ollama instance
 - SearXNG instance, with JSON and requests enabled
 - Docker (optional)

### Clone, Build, & Run:

#### Docker:
```
# clone
git clone git@github.com:Wgelyjr/facter-ai.git
# build
cd facter-ai
docker build . -t facter
# run
docker run -e OLLAMA_URL=http://your.host:port -e OLLAMA_MODEL=llama3.2:1b -e SEARXNG_URL=http://your.searxng:port -p 5000:5000 facter
```

#### Non-Docker:
(note - I don't test without docker)
```
# clone
git clone git@github.com:Wgelyjr/facter-ai.git

# "build"
cd facter-ai
python -m venv venv
source venv/bin/activate
pip install -r src/requirements.txt

# run

gunicorn --bind 0.0.0.0:5000 --workers 4 app:app --timeout 600
```

## What's using it like?

It's fine. Lots of kinks to work out - sometimes the JSON output of an LLM will cause issues, sometimes the final result will have completely lost the plot. I suspect both are issues with the LLMs I've elected to test with.

YMMV. This is an experimental project.

## Why did you build this?

It sounded cool.
