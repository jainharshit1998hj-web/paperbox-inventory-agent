import json
import math
import os
import gspread

# ─── LOAD .env ────────────────────────────────────────────────────────────────
with open("inventory_agent/.env", "r") as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            # Only set if not already set by Cell 3
            if key not in os.environ:
                os.environ[key] = value.strip('"')

# ─── GOOGLE SHEETS CONNECTION ─────────────────────────────────────────────────
SHEET_ID = "1QuvXFYZ0cGXm5NQNYI0y6p6TV5bqYcPSTmhe03laTiI"

gc     = gspread.service_account(filename="inventory_agent/credentials.json")
gsheet = gc.open_by_key(SHEET_ID)

def load_sheet(tab_name):
    return gsheet.worksheet(tab_name).get_all_records()

# ─── LOAD LIVE DATA FROM GOOGLE SHEETS ───────────────────────────────────────
inventory    = load_sheet("Inventory")
purchases    = load_sheet("Purchases")
items_master = load_sheet("Items Master")
orders       = load_sheet("Orders")
order_stages = load_sheet("Order Stages")
customers    = load_sheet("Customers")

print("✅ Live data loaded from Google Sheets!")

# ─── API CLIENT SETUP ─────────────────────────────────────────────────────────
def setup_client():
    api = os.environ.get("ACTIVE_API", "groq")
    if api == "groq":
        from groq import Groq
        return Groq(api_key=os.environ.get("GROQ_API_KEY"))
    elif api == "huggingface":
        from huggingface_hub import InferenceClient
        return InferenceClient(
            model="Qwen/Qwen2.5-7B-Instruct",
            token=os.environ.get("HF_API_TOKEN")
        )
    elif api == "openrouter":
        from openai import OpenAI
        return OpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1"
        )
    else:
        raise ValueError(f"Unknown API: '{api}'. Choose: groq, huggingface, openrouter")

client = setup_client()
print(f"✅ Connected to: {os.environ.get('ACTIVE_API', 'groq').upper()}")
    
# ─── CHAT FUNCTION ────────────────────────────────────────────────────────────
def chat(system_prompt, user_message, max_tokens=300):
    api = os.environ.get("ACTIVE_API", "groq")
    if api == "groq":
        r = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message}
            ]
        )
        return r.choices[0].message.content
    elif api == "huggingface":
        r = client.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message}
            ],
            max_tokens=max_tokens
        )
        return r.choices[0].message.content
    elif api == "openrouter":
        r = client.chat.completions.create(
            model="meta-llama/llama-3.3-70b-instruct:free",
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message}
            ]
        )
        return r.choices[0].message.content
    
# ─── BUSINESS LOGIC TOOLS ─────────────────────────────────────────────────────

def get_current_stock():
    """Returns latest closing stock for all items"""
    seen = {}
    for row in inventory:
        key = f"{row['category']} | {row['item_name']} | {row['size']}"
        seen[key] = row['closing_qty']
    result = ""
    for item, qty in seen.items():
        result += f"{item}: {qty}\n"
    return result if result else "No inventory data found."

def get_pending_orders():
    """Returns all orders that are not dispatched"""
    pending = [o for o in orders
               if str(o['status']).lower() != 'dispatched']
    if not pending:
        return "No pending orders."
    result = ""
    for o in pending:
        result += (
            f"ORD: {o['order_id']} | {o['customer_name']} | "
            f"{o['quantity']} {o['box_type']} boxes | "
            f"Due: {o['due_date']} | "
            f"Status: {o['status']} | "
            f"Priority: {o['priority']}\n"
        )
    return result

def get_low_stock():
    """Returns items below reorder point"""
    seen = {}
    for row in inventory:
        key = f"{row['category']} | {row['item_name']} | {row['size']}"
        seen[key] = row['closing_qty']

    reorder = {}
    for item in items_master:
        key = f"{item['category']} | {item['item_name']} | {item['size']}"
        reorder[key] = item['reorder_point']

    result = ""
    for key, qty in seen.items():
        rp = reorder.get(key, 0)
        if int(qty) <= int(rp):
            result += f"⚠️  {key}: {qty} left (reorder at {rp})\n"
    return result if result else "✅ All stock levels are fine."

def get_order_history():
    """Returns full stage history for all orders"""
    if not order_stages:
        return "No order stage data found."
    result = ""
    for s in order_stages:
        result += (
            f"{s['order_id']} | {s['stage']} | "
            f"{s['stage_date']} | {s['done_by']}"
            + (f" | {s['notes']}" if s.get('notes') else "") + "\n"
        )
    return result

def get_all_orders():
    """Returns all orders with full details"""
    if not orders:
        return "No orders found."
    result = ""
    for o in orders:
        result += (
            f"{o['order_id']} | {o['customer_name']} | "
            f"{o['item_description']} | Qty: {o['quantity']} | "
            f"Due: {o['due_date']} | Status: {o['status']} | "
            f"Priority: {o['priority']}\n"
        )
    return result

def get_all_customers():
    """Returns customer list"""
    if not customers:
        return "No customers found."
    result = ""
    for c in customers:
        result += (
            f"{c['customer_id']} | {c['customer_name']} | "
            f"{c['phone']} | {c['city']} | "
            f"Payment: {c['payment_terms']}\n"
        )
    return result

def get_purchases_summary():
    """Returns all purchases made"""
    if not purchases:
        return "No purchases found."
    result = ""
    for p in purchases:
        result += (
            f"{p['date']} | {p['category']} | {p['item_name']} "
            f"{p['size']} | Qty: {p['qty']} | "
            f"Total: ₹{p['total_cost']} | "
            f"Supplier: {p['supplier']} | Invoice: {p['invoice_no']}\n"
        )
    return result

def get_overdue_orders():
    """Returns orders past their due date and not yet dispatched"""
    from datetime import datetime
    
    today = datetime.now()
    overdue = []
    
    for o in orders:
        if str(o['status']).lower() == 'dispatched':
            continue
        due_str = o.get('due_date', '')
        if not due_str:
            continue
        try:
            due = datetime.strptime(due_str, "%d-%b-%Y")
            if due < today:
                days_late = (today - due).days
                overdue.append(
                    f"{o['order_id']} | {o['customer_name']} | "
                    f"{o['item_description']} | "
                    f"Due: {due_str} | "
                    f"{days_late} days overdue | "
                    f"Status: {o['status']}"
                )
        except ValueError:
            continue
    
    if not overdue:
        return "✅ No overdue orders."
    return "\n".join(overdue)

def get_this_week_priorities():
    """Returns orders due within the next 7 days, sorted by urgency"""
    from datetime import datetime, timedelta
    
    today    = datetime.now()
    week_end = today + timedelta(days=7)
    upcoming = []
    
    for o in orders:
        if str(o['status']).lower() == 'dispatched':
            continue
        due_str = o.get('due_date', '')
        if not due_str:
            continue
        try:
            due = datetime.strptime(due_str, "%d-%b-%Y")
            if today <= due <= week_end:
                days_left = (due - today).days
                upcoming.append({
                    'text': (
                        f"{o['order_id']} | {o['customer_name']} | "
                        f"{o['item_description']} | "
                        f"Due in {days_left} days ({due_str}) | "
                        f"Priority: {o['priority']} | "
                        f"Status: {o['status']}"
                    ),
                    'days_left': days_left,
                    'priority': o['priority']
                })
        except ValueError:
            continue
    
    if not upcoming:
        return "No orders due in the next 7 days."
    
    # Sort: Urgent first, then by days left
    upcoming.sort(key=lambda x: (x['priority'] != 'Urgent', x['days_left']))
    return "\n".join(item['text'] for item in upcoming)


def get_stock_vs_orders():
    """Shows current stock levels and pending order count"""
    stock = {}
    for row in inventory:
        key = f"{row['category']} | {row['item_name']} | {row['size']}"
        stock[key] = int(row['closing_qty'])

    reorder = {}
    for item in items_master:
        key = f"{item['category']} | {item['item_name']} | {item['size']}"
        reorder[key] = int(item['reorder_point'])

    pending_count = len([o for o in orders
                          if str(o['status']).lower() != 'dispatched'])

    result = f"Pending orders: {pending_count}\n\n"
    result += "Current stock levels (vs reorder point):\n"
    for key, qty in stock.items():
        rp = reorder.get(key, 0)
        flag = "⚠️ LOW - reorder soon" if qty <= rp else "✅ OK"
        result += f"  {key}: {qty} in stock — {flag} (reorder at {rp})\n"

    result += (
        "\nNote: To check if stock covers specific order requirements, "
        "add a 'material_required' column to the Orders tab."
    )
    return result


def get_customer_summary(customer_name=None):
    """Returns order history and stats for a specific customer or all customers"""
    summary = {}
    
    for o in orders:
        name = o['customer_name']
        if name not in summary:
            summary[name] = {'count': 0, 'total_qty': 0, 'orders': []}
        summary[name]['count'] += 1
        summary[name]['total_qty'] += int(o['quantity'])
        summary[name]['orders'].append(
            f"{o['order_id']} ({o['quantity']} units, {o['status']})"
        )
    
    result = ""
    for name, data in summary.items():
        result += (
            f"{name}: {data['count']} orders, "
            f"{data['total_qty']} total units\n"
            f"   Orders: {', '.join(data['orders'])}\n"
        )
    
    return result if result else "No customer order data found."

# ─── TOOL REGISTRY ────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name":        "current_stock",
        "description": "Use when asked about stock levels, how much is left, closing inventory, what we have in stock",
        "function":    get_current_stock,
    },
    {
        "name":        "pending_orders",
        "description": "Use when asked about pending orders, what is due, what needs to be produced, urgent orders",
        "function":    get_pending_orders,
    },
    {
        "name":        "low_stock",
        "description": "Use when asked what to reorder, what is running low, what needs purchasing, reorder suggestions",
        "function":    get_low_stock,
    },
    {
        "name":        "order_history",
        "description": "Use when asked about a SPECIFIC order ID's production stages, timeline of one order, what stage an order is at",
        "function":    get_order_history,
    },
    {
        "name":        "all_orders",
        "description": "Use when asked to list all orders, show all customer orders, full order list",
        "function":    get_all_orders,
    },
    {
        "name":        "customers",
        "description": "Use when asked about customers, customer list, who are our clients, customer details",
        "function":    get_all_customers,
    },
    {
        "name":        "purchases",
        "description": "Use when asked about purchases made, what was bought, supplier history, purchase records",
        "function":    get_purchases_summary,
    },
    {
        "name":        "overdue_orders",
        "description": "Use when asked about overdue orders, late orders, orders past due date, what's behind schedule",
        "function":    get_overdue_orders,
    },
    {
        "name":        "this_week_priorities",
        "description": "Use when asked what's due this week, upcoming deadlines, what to prioritize, urgent work",
        "function":    get_this_week_priorities,
    },
    {
        "name":        "stock_vs_orders",
        "description": "Use when asked if we have enough stock for orders, stock needed for production, material check",
        "function":    get_stock_vs_orders,
    },
    {
        "name":        "customer_summary",
        "description": "Use when asked to LIST customers, total orders PER customer, which customers we have, customer names and their order counts, business summary BY customer",
        "function":    get_customer_summary,
    },
]

# ─── AGENT LOOP ───────────────────────────────────────────────────────────────
def pick_tool(question):
    tool_list = "\n".join(
        f"{i+1}. {t['name']}: {t['description']}"
        for i, t in enumerate(TOOLS)
    )
    try:
        response = chat(
            "You are a tool selector. Reply ONLY with the tool name, nothing else. "
            "If no tool fits, reply: none\n\nAvailable tools:\n" + tool_list,
            "Question: " + question
        )
        if response is None:
            print("⚠️  API returned nothing. Try switching API in Cell 3.")
            return None
        chosen = response.strip().lower()
        for t in TOOLS:
            if t["name"] in chosen:
                return t
        return None
    except Exception as e:
        print(f"⚠️  Tool picker error: {e}")
        return None

def reload_data():
    """Call this to refresh data from Google Sheets without restarting"""
    global inventory, purchases, items_master, orders, order_stages, customers
    inventory    = load_sheet("Inventory")
    purchases    = load_sheet("Purchases")
    items_master = load_sheet("Items Master")
    orders       = load_sheet("Orders")
    order_stages = load_sheet("Order Stages")
    customers    = load_sheet("Customers")
    print("✅ Data refreshed from Google Sheets!")

def run_agent(question):
    print(f"\n🤔 Question: {question}")
    print("─" * 50)

    # Step 1: pick the right tool
    tool = pick_tool(question)

    # Step 2: run the tool
    if tool:
        print(f"🔧 Using tool: {tool['name']}")
        result = tool["function"]()
        data_for_ai = str(result)
    else:
        print("🔧 No tool matched — answering from knowledge")
        data_for_ai = "No specific tool data available."

    # Step 3: generate a friendly answer
    answer = chat(
        "You are PaperBox Co.'s business assistant for a small box manufacturing company. "
        "Give a clear, concise answer using the data provided. "
        "Use ₹ for currency. Be direct and helpful. "
        "If data is empty or missing, say so clearly.",
        f"Question: {question}\n\nData:\n{data_for_ai}"
    )

    print(f"\n📦 Answer:\n{answer}")
    print("─" * 50)
    return answer

print("\n🚀 PaperBox Agent ready! Data loaded from Google Sheets.")
print('💬 Try: run_agent("What orders are pending?")')
print('🔄 To refresh data: reload_data()')
