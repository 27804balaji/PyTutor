import streamlit as st
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from tutor import invoke_tutor  # ✅ Import this instead of `app`

import uuid
from chat_db import init_db

init_db()

# Streamlit setup
st.set_page_config(page_title="PyTutor", page_icon="📘")
st.title("👨‍🏫 PyTutor – Ask Me About PyTorch or Python")

# Initialize session state
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        SystemMessage(content=(
            "You are PyTutor, a friendly expert tutor for PyTorch and Python. "
            "Greet users, answer questions only related to Python or PyTorch, and "
            "avoid answering general knowledge."
        ))
    ]

if "greeted" not in st.session_state:
    with st.chat_message("assistant"):
        st.markdown("👋 Hello! I'm PyTutor. Ask me anything about PyTorch or Python.")
    st.session_state.greeted = True

# Display existing messages
for msg in st.session_state.chat_history:
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.markdown(msg.content)
    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            st.markdown(msg.content)

# Input box
if prompt := st.chat_input("Ask me about PyTorch or Python..."):
    user_msg = HumanMessage(content=prompt)
    st.session_state.chat_history.append(user_msg)
    with st.chat_message("user"):
        st.markdown(prompt)

    # ✅ Use invoke_tutor instead of app.invoke
    response = invoke_tutor(st.session_state.thread_id, prompt)

    ai_msg = AIMessage(content=response)
    st.session_state.chat_history.append(ai_msg)
    with st.chat_message("assistant"):
        st.markdown(response)
