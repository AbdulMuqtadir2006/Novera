import os
from dotenv import load_dotenv
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode, tools_condition

load_dotenv()

# --- 1. Point ChatOpenAI at OpenRouter instead of OpenAI ---
llm = ChatOpenAI(
    model="openrouter/free",  # auto-picks a working free model for you
    openai_api_key=os.getenv("OPENROUTER_API_KEY"),
    openai_api_base="https://openrouter.ai/api/v1",
)

# --- 2. Define a tool ---
@tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"It's sunny in {city}, 28°C"

tools = [get_weather]
llm_with_tools = llm.bind_tools(tools)

# --- 3. State ---
class State(TypedDict):
    messages: Annotated[list, add_messages]

# --- 4. Node ---
def call_model(state: State):
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

# --- 5. Build graph ---
graph_builder = StateGraph(State)
graph_builder.add_node("agent", call_model)
graph_builder.add_node("tools", ToolNode(tools))

graph_builder.set_entry_point("agent")
graph_builder.add_conditional_edges("agent", tools_condition)
graph_builder.add_edge("tools", "agent")

graph = graph_builder.compile()

# --- 6. Run it ---
result = graph.invoke({"messages": [{"role": "user", "content": "What's the weather in Muscat?"}]})
print(result["messages"][-1].content)