$ProjectPath = $PSScriptRoot
Set-Location $ProjectPath

$Python = Join-Path $ProjectPath "venv\Scripts\python.exe"
$SessionName = "mibox"

psmux kill-session -t $SessionName 2>$null

psmux new-session -d -s $SessionName

psmux split-window -h -t "$SessionName:0"

psmux split-window -v -t "$SessionName:0"

psmux split-window -v -t "$SessionName:1"

psmux select-layout -t $SessionName tiled

psmux send-keys -t "$SessionName:0" "'$Python' script.py" Enter
Start-Sleep -Milliseconds 1000
psmux send-keys -t "$SessionName:0" "1" Enter

psmux send-keys -t "$SessionName:1" "'$Python' script.py" Enter
Start-Sleep -Milliseconds 1000
psmux send-keys -t "$SessionName:1" "2" Enter

psmux send-keys -t "$SessionName:2" "'$Python' script.py" Enter
Start-Sleep -Milliseconds 1000
psmux send-keys -t "$SessionName:2" "3" Enter

psmux send-keys -t "$SessionName:3" "'$Python' script.py" Enter
Start-Sleep -Milliseconds 1000
psmux send-keys -t "$SessionName:3" "4" Enter

psmux attach-session -t $SessionName
