import os
import sys

# [V13.2 HUD HTML 소스코드]
html_source = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sniper V13.2 HUD</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .market-danger-blur { filter: blur(10px); pointer-events: none; user-select: none; }
        #danger-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(20, 0, 0, 0.6); z-index: 9999; align-items: center; justify-content: center; flex-direction: column; }
        @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
        .alert-blink { animation: blink 1.5s infinite; }
    </style>
</head>
<body class="bg-gray-900 text-gray-100 font-sans min-h-screen">
    <header class="fixed top-0 left-0 w-full bg-gray-900/95 border-b border-gray-700 z-50 backdrop-blur-sm shadow-lg">
        <div class="max-w-7xl mx-auto px-4 h-14 flex justify-between items-center">
            <div class="flex items-center gap-4">
                <h1 class="text-xl font-bold tracking-tighter text-blue-500">SNIPER <span class="text-white">V13.2</span></h1>
                <div id="system-badge" class="px-2 py-0.5 rounded bg-green-900/50 border border-green-600 text-[10px] text-green-400 font-mono animate-pulse">SYSTEM ONLINE</div>
            </div>
            <div class="flex gap-3">
                <div class="flex flex-col items-end"><span class="text-[10px] text-gray-500 uppercase font-bold tracking-wider">SPY PRICE</span><span id="spy-val" class="text-sm font-bold text-blue-300 font-mono">LOADING...</span></div>
                <div class="h-8 w-px bg-gray-700 mx-1"></div>
                <div class="flex flex-col items-end"><span class="text-[10px] text-gray-500 uppercase font-bold tracking-wider">VIX INDEX</span><span id="vix-val" class="text-sm font-bold text-yellow-400 font-mono">LOADING...</span></div>
            </div>
        </div>
    </header>
    <div id="danger-overlay" class="w-full h-full">
        <h2 class="text-5xl font-black text-red-600 alert-blink tracking-widest mb-4">RED ALERT</h2>
        <p class="text-xl text-red-300 font-mono">MARKET REGIME UNSTABLE. TRADING LOCKED.</p>
        <div class="mt-8 px-6 py-3 border border-red-600 rounded bg-black/50 text-red-500 font-mono text-sm">CODE: TURNAROUND_SNIPER_LOCK</div>
    </div>
    <main id="main-content" class="pt-20 pb-10 px-4 max-w-7xl mx-auto transition-all duration-500">
        <div class="flex justify-between items-end mb-6 border-b border-gray-800 pb-2">
            <h2 class="text-lg font-semibold text-gray-300">Target Scans</h2>
            <span class="text-xs text-gray-500 font-mono" id="last-update">Waiting for Engine...</span>
        </div>
        <div id="card-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <div class="bg-gray-800 rounded-lg p-5 border border-gray-700 opacity-50 text-center py-12"><p class="text-gray-500 text-sm">Initializing Scanner Engine...</p></div>
        </div>
    </main>
    <script>
        const DATA_URL = './market_status.json'; 
        async function fetchMarketData() {
            try {
                const response = await fetch(DATA_URL + '?t=' + new Date().getTime());
                if (!response.ok) throw new Error("Data fetch failed");
                const data = await response.json();
                updateHUD(data); renderCards(data.targets || []); checkMarketDanger(data);
                document.getElementById('last-update').innerText = "Last Update: " + new Date().toLocaleTimeString();
            } catch (error) {
                console.error("Connection Error:", error);
                document.getElementById('system-badge').innerText = "OFFLINE";
                document.getElementById('system-badge').className = "px-2 py-0.5 rounded bg-red-900/50 border border-red-600 text-[10px] text-red-400 font-mono";
            }
        }
        function updateHUD(data) {
            const spyEl = document.getElementById('spy-val'); const vixEl = document.getElementById('vix-val');
            spyEl.innerText = data.spy_price ? `$${data.spy_price}` : "N/A";
            vixEl.innerText = data.vix ? data.vix : "N/A";
            if (data.vix >= 30) vixEl.className = "text-sm font-bold text-red-500 font-mono animate-pulse";
            else if (data.vix >= 20) vixEl.className = "text-sm font-bold text-yellow-400 font-mono";
            else vixEl.className = "text-sm font-bold text-blue-300 font-mono";
        }
        function checkMarketDanger(data) {
            const content = document.getElementById('main-content'); const overlay = document.getElementById('danger-overlay'); const badge = document.getElementById('system-badge');
            if (data.status === "DANGER") { content.classList.add('market-danger-blur'); overlay.style.display = 'flex'; badge.innerText = "DANGER"; badge.className = "px-2 py-0.5 rounded bg-red-600 text-[10px] text-white font-mono animate-pulse"; }
            else { content.classList.remove('market-danger-blur'); overlay.style.display = 'none'; badge.innerText = "SYSTEM ONLINE"; badge.className = "px-2 py-0.5 rounded bg-green-900/50 border border-green-600 text-[10px] text-green-400 font-mono"; }
        }
        function renderCards(targets) {
            const grid = document.getElementById('card-grid'); grid.innerHTML = '';
            if (targets.length === 0) { grid.innerHTML = `<div class="col-span-full text-center text-gray-500 py-10 font-mono">No Targets Detected. Scanner Sleeping.</div>`; return; }
            targets.forEach(item => {
                const card = document.createElement('div');
                card.className = "bg-gray-800 rounded-lg p-5 border border-gray-700 hover:border-blue-500 transition-colors shadow-lg";
                card.innerHTML = `<div class="flex justify-between items-start mb-4"><div><h3 class="text-xl font-bold text-white">${item.ticker}</h3><p class="text-xs text-gray-400">${item.sector || 'Unknown'}</p></div><span class="bg-blue-900/30 text-blue-300 px-2 py-1 rounded text-xs font-mono border border-blue-800">${item.rsi ? 'RSI: ' + item.rsi : 'Ready'}</span></div><div class="space-y-2"><div class="flex justify-between text-sm"><span class="text-gray-500">Price</span><span class="text-gray-200 font-mono">$${item.price}</span></div><div class="flex justify-between text-sm"><span class="text-gray-500">Volume</span><span class="text-gray-200 font-mono">${item.volume || 'N/A'}</span></div></div><div class="mt-4 pt-4 border-t border-gray-700"><button class="w-full bg-gray-700 hover:bg-blue-600 text-white text-sm py-2 rounded transition-colors">Analysis</button></div>`;
                grid.appendChild(card);
            });
        }
        fetchMarketData(); setInterval(fetchMarketData, 5000);
    </script>
</body>
</html>"""

log = []
target_file = "index.html"

# [1. 중복 제거: 방송실 착각 해결]
# 하위 디렉토리에 숨은 index.html을 찾아 제거 (루트 제외)
removed_count = 0
for root, dirs, files in os.walk("."):
    for file in files:
        if file == "index.html":
            full_path = os.path.join(root, file)
            # 현재 스크립트가 실행되는 루트의 index.html은 제외하고 삭제
            if os.path.abspath(full_path) != os.path.abspath(target_file):
                try:
                    os.remove(full_path)
                    log.append(f"[CLEANUP] Deleted rogue file: {full_path}")
                    removed_count += 1
                except Exception as e:
                    log.append(f"[ERROR] Could not delete {full_path}: {e}")

if removed_count == 0:
    log.append("[CLEANUP] No rogue index.html files found.")

# [2. 파일 생성: V13.2 HUD]
try:
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(html_source)
    log.append(f"[DEPLOY] V13.2 HUD successfully overwritten at: {os.path.abspath(target_file)}")
except Exception as e:
    log.append(f"[CRITICAL FAIL] Could not write index.html: {e}")

# [3. 로그 저장]
with open("out.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(log))
