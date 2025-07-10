import inspect, json, dotenv, os
from typing import Any, Dict, List, Callable
from openai import OpenAI
import pokebase.loaders as loaders

dotenv.load_dotenv(".env")

class PokemonResearchAgent:
    """
    OpenAI Agent for Pokemon field research with dynamic tool loading from pokebase.loaders
    """
    
    def __init__(self, model: str = "gpt-4-turbo-preview", simulation=False):
        self._is_simulation_mode = simulation
        # self.client = OpenAI(api_key=os.getenv("C_OPENAI_KEY"))
        self.model = model
        self.tools = []
        self.tool_functions = {}
        # self._load_pokebase_tools()
    
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
            sample_size = min(3, len(obj))
            return [self._explore_object_recursively(item, max_depth, current_depth + 1) 
                   for item in obj[:sample_size]]
        
        # Handle dictionaries
        if isinstance(obj, dict):
            return {k: self._explore_object_recursively(v, max_depth, current_depth + 1) 
                   for k, v in list(obj.items())[:10]}  # Limit to first 10 items
        
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
        """Execute a pokebase tool function"""
        try:
            if tool_name not in self.tool_functions:
                return f"Tool {tool_name} not found"
            
            func = self.tool_functions[tool_name]
            result = func(**arguments)
            
            # Explore the result object recursively
            explored_result = self._explore_object_recursively(result)
            
            return json.dumps(explored_result, indent=2, default=str)
            
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"
    
    def research(self, query: str, max_iterations: int = 5) -> dict:
        """
        Conduct Pokemon research based on user query
        """
        if self._is_simulation_mode:
            return {"results": "Here's the result of my research ... ", 
                    "reasoning": "Reasoning is provided as a sequence of pokebase function calls"}
        
        system_prompt = """You are a Pokemon research assistant with access to the pokebase library functions.

IMPORTANT INSTRUCTIONS:
1. Use the available pokebase functions to gather detailed Pokemon data
2. When you receive abstract objects in function responses, they have been automatically explored using __dict__ recursively
3. The function responses contain comprehensive nested data structures - examine them carefully
4. Look for relationships between different data points (e.g., Pokemon types, abilities, stats, moves)
5. Provide detailed analysis and insights based on the data you retrieve
6. If you need more specific information about an object, you can call additional functions
7. Always cite the specific data sources you used in your analysis

Available functions are all from pokebase.loaders module and are prefixed with 'pokebase_'.

Your goal is to provide comprehensive, accurate, and insightful Pokemon research based on the user's query."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
        function_call_history = []
        
        for iteration in range(max_iterations):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools,
                tool_choice="auto"
            )
            
            message = response.choices[0].message
            messages.append(message)
            
            if message.tool_calls:
                # Execute tool calls
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)
                    
                    function_call_history.append((tool_name, arguments))
                    
                    result = self._execute_tool(tool_name, arguments)
                    
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": tool_name,
                        "content": result
                    })
            else:
                # No more tool calls, return the response
                return {"results": message.content, "reasoning": function_call_history}
        
        return {"results": "Research completed after maximum iterations", "reasoning": []}

def main():
    """Example usage of the Pokemon Research Agent"""
    
    # Initialize the agent (you need to provide your OpenAI API key)
    agent = PokemonResearchAgent()
    
    # Example research queries
    research_queries = [
        "What are the stats and abilities of Charizard? How do they compare to other Fire-type Pokemon?",
        "Tell me about the evolution chain of Eevee and all its possible evolutions",
        "What moves can Pikachu learn and what are their power levels?",
        "Compare the base stats of all starter Pokemon from Generation 1",
        "What are the most powerful Electric-type moves and which Pokemon can learn them?"
    ]
    
    print("Pokemon Research Agent initialized!")
    print(f"Loaded {len(agent.tools)} tools from pokebase.loaders")
    print("\nAvailable tools:")
    for tool in agent.tools:
        print(f"- {tool['function']['name']}: {tool['function']['description']}")
    
    # Interactive mode
    print("\n" + "="*60)
    print("POKEMON RESEARCH AGENT - Interactive Mode")
    print("="*60)
    
    while True:
        print("\nExample queries:")
        for i, query in enumerate(research_queries, 1):
            print(f"{i}. {query}")
        
        user_input = input("\nEnter your Pokemon research query (or 'quit' to exit): ").strip()
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            break
        
        if user_input.isdigit() and 1 <= int(user_input) <= len(research_queries):
            query = research_queries[int(user_input) - 1]
        else:
            query = user_input
        
        if query:
            print(f"\nResearching: {query}")
            print("-" * 50)
            
            try:
                result = agent.research(query)
                print(result)
            except Exception as e:
                print(f"Error during research: {e}")
        
        print("\n" + "="*60)


if __name__ == "__main__":
    main()