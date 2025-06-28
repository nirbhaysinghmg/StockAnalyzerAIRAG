echo "Stopping any process on port 5002..."
lsof -ti:9000 | xargs -r kill -9


nohup python3 app.py > backend.log 2>&1 &
disown

echo "Backend Started (Logs -> backend.log)"
