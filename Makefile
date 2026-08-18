PY = ./.venv/Scripts/python.exe

.PHONY: demo demo-fast poc poc-fast diagram freeze

demo:           ## LIVE DEMO target: real deberta filter, fully offline, no noise
	HF_HUB_OFFLINE=1 $(PY) poc_bypass.py

demo-fast:      ## Fallback if anything is wrong with the model cache (~5s)
	HF_HUB_OFFLINE=1 $(PY) poc_bypass.py --fast

poc:            ## Same as demo but allowed to reach the network (first run)
	$(PY) poc_bypass.py

poc-fast:
	$(PY) poc_bypass.py --fast

diagram:        ## docs/architecture.mmd -> png (needs npx @mermaid-js/mermaid-cli)
	npx -y @mermaid-js/mermaid-cli -i docs/architecture.mmd -o docs/architecture.png -b white -w 1600

freeze:
	$(PY) -m pip freeze > requirements-lock.txt
