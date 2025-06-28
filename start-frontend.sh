cd ~/StocksAI || {
  echo "Directory ~/StocksAI not found. Aborting."
  exit 1
}

# 2) Kill any existing process listening on port 5000
echo "Stopping any process on port 5002..."
lsof -ti:5002 | xargs -r kill -9

# 3) Start the static server on port 5000, detach it, and log output
nohup npx serve frontend -l 5002 > serve.log 2>&1 &

# 4) Prevent it from being killed when you close the SSH session
disown

echo "Frontend server restarted on port 5002 (logs → serve.log)"