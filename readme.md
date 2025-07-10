# Pokemon Deep Research Chatbot

This is a field-specific research Chatbot application for Pokemon open-ended research questions. The main framework consists of Python Flask backend, HTML/JavaScript UI, and SQLite database. OpenAI Agents is used as the LLM engine, and Python library "pokebase" is used as knowledge resource.

## Setup application
1. In the ".env" file, put a valid OpenAI API key
2. Install all required Python libraries
3. Run app.py to launch the chatbot application
4. Create a new chat or select one from history, rename, or delete
5. Type Pokemon related questions in the text box and wait for the results and reasoning

## Key features
1. Use of official knowledge source Python library "pokebase" (https://github.com/PokeAPI/pokebase) in AI research
2. Iterative function call suggestions are made, and functions are executed based on API docstring and the relavance to user query
3. Using sentence transformers for caching previous queries with very similar meaning, to save repeated API call

## Limitations
1. No context of previous user-agent conversation is kept
2. Pokebase function calls may sometimes have error
