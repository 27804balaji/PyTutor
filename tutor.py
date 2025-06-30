from typing import TypedDict, List
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from dotenv import load_dotenv

import uuid
from chat_db import init_db, save_message, load_history


load_dotenv()
init_db()

# === Agent State ===
class AgentState(TypedDict):
    messages: List[BaseMessage]
    question_type: str
    processed_output: str

# === LLM Setup ===
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

# === Nodes ===
def generate_greeting(state: AgentState) -> AgentState:
    greeting_input = state["messages"][-1].content 

    prompt = ChatPromptTemplate.from_template(
        "You are PyTutor, a friendly AI tutor who specializes in PyTorch and Python. "
        "A user greeted you with:\n\n\"{greeting}\"\n\n"
        "Reply with a warm and context-aware greeting. Stay in character as a tutor. "
        "If the greeting includes time (e.g., 'good morning'), respond appropriately. "
        "Avoid answering non-Python or non-PyTorch questions."
    )

    full_prompt = prompt.format(greeting=greeting_input)
    response = llm.invoke(full_prompt)
    state["processed_output"] = response.content
    return state

def question_classifier(state: AgentState) -> AgentState:
    msg = state["messages"][-1].content.lower()
    greetings = ["hello", "hi", "hey", "greetings"]

    if any(greet in msg for greet in greetings):
        state["question_type"] = "greeting"
    elif "code" in msg or "implement" in msg or "error" in msg or "fix" in msg:
        state["question_type"] = "code"
    else:
        state["question_type"] = "explanation"
    return state


def generate_explanation(state: AgentState) -> AgentState:
    chat_history = "\n".join([
        f"User: {m.content}" if isinstance(m, HumanMessage) else f"Tutor: {m.content}"
        for m in state["messages"] 
        if isinstance(m, (HumanMessage, AIMessage))
        ])
    question = state["messages"][-1].content
    prompt = ChatPromptTemplate.from_template(
    "You are PyTutor, a helpful tutor for PyTorch and Python. Here's the conversation so far:\n{history}\n\nCurrent Question:\n{question}\n\nPlease respond accordingly."
    )
    full_prompt = prompt.format(history=chat_history, question=question)

    response = llm.invoke(full_prompt)
    state["processed_output"] = response.content
    return state

def generate_code(state: AgentState) -> AgentState:
    chat_history = "\n".join([
        f"User: {m.content}" if isinstance(m, HumanMessage)
        else f"Tutor: {m.content}"
        for m in state["messages"] if isinstance(m, (HumanMessage, AIMessage))
    ])
    question = state["messages"][-1].content

    fix_keywords = ["fix", "error", "bug", "issue", "debug"]
    is_fix_request = any(word in question.lower() for word in fix_keywords)

    if is_fix_request:
        prompt = ChatPromptTemplate.from_template(
            "You are PyTutor, a Python expert. Based on this conversation:\n{history}\n\n"
            "The user is asking you to help fix some buggy code or error message:\n{question}\n\n"
            "Please provide a corrected version of the code with explanation if needed."
        )
    else:
        prompt = ChatPromptTemplate.from_template(
            "You are PyTutor, a helpful tutor for PyTorch and Python. Here's the conversation so far:\n{history}\n\n"
            "Current Question:\n{question}\n\nPlease respond accordingly."
        )

    full_prompt = prompt.format(history=chat_history, question=question)
    response = llm.invoke(full_prompt)
    state["processed_output"] = response.content
    return state


def router(state: AgentState) -> str:
    return "code" if state["question_type"] == "code" else "explanation"

def handle_chitchat(state: AgentState) -> AgentState:
    user_message = state["messages"][-1].content

    prompt = ChatPromptTemplate.from_template(
        "You're PyTutor, a friendly AI tutor for PyTorch and Python. The user said:\n\n"
        "\"{message}\"\n\n"
        "Respond politely and warmly as a tutor would during a casual moment. "
        "You don’t need to teach here, just acknowledge or continue the conversation naturally."
    )

    full_prompt = prompt.format(message=user_message)
    response = llm.invoke(full_prompt)
    state["processed_output"] = response.content
    return state

def check_relevance(state: AgentState) -> AgentState:
    user_input = state["messages"][-1].content.strip()

    prompt = ChatPromptTemplate.from_template(
        """
You are PyTutor, a helpful tutor for PyTorch and Python only.

Classify the user's message into one of these categories:
- greeting → for greetings like "hello", "hi", "good morning"
- code → only if it's Python or PyTorch code help
- explanation → only if it's about Python or PyTorch concepts
- chitchat → if it's small talk like "okay", "thanks", "great"
- irrelevant → if it's about other programming languages (C, Java, C++, etc.) or unrelated topics

Examples:
- "Can you help me write a for loop in Python?" → code
- "What is backpropagation in PyTorch?" → explanation
- "Fix this C++ error" → irrelevant
- "What's the capital of France?" → irrelevant
- "Thanks!" → chitchat
- "Good morning" → greeting

Now classify this:
"{user_input}"
Only reply with one word: greeting, code, explanation, chitchat, or irrelevant.
"""
    )

    result = llm.invoke(prompt.format(user_input=user_input)).content.strip().lower()

    valid = {"greeting", "code", "explanation", "chitchat", "irrelevant"}
    qtype = result if result in valid else "irrelevant"
    state["question_type"] = qtype

    if qtype == "irrelevant":
        state["processed_output"] = (
            "I'm here to help strictly with Python, PyTorch, and Python-based deep learning. "
            "Please ask a question related to those topics."
        )

    return state


def relevance_router(state: AgentState) -> str:
    qtype = state["question_type"]
    if qtype == "greeting":
        return "generate_greeting"
    elif qtype == "code":
        return "generate_code"
    elif qtype == "explanation":
        return "generate_explanation"
    elif qtype == "chitchat":
        return "handle_chitchat"
    else:
        return "end_irrelevant"



# === Graph Setup ===
graph = StateGraph(AgentState)

graph.add_node("check_relevance", check_relevance)
graph.add_node("question_classifier", question_classifier)
graph.add_node("generate_code", generate_code)
graph.add_node("generate_explanation", generate_explanation)
graph.add_node("end_irrelevant", lambda state: state)
graph.add_node("generate_greeting", generate_greeting)  
graph.add_node("handle_chitchat", handle_chitchat)

# Conditional edges
graph.add_conditional_edges(
    "check_relevance", relevance_router, {
        "generate_greeting": "generate_greeting",
        "generate_code": "generate_code",
        "generate_explanation": "generate_explanation",
        "handle_chitchat": "handle_chitchat",
        "end_irrelevant": "end_irrelevant"
    }
)

graph.add_edge("generate_greeting", END)         
graph.add_edge("generate_code", END)
graph.add_edge("generate_explanation", END)
graph.add_edge("end_irrelevant", END)

graph.set_entry_point("check_relevance")
app = graph.compile()

# === System Prompt ===
system_prompt = SystemMessage(content=(
    "You are PyTutor, an expert tutor strictly for Python programming, including PyTorch and Python-based deep learning.\n"
    "You MUST ONLY answer questions that are exclusively about Python, PyTorch, or Python deep learning.\n"
    "If a question is about any other programming language (e.g., C, Java, C++, JavaScript, etc.) or any unrelated topic "
    "(general knowledge, politics, history, geography, etc.), you MUST NOT provide any answer.\n"
    "Instead, respond exactly with:\n"
    "'I'm here to help strictly with Python, PyTorch, and Python-based deep learning. "
    "Please ask a question related to those topics.'\n"
    "Do not provide any partial answers, code snippets, explanations, or suggestions about other languages or topics.\n"
    "Always be concise, clear, polite, and supportive."
))


thread_id = str(uuid.uuid4())
print("📌 Session Thread ID:", thread_id)
print("👋 Welcome to PyTutor! Ask me anything about PyTorch or Python.")

save_message(thread_id, role="system", content=system_prompt.content)


def invoke_tutor(thread_id: str, user_input: str) -> str:
    """
    Handles a single turn of conversation:
    1. Save user input.
    2. Invoke LangGraph app with full chat history.
    3. Save assistant response.
    4. Return response to UI.
    """

    try:
        save_message(thread_id, role="user", content=user_input)

        chat_history = load_history(thread_id)
        input_state = {"messages": chat_history}
        result = app.invoke(input_state)

        reply = result.get("processed_output", "⚠️ No response generated.")
        save_message(thread_id, role="assistant", content=reply)

        return reply
    
    except Exception as e:
        error_msg = f"⚠️ Error: {str(e)}"
        print("[ERROR]", error_msg)
        return error_msg




