import os
import json
import re
from pathlib import Path
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

# ---------------------------------------------------------
# 1. APPLICATION CONFIGURATION
# ---------------------------------------------------------

load_dotenv()

st.set_page_config(
    page_title="ResolveIQ - Smart Customer Support",
    page_icon="🎧",
    layout="wide"
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MEMORY_FILE = DATA_DIR / "memory.json"

DATA_DIR.mkdir(exist_ok=True)

CUSTOMERS = {
    "CUST-1001": {
        "name": "Asha Mehta",
        "email": "asha@example.com",
        "plan": "Premium",
        "issue": "Payment deducted but order not confirmed"
    },
    "CUST-1002": {
        "name": "Ravi Kumar",
        "email": "ravi@example.com",
        "plan": "Standard",
        "issue": "Unable to log in"
    },
    "CUST-1003": {
        "name": "Mina Shah",
        "email": "mina@example.com",
        "plan": "Business",
        "issue": "Refund not received"
    }
}

# ---------------------------------------------------------
# 2. LOCAL MEMORY DATABASE
# ---------------------------------------------------------

def load_memory():
    """Load saved customer memories from JSON."""

    if not MEMORY_FILE.exists():
        return {}

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        return data if isinstance(data, dict) else {}

    except (json.JSONDecodeError, OSError):
        return {}


def save_memory(data):
    """Save customer memories safely."""

    temporary_file = MEMORY_FILE.with_suffix(".tmp")

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

    temporary_file.replace(MEMORY_FILE)


def add_local_memory(customer_id, content, category="conversation"):
    """Store one memory for a customer."""

    database = load_memory()

    if customer_id not in database:
        database[customer_id] = []

    entry = {
        "content": content,
        "category": category,
        "created_at": datetime.now().isoformat(timespec="seconds")
    }

    database[customer_id].append(entry)
    save_memory(database)


def get_local_memories(customer_id):
    """Return all memories for one customer."""

    database = load_memory()
    return database.get(customer_id, [])


def search_local_memories(customer_id, query, limit=5):
    """Find memories containing words related to the query."""

    memories = get_local_memories(customer_id)

    words = {
        word.lower()
        for word in re.findall(r"[a-zA-Z0-9]+", query)
        if len(word) > 2
    }

    scored = []

    for memory in memories:
        content = memory.get("content", "")
        content_words = set(
            word.lower()
            for word in re.findall(r"[a-zA-Z0-9]+", content)
        )

        score = len(words.intersection(content_words))

        if score > 0:
            scored.append((score, memory))

    scored.sort(key=lambda item: item[0], reverse=True)

    if scored:
        return [item[1] for item in scored[:limit]]

    return memories[-limit:]


# ---------------------------------------------------------
# 3. HINDSIGHT MEMORY CONNECTION
# ---------------------------------------------------------

HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY", "").strip()
HINDSIGHT_BASE_URL = os.getenv(
    "HINDSIGHT_BASE_URL",
    "https://api.hindsight.vectorize.io"
).strip()

HINDSIGHT_BANK_ID = os.getenv(
    "HINDSIGHT_BANK_ID",
    "resolveiq-support"
).strip()


@st.cache_resource
def get_hindsight_client():
    """Connect to Hindsight when an API key is configured."""

    if not HINDSIGHT_API_KEY:
        return None

    try:
        from hindsight_client import Hindsight

        client = Hindsight(
            base_url=HINDSIGHT_BASE_URL,
            api_key=HINDSIGHT_API_KEY
        )

        try:
            client.create_bank(
                bank_id=HINDSIGHT_BANK_ID,
                name="ResolveIQ Customer Support",
                background=(
                    "Customer support memory bank. "
                    "Remember customer issues, preferences, "
                    "past tickets and successful resolutions."
                )
            )
        except Exception:
            # The bank may already exist.
            pass

        return client

    except Exception as error:
        st.session_state["hindsight_connection_error"] = str(error)
        return None


def hindsight_retain(customer_id, customer_name, content):
    """Save customer information to Hindsight."""

    client = get_hindsight_client()

    if client is None:
        return False

    try:
        client.retain(
            bank_id=HINDSIGHT_BANK_ID,
            content=(
                f"Customer ID: {customer_id}\n"
                f"Customer name: {customer_name}\n"
                f"Information: {content}"
            ),
            context="ResolveIQ customer support interaction"
        )
        return True

    except Exception as error:
        st.session_state["hindsight_operation_error"] = str(error)
        return False


def hindsight_recall(customer_id, query):
    """Retrieve relevant memories from Hindsight."""

    client = get_hindsight_client()

    if client is None:
        return []

    try:
        result = client.recall(
            bank_id=HINDSIGHT_BANK_ID,
            query=(
                f"Find memories only about customer {customer_id}. "
                f"Question: {query}"
            )
        )

        return [
            item.text
            for item in result.results
            if hasattr(item, "text")
        ]

    except Exception as error:
        st.session_state["hindsight_operation_error"] = str(error)
        return []


def hindsight_reflect(customer_id, customer_name, query):
    """Ask Hindsight to generate an answer using stored memories."""

    client = get_hindsight_client()

    if client is None:
        return None

    try:
        result = client.reflect(
            bank_id=HINDSIGHT_BANK_ID,
            query=(
                f"You are ResolveIQ, a professional customer support agent.\n"
                f"Customer ID: {customer_id}\n"
                f"Customer name: {customer_name}\n"
                f"Customer question: {query}\n\n"
                "Use relevant past customer memories to answer. "
                "Be empathetic, concise and accurate. "
                "Never invent refunds, transactions or completed actions. "
                "If information is missing, ask the customer for it."
            )
        )

        return result.text

    except Exception as error:
        st.session_state["hindsight_operation_error"] = str(error)
        return None


# ---------------------------------------------------------
# 4. LOCAL CUSTOMER SUPPORT AGENT
# ---------------------------------------------------------

def generate_local_response(customer, query, memories):
    """Generate a useful response without an external AI API."""

    name = customer["name"]
    lower_query = query.lower()

    memory_text = "\n".join(
        item.get("content", "")
        for item in memories
    ).lower()

    if any(word in lower_query for word in [
        "previous", "last time", "earlier", "before",
        "history", "remember", "old issue"
    ]):
        if memories:
            details = "\n".join(
                "- " + item.get("content", "")
                for item in memories[-5:]
            )

            return (
                f"Hello {name}, I checked the information "
                "saved from your previous support conversations.\n\n"
                "Here is what I found:\n"
                f"{details}\n\n"
                "Would you like me to help you continue with "
                "one of these issues?"
            )

        return (
            f"Hello {name}, I do not have any previous support "
            "conversation saved yet. Please tell me about the "
            "issue and I will save the details for future support."
        )

    if any(word in lower_query for word in [
        "payment", "paid", "deducted", "order", "transaction"
    ]):
        return (
            f"Hello {name}, I understand that you are facing "
            "a payment or order-related problem.\n\n"
            "Please share your order ID and payment reference "
            "number. I can record the details and help you "
            "check the next steps.\n\n"
            "I will not mark a payment as successful until "
            "it has been verified."
        )

    if any(word in lower_query for word in [
        "refund", "money back", "return"
    ]):
        return (
            f"Hello {name}, I understand your concern about "
            "the refund.\n\n"
            "Please provide your order ID and refund reference "
            "if available. I can record the issue and help "
            "you track the next steps."
        )

    if any(word in lower_query for word in [
        "login", "log in", "password", "account", "sign in"
    ]):
        return (
            f"Hello {name}, I can help with your account access.\n\n"
            "Please check that your email address is correct "
            "and try the password reset option. Never share "
            "your password or OTP with anyone.\n\n"
            "If the problem continues, tell me the exact "
            "error message you see."
        )

    if "resolved" in lower_query or "fixed" in lower_query:
        return (
            f"Thank you, {name}. I can record that this issue "
            "has been resolved. Please confirm whether you "
            "need any additional help."
        )

    if memories:
        previous = "\n".join(
            "- " + item.get("content", "")
            for item in memories[-3:]
        )

        return (
            f"Hello {name}, thank you for contacting ResolveIQ.\n\n"
            "I checked your saved support history:\n"
            f"{previous}\n\n"
            "I will use this context to help you. "
            "Could you share a little more detail about "
            "the problem you are facing now?"
        )

    return (
        f"Hello {name}, welcome to ResolveIQ customer support!\n\n"
        "I am here to help with payments, orders, refunds "
        "and account access.\n\n"
        "Please describe your issue. I will save the details "
        "so that you do not have to repeat the same information "
        "in future conversations."
    )


# ---------------------------------------------------------
# 5. PROCESS CUSTOMER MESSAGE
# ---------------------------------------------------------

def process_message(customer_id, message):
    customer = CUSTOMERS[customer_id]
    customer_name = customer["name"]

    # Retrieve memories from both systems.
    local_memories = search_local_memories(
        customer_id,
        message
    )

    cloud_memories = hindsight_recall(
        customer_id,
        message
    )

    # Try Hindsight reflection first.
    answer = hindsight_reflect(
        customer_id,
        customer_name,
        message
    )

    if answer:
        answer = answer.strip()
        memory_source = "Hindsight"
    else:
        answer = generate_local_response(
            customer,
            message,
            local_memories
        )

        memory_source = "Local JSON memory"

    # Save the customer message.
    add_local_memory(
        customer_id,
        f"Customer said: {message}",
        "customer_message"
    )

    hindsight_retain(
        customer_id,
        customer_name,
        f"Customer said: {message}"
    )

    # Save the agent response.
    add_local_memory(
        customer_id,
        f"ResolveIQ replied: {answer}",
        "agent_response"
    )

    hindsight_retain(
        customer_id,
        customer_name,
        f"ResolveIQ replied: {answer}"
    )

    return answer, memory_source, cloud_memories


# ---------------------------------------------------------
# 6. SAMPLE CUSTOMER HISTORY
# ---------------------------------------------------------

def load_sample_history(customer_id):
    customer = CUSTOMERS[customer_id]
    name = customer["name"]

    sample_messages = [
        (
            f"{name} reported that a payment was deducted "
            "but the order confirmation was not received."
        ),
        (
            f"{name} contacted support again and shared "
            "that the issue was still being investigated."
        ),
        (
            f"{name} prefers clear updates and does not "
            "want to repeat the same issue."
        )
    ]

    for message in sample_messages:
        add_local_memory(
            customer_id,
            message,
            "sample_history"
        )

        hindsight_retain(
            customer_id,
            name,
            message
        )


# ---------------------------------------------------------
# 7. USER INTERFACE
# ---------------------------------------------------------

st.title("🎧 ResolveIQ")
st.subheader("AI Customer Support Agent That Learns From Every Ticket")

st.write(
    "ResolveIQ remembers customer issues, recalls previous "
    "conversations and helps support teams provide more "
    "personalized service."
)

# Sidebar
st.sidebar.title("Customer Dashboard")

customer_id = st.sidebar.selectbox(
    "Select a customer",
    list(CUSTOMERS.keys()),
    format_func=lambda value: (
        f"{CUSTOMERS[value]['name']} ({value})"
    )
)

customer = CUSTOMERS[customer_id]

if st.session_state.get("active_customer") != customer_id:
    st.session_state["active_customer"] = customer_id
    st.session_state["chat_history"] = []

st.sidebar.divider()

st.sidebar.write("### Customer Information")
st.sidebar.write(f"**Name:** {customer['name']}")
st.sidebar.write(f"**Email:** {customer['email']}")
st.sidebar.write(f"**Plan:** {customer['plan']}")
st.sidebar.write(f"**Known issue:** {customer['issue']}")

# Memory status
st.sidebar.divider()
st.sidebar.write("### Memory Status")

if HINDSIGHT_API_KEY:
    hindsight_client = get_hindsight_client()

    if hindsight_client:
        st.sidebar.success("Hindsight connected")
    else:
        st.sidebar.warning("Hindsight unavailable; using local memory")
else:
    st.sidebar.info("Local memory mode")

local_memories = get_local_memories(customer_id)

st.sidebar.metric(
    "Saved local memories",
    len(local_memories)
)

# Sample data button
if st.sidebar.button(
    "Load sample customer history",
    use_container_width=True
):
    load_sample_history(customer_id)
    st.sidebar.success("Sample history saved.")
    st.rerun()

# Clear local memories button
if st.sidebar.button(
    "Clear this customer's local memory",
    use_container_width=True
):
    database = load_memory()
    database[customer_id] = []
    save_memory(database)
    st.session_state["chat_history"] = []
    st.sidebar.success("Local memory cleared.")
    st.rerun()

# Main screen
left, right = st.columns([2, 1])

with left:
    st.markdown("### 💬 Customer Support Chat")

    chat_area = st.container()

    with chat_area:
        history = st.session_state.get("chat_history", [])

        for item in history:
            with st.chat_message(item["role"]):
                st.markdown(item["content"])

    user_message = st.chat_input(
        "Type the customer's question here..."
    )

    if user_message:
        st.session_state["chat_history"].append({
            "role": "user",
            "content": user_message
        })

        with st.spinner("ResolveIQ is checking customer memory..."):
            answer, memory_source, cloud_memories = process_message(
                customer_id,
                user_message
            )

        st.session_state["chat_history"].append({
            "role": "assistant",
            "content": answer
        })

        st.rerun()

with right:
    st.markdown("### 🧠 Customer Memory")

    st.caption(
        "Information retained from previous conversations."
    )

    local_memories = get_local_memories(customer_id)

    if local_memories:
        for memory in reversed(local_memories[-10:]):
            with st.expander(
                memory.get("category", "Memory").replace("_", " ").title()
            ):
                st.write(memory.get("content", ""))
                st.caption(memory.get("created_at", ""))

    else:
        st.info(
            "No memories saved yet. Start a conversation "
            "or load sample history."
        )

    st.divider()

    st.markdown("### 📊 Support Insights")

    st.metric(
        "Total saved interactions",
        len(local_memories)
    )

    resolved_count = sum(
        1 for item in local_memories
        if "resolved" in item.get("content", "").lower()
    )

    st.metric(
        "Interactions mentioning resolution",
        resolved_count
    )

    st.caption(
        "These are memory-based demo metrics, not verified "
        "business performance statistics."
    )

# Footer
st.divider()

st.caption(
    "ResolveIQ | Customer Support Memory Agent | "
    "Local JSON memory with optional Hindsight integration"
)