PYTHON ?= python3
VENV ?= .venv
VENVPY ?= $(VENV)/bin/python
PIP ?= $(VENV)/bin/pip

.PHONY: bootstrap test quality pilot demo agent-acceptance serve frontend clean-artifacts

bootstrap:
	@if [ ! -x "$(VENVPY)" ]; then $(PYTHON) -m venv $(VENV); fi
	$(VENVPY) -m pip install --upgrade pip
	$(PIP) install -r requirements.txt

test:
	$(VENVPY) -m unittest discover -s tests

quality:
	$(VENVPY) scripts/run_quality_gate.py

pilot:
	$(VENVPY) scripts/run_real_dataset_pilot.py --fixture

demo:
	$(VENVPY) scripts/run_demo_acceptance.py

agent-acceptance:
	$(VENVPY) scripts/run_agent_tool_acceptance.py

serve:
	$(VENVPY) -m uvicorn src.api.server:app --reload --port 8001

frontend:
	@if [ -d frontend ] && [ -f frontend/package.json ]; then \
		cd frontend && npm run build; \
	else \
		echo "frontend/package.json not found; skipped"; \
	fi

clean-artifacts:
	rm -f outputs/eval/*.audit_tmp.json
	rm -rf outputs/quality_gate/tmp
	rm -rf outputs/quality_gate/warehouses
	rm -rf outputs/demo_acceptance/uploaded_datasets
	rm -rf outputs/demo_acceptance/uploaded_sources
	rm -rf outputs/demo_acceptance/warehouses
	rm -rf outputs/tool_manifest
	rm -rf outputs/openapi
	rm -rf outputs/agent_tool_acceptance
	rm -f outputs/tool_audit/test_audit.jsonl
