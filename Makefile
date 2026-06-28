PYTHON ?= python3
VENV ?= .venv
VENVPY ?= $(VENV)/bin/python
PIP ?= $(VENV)/bin/pip
DEV_AUTH_TOKENS_JSON ?= {"operator-token":{"actor_id":"operator","permission_scopes":["read_only","query","confirm","dataset_write","review_admin","warehouse_admin","diagnostics"]},"agent-token":{"actor_id":"agent","permission_scopes":["read_only","query","confirm"]}}

.PHONY: bootstrap test quality pilot operator-trial demo agent-acceptance release-check serve serve-user macos-app macos-dmg windows-zip frontend frontend-user-build clean-artifacts

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

operator-trial:
	$(VENVPY) scripts/run_operator_trial.py --fixture

demo:
	$(VENVPY) scripts/run_demo_acceptance.py

agent-acceptance:
	$(VENVPY) scripts/run_agent_tool_acceptance.py

release-check:
	$(VENVPY) scripts/validate_release_package.py

serve:
	@if [ -z "$$AUTH_TOKENS_JSON" ]; then \
		export AUTH_TOKENS_JSON='$(DEV_AUTH_TOKENS_JSON)'; \
		$(VENVPY) -m uvicorn src.api.server:app --reload --port 8001; \
	else \
		$(VENVPY) -m uvicorn src.api.server:app --reload --port 8001; \
	fi

serve-user:
	$(VENVPY) scripts/run_local_user_web.py

macos-app:
	$(VENVPY) scripts/build_local_user_app.py

macos-dmg:
	$(VENVPY) scripts/build_internal_macos_dmg.py

windows-zip:
	$(VENVPY) scripts/build_internal_windows_zip.py

frontend:
	@if [ -d frontend ] && [ -f frontend/package.json ]; then \
		cd frontend && npm run build; \
	else \
		echo "frontend/package.json not found; skipped"; \
	fi

frontend-user-build:
	cd frontend-user && npm install && npm run build

clean-artifacts:
	find src scripts tests -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
	find src scripts tests -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
	rm -f .DS_Store
	rm -f outputs/eval/*.audit_tmp.json
	rm -rf outputs/tool_audit
	rm -rf outputs/answer_demo
	find outputs/mvp_demo -type f ! -name 'AGENTS.override.md' -delete 2>/dev/null || true
	rm -f outputs/quality_gate/report.json
	rm -f outputs/quality_gate/report.md
	rm -rf outputs/quality_gate/tmp
	rm -rf outputs/quality_gate/warehouses
	rm -rf outputs/demo_acceptance/uploaded_datasets
	rm -rf outputs/demo_acceptance/uploaded_sources
	rm -rf outputs/demo_acceptance/warehouses
	rm -rf outputs/operator_trial
	rm -rf outputs/tool_manifest
	rm -rf outputs/openapi
	rm -rf outputs/agent_tool_acceptance
	rm -rf outputs/release_package
	rm -f outputs/tool_audit/test_audit.jsonl
