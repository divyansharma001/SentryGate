PY = ./.venv/Scripts/python.exe

.PHONY: demo demo-fast poc poc-fast capture diagram deck present freeze

demo:           ## LIVE DEMO target: real deberta filter, fully offline, no noise
	HF_HUB_OFFLINE=1 $(PY) poc_bypass.py

demo-fast:      ## Fallback if anything is wrong with the model cache (~5s)
	HF_HUB_OFFLINE=1 $(PY) poc_bypass.py --fast

poc:            ## Same as demo but allowed to reach the network (first run)
	$(PY) poc_bypass.py

poc-fast:
	$(PY) poc_bypass.py --fast

capture:        ## Re-record the run the deck quotes from
	HF_HUB_OFFLINE=1 $(PY) poc_bypass.py > docs/captures/demo-output.txt 2>&1
	sed -i 's/\r$$//' docs/captures/demo-output.txt

diagram:        ## mermaid sources -> png, light for print + dark for the deck
	npx -y @mermaid-js/mermaid-cli -i docs/problem.mmd      -o docs/problem.png      -b white -w 1800
	npx -y @mermaid-js/mermaid-cli -i docs/architecture.mmd -o docs/architecture.png -b white -w 1800
	npx -y @mermaid-js/mermaid-cli -i docs/problem.mmd      -o docs/captures/problem-dark.png      -t dark -b transparent -w 2000
	npx -y @mermaid-js/mermaid-cli -i docs/architecture.mmd -o docs/captures/architecture-dark.png -t dark -b transparent -w 2000

deck:           ## Rebuild docs/deck.html from the template + the captured run
	$(PY) docs/build_deck.py

present:        ## Serve the deck at http://127.0.0.1:8777/deck.html
	@echo "Open http://127.0.0.1:8777/deck.html  (Ctrl-C to stop)"
	cd docs && $(CURDIR)/.venv/Scripts/python.exe -m http.server 8777 --bind 127.0.0.1

freeze:
	$(PY) -m pip freeze > requirements-lock.txt
