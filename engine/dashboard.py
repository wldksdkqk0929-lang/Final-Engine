import json
import os
from datetime import datetime

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def generate_html():
    dossier_data = load_json('Target_Dossier.json')
    order_data = load_json('Order_Book.json')
    dossier = dossier_data.get('dossier', [])
    orders = order_data if isinstance(order_data, list) else []
    
    # 통계 계산
    total_targets = len(dossier)
    engage_count = sum(1 for t in dossier if t['action'] == 'ENGAGE')
    watch_count = sum(1 for t in dossier if t['action'] == 'WATCH')
    
    # === V11.5 스타일 (Modern Fintech Dark Theme) ===
    css = """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
        
        :root {
            --bg-color: #0f172a;       /* Slate 900 */
            --card-bg: #1e293b;        /* Slate 800 */
            --text-main: #f8fafc;      /* Slate 50 */
            --text-sub: #94a3b8;       /* Slate 400 */
            --accent-green: #10b981;   /* Emerald 500 */
            --accent-yellow: #f59e0b;  /* Amber 500 */
            --accent-red: #ef4444;     /* Red 500 */
            --border-color: #334155;   /* Slate 700 */
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-main);
            font-family: 'Inter', -apple-system, sans-serif;
            margin: 0;
            padding: 20px;
            -webkit-font-smoothing: antialiased;
        }

        .container {
            max-width: 600px;
            margin: 0 auto;
        }

        /* HEADER & STATUS BAR */
        .header {
            text-align: center;
            margin-bottom: 20px;
        }
        .header h1 {
            font-size: 1.2rem;
            color: var(--accent-yellow);
            letter-spacing: 1px;
            margin: 0;
            text-transform: uppercase;
        }
        .status-bar {
            display: flex;
            justify-content: space-between;
            background: #020617;
            padding: 10px 15px;
            border-radius: 8px;
            margin-top: 10px;
            border: 1px solid var(--border-color);
            font-size: 0.8rem;
            color: var(--text-sub);
        }
        .status-item span { color: var(--text-main); font-weight: bold; }

        /* CARD DESIGN */
        .card {
            background: var(--card-bg);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            border: 1px solid var(--border-color);
            transition: transform 0.2s;
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 10px;
        }
        
        .symbol { font-size: 1.5rem; font-weight: 800; color: #fff; }
        
        .badge {
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
        }
        .badge.ENGAGE { background: rgba(16, 185, 129, 0.2); color: var(--accent-green); border: 1px solid var(--accent-green); }
        .badge.WATCH { background: rgba(245, 158, 11, 0.2); color: var(--accent-yellow); border: 1px solid var(--accent-yellow); }
        .badge.DISCARD { background: rgba(239, 68, 68, 0.2); color: var(--accent-red); border: 1px solid var(--accent-red); }

        /* SCORES GRID */
        .metrics {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 10px;
            margin-bottom: 15px;
        }
        .metric-box {
            background: #0f172a;
            padding: 8px;
            border-radius: 6px;
            text-align: center;
        }
        .metric-label { font-size: 0.65rem; color: var(--text-sub); display: block; margin-bottom: 2px; }
        .metric-val { font-size: 0.9rem; font-weight: 600; color: var(--text-main); }

        /* THESIS TEXT */
        .thesis {
            background: rgba(0,0,0,0.2);
            padding: 12px;
            border-radius: 8px;
            font-size: 0.85rem;
            line-height: 1.5;
            color: #cbd5e1;
            border-left: 3px solid var(--border-color);
        }

        /* EXECUTION ACTION */
        .action-btn {
            margin-top: 15px;
            background: var(--accent-green);
            color: #000;
            text-align: center;
            padding: 10px;
            border-radius: 8px;
            font-weight: bold;
            font-size: 0.9rem;
            box-shadow: 0 0 10px rgba(16, 185, 129, 0.4);
        }

        .footer {
            text-align: center;
            margin-top: 40px;
            font-size: 0.7rem;
            color: var(--text-sub);
            opacity: 0.5;
        }
    </style>
    """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
        <title>SNIPER V9 PRO</title>
        {css}
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Hybrid Sniper V9</h1>
                <div class="status-bar">
                    <div class="status-item">TARGETS: <span>{total_targets}</span></div>
                    <div class="status-item">ENGAGE: <span style="color:#10b981">{engage_count}</span></div>
                    <div class="status-item">WATCH: <span style="color:#f59e0b">{watch_count}</span></div>
                </div>
                <div style="font-size: 0.7rem; color: #64748b; margin-top: 5px;">
                    UPDATED: {datetime.now().strftime('%H:%M:%S')}
                </div>
            </div>
    """
    
    if not dossier:
        html += "<div class='card'><div style='text-align:center; padding:20px; color:#64748b;'>SYSTEM STANDBY / WAITING FOR DATA</div></div>"
    
    for target in dossier:
        symbol = target['symbol']
        action = target['action']
        tech = target.get('tech_score', 0)
        fund = target.get('reasoning_score', 0)
        risk = target.get('risk_level', '-')
        summary = target.get('thesis', {}).get('summary', 'No summary')
        executed = any(o['symbol'] == symbol for o in orders)
        
        # 위험도 색상 처리
        risk_color = "#ef4444" if risk == "HIGH" else "#f59e0b" if risk == "MEDIUM" else "#10b981"
        
        html += f"""
        <div class="card">
            <div class="card-header">
                <span class="symbol">{symbol}</span>
                <span class="badge {action}">{action}</span>
            </div>
            
            <div class="metrics">
                <div class="metric-box">
                    <span class="metric-label">TECH SCORE</span>
                    <span class="metric-val">{tech}</span>
                </div>
                <div class="metric-box">
                    <span class="metric-label">AI SCORE</span>
                    <span class="metric-val">{fund}</span>
                </div>
                <div class="metric-box">
                    <span class="metric-label">RISK LEVEL</span>
                    <span class="metric-val" style="color:{risk_color}">{risk}</span>
                </div>
            </div>
            
            <div class="thesis">
                {summary}
            </div>
        """
        
        if executed:
            html += f"""<div class="action-btn">⚡ $1,000 ORDER EXECUTED</div>"""
            
        html += "</div>"

    html += """
            <div class="footer">ENGINE: V9.2 / UI: SLATE-PRO / SECURE CONNECTION</div>
        </div>
    </body>
    </html>
    """
    
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("🎨 [Dashboard] V11.5 Style Upgrade Applied: index.html")

if __name__ == "__main__":
    generate_html()
