import streamlit as st
import asyncio
import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from mcp.types import TextContent

# Load environment variables
load_dotenv()

SERVER_URL = "http://localhost:8000/mcp/sse"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

st.set_page_config(page_title="Weather Agent (MCP + LLM)", page_icon="🤖")
st.title("🤖 Weather Agent")

if not OPENROUTER_API_KEY:
    st.error("OPENROUTER_API_KEY not found in .env")
    st.stop()

client = OpenAI(
    base_url=OPENROUTER_BASE_URL,
    api_key=OPENROUTER_API_KEY,
)

if "messages" not in st.session_state:
    st.session_state.messages = []


async def run_agent_turn(user_input: str):
    st.session_state.messages.append(
        {"role": "user", "content": user_input}
    )

    try:
        async with sse_client(SERVER_URL) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()

                tools = await session.list_tools()
                openai_tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.inputSchema,
                        },
                    }
                    for t in tools.tools
                ]

                response = client.chat.completions.create(
                    model="openai/gpt-3.5-turbo",
                    messages=st.session_state.messages,
                    tools=openai_tools,
                    tool_choice="auto",
                )

                assistant_msg = response.choices[0].message

                if assistant_msg.tool_calls:
                    st.session_state.messages.append(assistant_msg)

                    for call in assistant_msg.tool_calls:
                        args = json.loads(call.function.arguments)
                        result = await session.call_tool(call.function.name, args)

                        output = ""
                        for content in result.content:
                            if isinstance(content, TextContent):
                                output += content.text + "\n"

                        st.session_state.messages.append({
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": output
                        })

                    final_response = client.chat.completions.create(
                        model="openai/gpt-3.5-turbo",
                        messages=st.session_state.messages,
                    )

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": final_response.choices[0].message.content
                    })
                else:
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": assistant_msg.content
                    })

    except Exception as e:
        st.error(str(e))


# UI
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask about the weather..."):
    asyncio.run(run_agent_turn(prompt))
    st.rerun()
