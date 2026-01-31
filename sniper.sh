#!/bin/bash
echo "🔥 MANUAL MISSION START..."
# 미션 수행
python scripts/run_v9_mission.py > out.txt 2>&1
# 대시보드 생성
python engine/dashboard.py >> out.txt 2>&1
# 방송국(gh-pages)으로 전송
git add .
git commit -m "Manual Update: $(date)" >> out.txt 2>&1
git push origin main:gh-pages --force >> out.txt 2>&1
echo "✅ DONE. Dashboard updated."
