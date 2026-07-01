# ════════════════════════════════════════════════════════════════════
# PAPERBOX CO. — WEB APP (app.py)
# Run with: python app.py
# Then open: http://localhost:5050
# ════════════════════════════════════════════════════════════════════

import os

# Set your default API before loading the agent
os.environ["ACTIVE_API"] = "groq"

from flask import Flask, render_template_string, request, jsonify
from datetime import date as _date, datetime as _datetime
import json

# ── LOAD THE AGENT (reuses everything from inventory_agent.py) ───────
import os as _os
_script_dir = _os.path.dirname(_os.path.abspath(__file__))
_os.chdir(_script_dir)  # stay in same folder as app.py
exec(open(_os.path.join(_script_dir, "inventory_agent.py")).read())

app = Flask(__name__)

# ── UPDATE AGENT (natural language updates) ───────────────────────────
def update_agent(instruction):
    today = str(_date.today().strftime("%d-%b-%Y"))

    extraction_prompt = f"""
You are a data extractor for PaperBox Co., a box manufacturing business.
Today's date is {today}.

Extract structured data from the instruction below and return ONLY a JSON object.
No explanation, no markdown, just raw JSON.

If it is a NEW ORDER, return:
{{
  "action": "new_order",
  "date_received": "<date or today if not mentioned>",
  "customer_name": "<name>",
  "item_description": "<description>",
  "box_type": "<type or Regular if not mentioned>",
  "quantity": <number>,
  "due_date": "<due date or leave blank>",
  "priority": "<Urgent or Normal>",
  "notes": "<any other detail>"
}}

If it is a STAGE UPDATE for an existing order, return:
{{
  "action": "stage_update",
  "order_id": "<ORD-XXX>",
  "stage": "<exact stage name>",
  "stage_date": "<date or today>",
  "done_by": "<person or Manager if not mentioned>",
  "notes": "<any detail>"
}}

If it is a STOCK UPDATE, return:
{{
  "action": "stock_update",
  "date": "<date or today>",
  "category": "<category>",
  "item_name": "<item>",
  "size": "<size or ->",
  "opening_qty": 0,
  "purchased_qty": <qty if received, else 0>,
  "used_qty": <qty if used, else 0>,
  "closing_qty": 0,
  "unit": "<unit>",
  "notes": "<any detail>"
}}

If it is a NEW PURCHASE, return:
{{
  "action": "new_purchase",
  "date": "<date or today>",
  "category": "<category>",
  "item_name": "<item>",
  "size": "<size>",
  "qty": <number>,
  "unit_cost": <cost or 0>,
  "total_cost": <total or 0>,
  "supplier": "<supplier or Unknown>",
  "invoice_no": "<invoice or ->",
  "notes": "<any detail>"
}}

Instruction: {instruction}
"""

    raw = chat("You extract data and return only JSON.", extraction_prompt)

    try:
        clean = raw.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
    except Exception as e:
        return f"❌ Could not understand instruction: {e}"

    action = data.get("action")
    summary = ""

    if action == "new_order":
        existing_ids = [o.get("order_id", "") for o in orders]
        nums = [int(oid.replace("ORD-", ""))
                for oid in existing_ids
                if oid.startswith("ORD-")]
        next_num = max(nums) + 1 if nums else 1
        order_id = f"ORD-{str(next_num).zfill(3)}"

        orders_tab = gsheet.worksheet("Orders")
        orders_tab.append_row([
            order_id,
            data.get("date_received", today),
            data.get("customer_name", ""),
            "",
            data.get("item_description", ""),
            data.get("box_type", "Regular"),
            data.get("quantity", 0),
            data.get("due_date", ""),
            data.get("priority", "Normal"),
            "Received",
            _datetime.now().strftime("%d-%b-%Y %H:%M:%S"),
            data.get("notes", "")
        ])

        stages_tab = gsheet.worksheet("Order Stages")
        stages_tab.append_row([
            order_id,
            "Order Received",
            data.get("date_received", today),
            "Harshit",
            _datetime.now().strftime("%d-%b-%Y %H:%M:%S"),
            data.get("notes", "")
        ])

        summary = (
            f"✅ New order {order_id} added!\n"
            f"Customer: {data.get('customer_name')}\n"
            f"Qty: {data.get('quantity')} boxes"
        )

    elif action == "stage_update":
        stages_tab = gsheet.worksheet("Order Stages")
        stages_tab.append_row([
            data.get("order_id", ""),
            data.get("stage", ""),
            data.get("stage_date", today),
            data.get("done_by", "Manager"),
            _datetime.now().strftime("%d-%b-%Y %H:%M:%S"),
            data.get("notes", "")
        ])

        orders_tab = gsheet.worksheet("Orders")
        all_rows = orders_tab.get_all_values()
        for i, row in enumerate(all_rows):
            if row[0] == data.get("order_id"):
                orders_tab.update_cell(i + 1, 10, data.get("stage"))
                break

        summary = f"✅ {data.get('order_id')} → {data.get('stage')}"

    elif action == "stock_update":
        inv_tab = gsheet.worksheet("Inventory")
        inv_tab.append_row([
            data.get("date", today),
            data.get("category", ""),
            data.get("item_name", ""),
            data.get("size", "-"),
            data.get("opening_qty", 0),
            data.get("purchased_qty", 0),
            data.get("used_qty", 0),
            data.get("closing_qty", 0),
            data.get("unit", ""),
            _datetime.now().strftime("%d-%b-%Y %H:%M:%S"),
            data.get("notes", "")
        ])
        summary = (
            f"✅ Stock updated: {data.get('item_name')} "
            f"{data.get('size', '')}"
        )

    elif action == "new_purchase":
        purchases_tab = gsheet.worksheet("Purchases")
        purchases_tab.append_row([
            data.get("date", today),
            data.get("category", ""),
            data.get("item_name", ""),
            data.get("size", ""),
            data.get("qty", 0),
            data.get("unit_cost", 0),
            data.get("total_cost", 0),
            data.get("supplier", ""),
            data.get("invoice_no", "-"),
            _datetime.now().strftime("%d-%b-%Y %H:%M:%S"),
            data.get("notes", "")
        ])
        summary = (
            f"✅ Purchase recorded: {data.get('qty')} x "
            f"{data.get('item_name')} from {data.get('supplier')}"
        )

    else:
        return "❌ Could not determine what to update."

    reload_data()
    return summary


# ── HTML PAGE ─────────────────────────────────────────────────────────
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PaperBox Assistant</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, Arial, sans-serif; }
        body { background: #e5ddd5; height: 100vh; display: flex; flex-direction: column; }
        .header {
            background: #075e54; color: white; padding: 16px;
            font-size: 18px; font-weight: bold;
            display: flex; align-items: center; justify-content: space-between;
        }
        .header select {
            font-size: 13px; padding: 4px 8px; border-radius: 6px;
            border: none; background: white; color: #075e54;
            font-weight: normal; margin-left: 10px;
        }
        #apiStatus { font-size: 12px; font-weight: normal; margin-left: 8px; }
        .quick-buttons {
            display: flex; flex-wrap: wrap; gap: 8px; padding: 10px;
            background: #f0f0f0; border-bottom: 1px solid #ddd;
        }
        .quick-btn {
            background: white; border: 1px solid #ccc; border-radius: 16px;
            padding: 8px 14px; font-size: 13px; cursor: pointer; color: #333;
        }
        .quick-btn:active { background: #ddd; }
        .chat-area {
            flex: 1; overflow-y: auto; padding: 16px;
            display: flex; flex-direction: column; gap: 10px;
        }
        .msg {
            max-width: 80%; padding: 10px 14px; border-radius: 8px;
            font-size: 14px; line-height: 1.4; white-space: pre-wrap;
        }
        .user { background: #dcf8c6; align-self: flex-end; }
        .bot { background: white; align-self: flex-start; }
        .loading { color: #888; font-style: italic; }
        .input-area {
            display: flex; padding: 10px; background: #f0f0f0; gap: 8px;
        }
        .input-area input[type="text"] {
            flex: 1; padding: 12px; border: none; border-radius: 20px;
            font-size: 14px; outline: none;
        }
        .input-area button {
            background: #075e54; color: white; border: none;
            border-radius: 20px; padding: 12px 20px; font-size: 14px;
            cursor: pointer;
        }
        .input-area button:active { background: #054c43; }
        .receipt-btn {
            background: #25d366; color: white; border: none;
            border-radius: 20px; padding: 12px 16px; font-size: 18px;
            cursor: pointer;
        }
        .confirm-card {
            background: white; border-radius: 8px; padding: 14px;
            align-self: flex-start; max-width: 90%;
            border-left: 4px solid #25d366;
        }
        .confirm-card table { width: 100%; border-collapse: collapse; font-size: 13px; }
        .confirm-card td { padding: 5px 8px; border-bottom: 1px solid #f0f0f0; }
        .confirm-card td:first-child { color: #888; width: 38%; }
        .confirm-card input {
            width: 100%; border: 1px solid #ddd; border-radius: 4px;
            padding: 4px 6px; font-size: 13px;
        }
        .confirm-btns { display: flex; gap: 8px; margin-top: 10px; }
        .confirm-btns button {
            flex: 1; padding: 10px; border: none; border-radius: 8px;
            font-size: 14px; cursor: pointer; font-weight: bold;
        }
        .btn-confirm { background: #25d366; color: white; }
        .btn-cancel { background: #f0f0f0; color: #333; }
    </style>
</head>
<body>
    <div class="header">
        📦 PaperBox Assistant
        <select id="apiSelect" onchange="switchAPI()">
            <option value="groq">Groq</option>
            <option value="huggingface">HuggingFace</option>
            <option value="openrouter">OpenRouter</option>
        </select>
        <span id="apiStatus"></span>
    </div>

    <div class="quick-buttons">
        <div class="quick-btn" onclick="ask('What orders are pending?')">📋 Pending Orders</div>
        <div class="quick-btn" onclick="ask('What orders are overdue?')">⚠️ Overdue</div>
        <div class="quick-btn" onclick="ask('What is due this week?')">📅 This Week</div>
        <div class="quick-btn" onclick="ask('What stock do I have?')">📦 Stock Levels</div>
        <div class="quick-btn" onclick="ask('What do I need to reorder?')">🔄 Reorder Check</div>
        <div class="quick-btn" onclick="ask('List all customers and their orders')">👥 Customers</div>
    </div>

    <div class="chat-area" id="chat">
        <div class="msg bot">👋 Hi! Ask me about orders, stock, or tell me updates like "ORD-002 sent to printer". Tap 📸 to scan a receipt!</div>
    </div>

    <input type="file" id="receiptInput" accept="image/*" style="display:none" onchange="scanReceipt(this)">

    <div class="input-area">
        <button class="receipt-btn" onclick="document.getElementById('receiptInput').click()" title="Scan Receipt">📸</button>
        <input type="text" id="userInput" placeholder="Type a question or update..."
               onkeypress="if(event.key==='Enter') send()">
        <button onclick="send()">Send</button>
    </div>

    <script>
        const chat = document.getElementById('chat');
        const input = document.getElementById('userInput');

        function addMessage(text, sender) {
            const div = document.createElement('div');
            div.className = 'msg ' + sender;
            div.textContent = text;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
            return div;
        }

        function ask(text) {
            input.value = text;
            send();
        }

        async function switchAPI() {
            const select = document.getElementById('apiSelect');
            const status = document.getElementById('apiStatus');
            const newApi = select.value;
            status.textContent = '⏳ switching...';
            try {
                const response = await fetch('/switch_api', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api: newApi })
                });
                const data = await response.json();
                status.textContent = data.success ? '✅ ' + data.api : '❌ ' + data.error;
            } catch (err) {
                status.textContent = '❌ failed';
            }
        }

        async function loadCurrentAPI() {
            try {
                const response = await fetch('/current_api');
                const data = await response.json();
                document.getElementById('apiSelect').value = data.api;
                document.getElementById('apiStatus').textContent = '✅ ' + data.api;
            } catch (err) {}
        }
        loadCurrentAPI();

        async function send() {
            const text = input.value.trim();
            if (!text) return;
            addMessage(text, 'user');
            input.value = '';
            const loadingMsg = addMessage('Thinking...', 'bot loading');
            try {
                const response = await fetch('/ask', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text })
                });
                const data = await response.json();
                loadingMsg.textContent = data.reply;
                loadingMsg.className = 'msg bot';
            } catch (err) {
                loadingMsg.textContent = '❌ Error connecting to server.';
                loadingMsg.className = 'msg bot';
            }
        }

        // ── RECEIPT SCANNER ──────────────────────────────────────────
        async function scanReceipt(input) {
            if (!input.files[0]) return;
            const loadingMsg = addMessage('📸 Reading receipt... please wait', 'bot loading');

            const formData = new FormData();
            formData.append('image', input.files[0]);
            input.value = '';

            try {
                const response = await fetch('/scan_receipt', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();

                if (!result.success) {
                    loadingMsg.textContent = '❌ Could not read receipt: ' + result.error;
                    loadingMsg.className = 'msg bot';
                    return;
                }

                const d = result.data;
                const card = document.createElement('div');
                card.className = 'confirm-card';
                card.id = 'confirmCard';
                card.innerHTML = `
                    <b>📋 Receipt Scanned — Check & confirm:</b>
                    <table style="margin-top:8px">
                        <tr><td>Supplier</td><td><input id="r_supplier" value="${d.supplier||''}"></td></tr>
                        <tr><td>Invoice No</td><td><input id="r_invoice" value="${d.invoice_no||'-'}"></td></tr>
                        <tr><td>Date</td><td><input id="r_date" value="${d.date||''}"></td></tr>
                        <tr><td>Item</td><td><input id="r_item" value="${d.item_name||''}"></td></tr>
                        <tr><td>Category</td><td><input id="r_category" value="${d.category||''}"></td></tr>
                        <tr><td>Size</td><td><input id="r_size" value="${d.size||'-'}"></td></tr>
                        <tr><td>Qty</td><td><input id="r_qty" value="${d.qty||0}"></td></tr>
                        <tr><td>Unit Cost ₹</td><td><input id="r_unit_cost" value="${d.unit_cost||0}"></td></tr>
                        <tr><td>Total ₹</td><td><input id="r_total" value="${d.total_cost||0}"></td></tr>
                        <tr><td>Notes</td><td><input id="r_notes" value="${d.notes||''}"></td></tr>
                    </table>
                    <div class="confirm-btns">
                        <button class="btn-confirm" onclick="confirmReceipt()">✅ Save to Sheet</button>
                        <button class="btn-cancel" onclick="cancelReceipt()">❌ Cancel</button>
                    </div>
                `;
                loadingMsg.replaceWith(card);
                chat.scrollTop = chat.scrollHeight;

            } catch (err) {
                loadingMsg.textContent = '❌ Error scanning receipt.';
                loadingMsg.className = 'msg bot';
            }
        }

        async function confirmReceipt() {
            const data = {
                supplier:   document.getElementById('r_supplier').value,
                invoice_no: document.getElementById('r_invoice').value,
                date:       document.getElementById('r_date').value,
                item_name:  document.getElementById('r_item').value,
                category:   document.getElementById('r_category').value,
                size:       document.getElementById('r_size').value,
                qty:        parseFloat(document.getElementById('r_qty').value) || 0,
                unit_cost:  parseFloat(document.getElementById('r_unit_cost').value) || 0,
                total_cost: parseFloat(document.getElementById('r_total').value) || 0,
                notes:      document.getElementById('r_notes').value
            };

            document.getElementById('confirmCard').innerHTML = '<i>💾 Saving to Google Sheet...</i>';

            try {
                const response = await fetch('/confirm_receipt', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                const card = document.getElementById('confirmCard');
                if (result.success) {
                    card.style.borderColor = '#075e54';
                    card.innerHTML = result.message;
                } else {
                    card.innerHTML = '❌ Error: ' + result.error;
                }
            } catch (err) {
                document.getElementById('confirmCard').innerHTML = '❌ Error saving.';
            }
        }

        function cancelReceipt() {
            const card = document.getElementById('confirmCard');
            if (card) card.remove();
        }
    </script>
</body>
</html>
"""

# ── ROUTES ─────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template_string(HTML_PAGE)

@app.route("/current_api")
def current_api():
    return jsonify({"api": os.environ.get("ACTIVE_API", "groq")})

@app.route("/switch_api", methods=["POST"])
def switch_api():
    global client
    new_api = request.json.get("api", "").strip().lower()
    valid_apis = ["groq", "huggingface", "openrouter"]
    if new_api not in valid_apis:
        return jsonify({"success": False, "error": "Invalid API name"})
    try:
        os.environ["ACTIVE_API"] = new_api
        client = setup_client()
        return jsonify({"success": True, "api": new_api})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/ask", methods=["POST"])
def ask():
    user_message = request.json.get("message", "")
    decision_prompt = (
        "Reply with ONLY one word: 'question' if this is asking for information, "
        "or 'update' if this is reporting something that happened "
        "(like an order received, stock used, stage change, purchase made).\n\n"
        f"Message: {user_message}"
    )
    try:
        decision = chat(
            "You classify messages as 'question' or 'update'. Reply with only one word.",
            decision_prompt
        )
        decision = (decision or "").strip().lower()
    except Exception:
        decision = "question"

    try:
        if "update" in decision:
            reply = update_agent(user_message)
        else:
            reply = run_agent_silent(user_message)
    except Exception as e:
        reply = f"❌ Error: {e}"

    return jsonify({"reply": reply})


# ── RECEIPT SCANNER ROUTES ─────────────────────────────────────────────

@app.route("/scan_receipt", methods=["POST"])
def scan_receipt():
    import base64
    today = _date.today().strftime("%d-%b-%Y")

    if "image" not in request.files:
        return jsonify({"success": False, "error": "No image uploaded"})

    image_file = request.files["image"]
    image_data = base64.b64encode(image_file.read()).decode("utf-8")
    mime_type = image_file.content_type or "image/jpeg"

    prompt = f"""You are reading a purchase receipt or invoice for PaperBox Co., a box manufacturing company.
Today's date is {today}.

Extract the purchase details and return ONLY a JSON object, no explanation, no markdown:
{{
  "date": "<date on receipt or today if not found>",
  "supplier": "<supplier or shop name>",
  "invoice_no": "<invoice or bill number or ->",
  "item_name": "<item purchased>",
  "category": "<category: Paper/Ink/Packaging/Other>",
  "size": "<size if mentioned or ->",
  "qty": <quantity as number>,
  "unit_cost": <cost per unit as number or 0>,
  "total_cost": <total amount as number or 0>,
  "notes": "<any other useful detail>"
}}"""

    try:
        from groq import Groq
        groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        response = groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime_type};base64,{image_data}"
                    }}
                ]
            }]
        )
        raw = response.choices[0].message.content
        clean = raw.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/confirm_receipt", methods=["POST"])
def confirm_receipt():
    today = _date.today().strftime("%d-%b-%Y")
    data = request.json
    try:
        purchases_tab = gsheet.worksheet("Purchases")
        purchases_tab.append_row([
            data.get("date", today),
            data.get("category", ""),
            data.get("item_name", ""),
            data.get("size", "-"),
            data.get("qty", 0),
            data.get("unit_cost", 0),
            data.get("total_cost", 0),
            data.get("supplier", ""),
            data.get("invoice_no", "-"),
            _datetime.now().strftime("%d-%b-%Y %H:%M:%S"),
            data.get("notes", "")
        ])
        reload_data()
        return jsonify({
            "success": True,
            "message": f"✅ Purchase saved!\n{data.get('qty')} x {data.get('item_name')}\nSupplier: {data.get('supplier')}\nTotal: ₹{data.get('total_cost')}"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ── SILENT VERSION OF run_agent ────────────────────────────────────────
def run_agent_silent(question):
    tool = pick_tool(question)
    if tool:
        result = tool["function"]()
        data_for_ai = str(result)
    else:
        data_for_ai = "No specific tool data available."

    answer = chat(
        "You are PaperBox Co.'s business assistant for a small box manufacturing company. "
        "Give a clear, concise answer using the data provided. "
        "Use ₹ for currency. Be direct and helpful. "
        "If data is empty or missing, say so clearly.",
        f"Question: {question}\n\nData:\n{data_for_ai}"
    )
    return answer or "Sorry, I couldn't generate a response."


# ── RUN THE SERVER ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n🚀 PaperBox Web App starting...")
    print("📱 Open in browser: http://localhost:5050")
    print("📱 On phone (same WiFi): http://YOUR-COMPUTER-IP:5050")
    print("\nPress CTRL+C to stop the server.\n")
    app.run(host="0.0.0.0", port=5050, debug=False)
