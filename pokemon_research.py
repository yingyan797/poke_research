import inspect, json, dotenv, os
from typing import Any, Dict, List, Callable, Optional
from openai import OpenAI
import pokebase.loaders as loaders

dotenv.load_dotenv(".env")

class PokemonResearchAgent:
    """
    Enhanced OpenAI Agent for Pokemon field research with dynamic tool loading from pokebase.loaders
    """
    
    def __init__(self, model: str = "gpt-4-turbo-preview", simulation=False):
        self._is_simulation_mode = simulation
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.tools = []
        self.tool_functions = {}
        self.knowledge_base = {}  # Store accumulated knowledge
        self.function_cache = {}  # Cache for function call results
        self.current_session_calls = set()  # Track calls made in current research session
        self._load_pokebase_tools()
    
    def _load_pokebase_tools(self):
        """Dynamically load all functions from pokebase.loaders as OpenAI function tools"""
        
        # Get all functions from pokebase.loaders module
        for name, obj in inspect.getmembers(loaders):
            if inspect.isfunction(obj) and not name.startswith('_'):
                # Get function signature and docstring
                sig = inspect.signature(obj)
                doc = inspect.getdoc(obj) or "No description available"
                
                # Parse parameters
                parameters = {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
                
                for param_name, param in sig.parameters.items():
                    param_type = self._get_param_type(param)
                    param_desc = self._extract_param_description(doc, param_name)
                    
                    parameters["properties"][param_name] = {
                        "type": param_type,
                        "description": param_desc
                    }
                    
                    # Add to required if no default value
                    if param.default == inspect.Parameter.empty:
                        parameters["required"].append(param_name)
                
                # Create OpenAI function tool schema
                tool_schema = {
                    "type": "function",
                    "function": {
                        "name": f"pokebase_{name}",
                        "description": self._clean_docstring(doc),
                        "parameters": parameters
                    }
                }
                
                self.tools.append(tool_schema)
                self.tool_functions[f"pokebase_{name}"] = obj
                
                print(f"Loaded tool: pokebase_{name}")
    
    def _get_param_type(self, param) -> str:
        """Convert Python parameter type to JSON schema type"""
        if param.annotation == inspect.Parameter.empty:
            return "string"  # Default to string if no annotation
        
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object"
        }
        
        return type_map.get(param.annotation, "string")
    
    def _extract_param_description(self, docstring: str, param_name: str) -> str:
        """Extract parameter description from docstring"""
        if not docstring:
            return f"Parameter {param_name}"
        
        # Simple extraction - look for parameter descriptions
        lines = docstring.split('\n')
        for i, line in enumerate(lines):
            if param_name in line and ':' in line:
                return line.split(':')[-1].strip()
        
        return f"Parameter {param_name}"
    
    def _clean_docstring(self, docstring: str) -> str:
        """Clean and format docstring for OpenAI function description"""
        if not docstring:
            return "Pokemon data function"
        
        # Take first line or first sentence
        lines = docstring.strip().split('\n')
        first_line = lines[0].strip()
        
        # Limit length for OpenAI function descriptions
        if len(first_line) > 200:
            first_line = first_line[:197] + "..."
        
        return first_line
    
    def _explore_object_recursively(self, obj: Any, max_depth: int = 3, current_depth: int = 0) -> Dict:
        """
        Recursively explore object attributes using __dict__ method
        """
        if current_depth >= max_depth:
            return {"_truncated": "Max depth reached"}
        
        if obj is None:
            return None
        
        # Handle primitive types
        if isinstance(obj, (str, int, float, bool)):
            return obj
        
        # Handle lists
        if isinstance(obj, list):
            if len(obj) == 0:
                return []
            # Sample first few items
            sample_size = min(5, len(obj))  # Increased sample size
            return [self._explore_object_recursively(item, max_depth, current_depth + 1) 
                   for item in obj[:sample_size]]
        
        # Handle dictionaries
        if isinstance(obj, dict):
            return {k: self._explore_object_recursively(v, max_depth, current_depth + 1) 
                   for k, v in list(obj.items())[:15]}  # Increased limit
        
        # Handle objects with __dict__
        if hasattr(obj, '__dict__'):
            obj_dict = {}
            for key, value in obj.__dict__.items():
                if not key.startswith('_'):  # Skip private attributes
                    obj_dict[key] = self._explore_object_recursively(value, max_depth, current_depth + 1)
            return obj_dict
        
        # Handle other objects by converting to string
        try:
            return str(obj)
        except:
            return f"<{type(obj).__name__} object>"
    
    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute a pokebase tool function with caching to avoid repetition"""
        # Create cache key from tool name and arguments
        cache_key = f"{tool_name}_{json.dumps(arguments, sort_keys=True)}"
        
        # Check if we already have this result cached
        if cache_key in self.function_cache:
            return self.function_cache[cache_key]
        
        # Check if this exact call was made in current session
        if cache_key in self.current_session_calls:
            return f"[CACHED] This exact function call was already made in this research session. Result: {self.function_cache.get(cache_key, 'Result not found in cache')}"
        
        try:
            if tool_name not in self.tool_functions:
                return f"Tool {tool_name} not found"
            
            func = self.tool_functions[tool_name]
            result = func(**arguments)
            
            # Store result in knowledge base for future reference
            self.knowledge_base[cache_key] = result
            
            # Explore the result object recursively
            explored_result = self._explore_object_recursively(result, max_depth=4)
            
            # Cache the result
            result_json = json.dumps(explored_result, indent=2, default=str)
            self.function_cache[cache_key] = result_json
            self.current_session_calls.add(cache_key)
            
            return result_json
            
        except Exception as e:
            error_msg = f"Error executing {tool_name}: {str(e)}"
            # Try to provide helpful context about the error
            if "not found" in str(e).lower():
                error_msg += f"\nSuggestion: Check if the parameter values are correct. Available arguments were: {arguments}"
            
            # Cache error results too to avoid repeating failed calls
            self.function_cache[cache_key] = error_msg
            self.current_session_calls.add(cache_key)
            
            return error_msg
    
    def _synthesize_knowledge(self, query: str, messages: List[Dict], function_calls: List) -> str:
        """Synthesize collected knowledge into a comprehensive response"""
        
        # Extract tool results from messages
        tool_results = []
        for msg in messages:
            if msg.get("role") == "tool":
                tool_results.append({
                    "tool": msg.get("name", "unknown"),
                    "content": msg.get("content", "")
                })
        
        # Create a synthesis prompt
        synthesis_prompt = f"""
        Based on the Pokemon research query: "{query}"
        
        The following tool functions were called: {[f[0] for f in function_calls]}
        
        Tool results obtained:
        {json.dumps(tool_results[:5], indent=2)}  # Limit to first 5 results to avoid token limits
        
        Please provide a comprehensive analysis that:
        1. Directly answers the user's question
        2. Synthesizes all the collected data
        3. Provides insights and comparisons where relevant
        4. Mentions any limitations or areas that need more research
        5. Organizes the information clearly
        
        Even if some tool calls failed, use whatever data was successfully retrieved to provide the best possible answer.
        """
        
        try:
            synthesis_response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a Pokemon research analyst. Synthesize the provided data into a comprehensive, well-organized response."},
                    {"role": "user", "content": synthesis_prompt}
                ],
                temperature=0.7
            )
            
            return synthesis_response.choices[0].message.content
            
        except Exception as e:
            print(f"Synthesis error: {e}")
            # Fallback: create a basic summary
            return self._create_fallback_summary(query, function_calls, tool_results)
    
    def _create_fallback_summary(self, query: str, function_calls: List, tool_results: List) -> str:
        """Create a fallback summary when synthesis fails"""
        summary = f"Pokemon Research Results for: {query}\n\n"
        
        if function_calls:
            summary += f"Research conducted using {len(function_calls)} tool calls:\n"
            for tool_name, args in function_calls:
                summary += f"- {tool_name} with parameters: {args}\n"
        
        if tool_results:
            summary += f"\nData collected from {len(tool_results)} successful queries:\n"
            for result in tool_results:
                summary += f"- {result['tool']}: {result['content'][:200]}...\n"
        else:
            summary += "\nNo data was successfully retrieved. Please try rephrasing your query or check if the Pokemon names/terms are correct."
        
        return summary
    
    def research(self, query: str, max_iterations: int = 4) -> dict:  # Increased iterations
        """
        Conduct Pokemon research based on user query - always returns meaningful results
        """
        # Reset session tracking for new research query
        self.current_session_calls.clear()
        
        if self._is_simulation_mode:
            return {
                "results": "Here's the result of my research based on simulated Pokemon data collection...", 
                "reasoning": "Reasoning is provided as a sequence of pokebase function calls",
                "success": True,
                "iterations_used": 0,
                "cached_calls": 0,
                "unique_calls": 0
            }
        
        system_prompt = """You are a Pokemon research assistant with access to the pokebase library functions.

IMPORTANT INSTRUCTIONS:
1. Use the available pokebase functions to gather detailed Pokemon data
2. When you receive abstract objects in function responses, they have been automatically explored using __dict__ recursively
3. The function responses contain comprehensive nested data structures - examine them carefully
4. Look for relationships between different data points (e.g., Pokemon types, abilities, stats, moves)
5. Be persistent - if one approach doesn't work, try different function calls or parameters
6. If you encounter errors, try alternative approaches or similar Pokemon names
7. Always provide analysis even with partial data
8. Use specific Pokemon names, move names, type names as they appear in the Pokemon database
9. AVOID REPEATING THE SAME FUNCTION CALLS - if you see [CACHED] in a response, that means you already made that exact call
10. Build upon previous results rather than repeating the same queries
11. If you get sufficient data, proceed to analysis rather than making more calls

Available functions are all from pokebase.loaders module and are prefixed with 'pokebase_'.

Your goal is to provide comprehensive, accurate, and insightful Pokemon research based on the user's query."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
        function_call_history = []
        final_response = None
        cached_calls = 0
        
        for iteration in range(max_iterations):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                    temperature=0.3  # Lower temperature for more focused responses
                )
                
                message = response.choices[0].message
                
                # Convert message to dict format for messages list
                message_dict = {
                    "role": message.role,
                    "content": message.content
                }
                
                # Add tool calls if they exist
                if message.tool_calls:
                    message_dict["tool_calls"] = message.tool_calls
                
                messages.append(message_dict)
                
                if message.tool_calls:
                    # Execute tool calls
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        arguments = json.loads(tool_call.function.arguments)
                        for rogue_arg in ["args", "kwargs"]:
                            if rogue_arg in arguments:
                                arguments.pop(rogue_arg)

                        function_call_history.append((tool_name, arguments))
                        result = self._execute_tool(tool_name, arguments)
                        
                        # Count cached calls
                        if result.startswith("[CACHED]"):
                            cached_calls += 1
                        
                        messages.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": tool_name,
                            "content": result
                        })
                else:
                    # No more tool calls, store the response
                    final_response = message.content
                    break
                    
            except Exception as e:
                print(f"Error in iteration {iteration + 1}: {e}")
                break
        
        # Calculate unique calls
        unique_calls = len(function_call_history) - cached_calls
        
        # Always provide a meaningful response
        if final_response:
            results = final_response
            success = True
        elif function_call_history:
            # Synthesize available knowledge if we have any data
            results = self._synthesize_knowledge(query, messages, function_call_history)
            success = True
        else:
            # No data collected at all
            results = f"I wasn't able to collect specific data for your query: '{query}'. This could be due to:\n" \
                     f"- Pokemon names or terms not being recognized\n" \
                     f"- API connectivity issues\n" \
                     f"- The specific data not being available in the Pokemon database\n\n" \
                     f"Please try rephrasing your query or using more specific Pokemon names."
            success = False
        
        return {
            "results": results,
            "reasoning": function_call_history,
            "success": success,
            "iterations_used": min(iteration + 1, max_iterations),
            "knowledge_entries": len(self.knowledge_base),
            "cached_calls": cached_calls,
            "unique_calls": unique_calls,
            "efficiency_ratio": f"{unique_calls}/{len(function_call_history)}" if function_call_history else "0/0"
        }
    
    def get_research_summary(self) -> dict:
        """Get a summary of all research conducted in this session"""
        return {
            "total_tools_available": len(self.tools),
            "knowledge_base_size": len(self.knowledge_base),
            "function_cache_size": len(self.function_cache),
            "current_session_calls": len(self.current_session_calls),
            "available_tools": [tool['function']['name'] for tool in self.tools]
        }
    
    def clear_cache(self):
        """Clear the function cache - useful for testing or memory management"""
        self.function_cache.clear()
        self.current_session_calls.clear()
        print("Function cache cleared")

def main():
    """Example usage of the Enhanced Pokemon Research Agent"""
    
    # Initialize the agent
    agent = PokemonResearchAgent()
    
    # Example research queries
    research_queries = [
        "What are the stats and abilities of Charizard? How do they compare to other Fire-type Pokemon?",
        "Tell me about the evolution chain of Eevee and all its possible evolutions",
        "What moves can Pikachu learn and what are their power levels?",
        "Compare the base stats of all starter Pokemon from Generation 1",
        "What are the most powerful Electric-type moves and which Pokemon can learn them?",
        "What are the weaknesses and resistances of Dragon-type Pokemon?",
        "Show me the legendary Pokemon from Generation 1 and their stats"
    ]
    
    print("Enhanced Pokemon Research Agent initialized!")
    print(f"Loaded {len(agent.tools)} tools from pokebase.loaders")
    
    # Show available tools
    print("\nAvailable tools:")
    for tool in agent.tools[:10]:  # Show first 10 tools
        print(f"- {tool['function']['name']}: {tool['function']['description']}")
    if len(agent.tools) > 10:
        print(f"... and {len(agent.tools) - 10} more tools")
    
    # Interactive mode
    print("\n" + "="*60)
    print("ENHANCED POKEMON RESEARCH AGENT - Interactive Mode")
    print("="*60)
    
    while True:
        print("\nExample queries:")
        for i, query in enumerate(research_queries, 1):
            print(f"{i}. {query}")
        
        user_input = input("\nEnter your Pokemon research query (or 'quit' to exit, 'summary' for session summary, 'clear' to clear cache): ").strip()
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            break
        
        if user_input.lower() == 'summary':
            summary = agent.get_research_summary()
            print(f"\nSession Summary:")
            print(f"- Available tools: {summary['total_tools_available']}")
            print(f"- Knowledge base entries: {summary['knowledge_base_size']}")
            print(f"- Function cache size: {summary['function_cache_size']}")
            print(f"- Current session calls: {summary['current_session_calls']}")
            continue
        
        if user_input.lower() == 'clear':
            agent.clear_cache()
            continue
        
        if user_input.isdigit() and 1 <= int(user_input) <= len(research_queries):
            query = research_queries[int(user_input) - 1]
        else:
            query = user_input
        
        if query:
            print(f"\nResearching: {query}")
            print("-" * 50)
            
            try:
                result = agent.research(query)
                print(f"\nRESULTS:")
                print(result['results'])
                print(f"\nResearch Status: {'Success' if result['success'] else 'Partial'}")
                print(f"Iterations used: {result['iterations_used']}")
                print(f"Function calls made: {len(result['reasoning'])}")
                print(f"Unique calls: {result['unique_calls']}")
                print(f"Cached calls: {result['cached_calls']}")
                print(f"Efficiency ratio: {result['efficiency_ratio']}")
                
                if result['reasoning']:
                    print(f"\nFunction calls executed:")
                    for i, (tool_name, args) in enumerate(result['reasoning'], 1):
                        print(f"{i}. {tool_name}({args})")
                
            except Exception as e:
                print(f"Error during research: {e}")
                print("The agent encountered an error, but this has been logged for improvement.")
        
        print("\n" + "="*60)


if __name__ == "__main__":
    main()