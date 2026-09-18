# Oluso developer tasks. Run `make help` for the list.
# Windows without GNU make: run the equivalent commands listed in CONTRIBUTING.md.

PYTHON ?= python
SCRATCH ?= $(TMPDIR)
export PYTHONDONTWRITEBYTECODE = 1

.DEFAULT_GOAL := help

.PHONY: help install lint test coverage check serve dashboard \
        data train evaluate robustness redteam bench load evidence \
        demo-video writeup package smoke sbom clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install the package with dev and dashboard extras (editable)
	$(PYTHON) -m pip install -e '.[dev,dashboard]'

lint: ## Static checks (ruff)
	ruff check .

test: ## Unit and integration tests
	pytest

coverage: ## Tests with the CI coverage gate
	pytest --cov=oluso --cov-fail-under=85

check: lint coverage smoke ## Everything CI runs, locally

serve: ## Run the API on :8000 with reload
	uvicorn app:app --reload --port 8000

dashboard: ## Run the Streamlit investigator console on :8501
	streamlit run dashboard/app.py

# ---- Model lifecycle -------------------------------------------------------
data: ## Regenerate the synthetic corpus (data/*.csv)
	$(PYTHON) scripts/generate_synthetic.py

train: ## Train the calibrated population model (models/ato_model.joblib)
	$(PYTHON) scripts/train_model.py

evaluate: ## Full runtime evaluation with intervals, ablation and attribution
	$(PYTHON) scripts/evaluate_system.py

robustness: ## Account-disjoint, separability and coverage-leakage gates
	$(PYTHON) scripts/evaluate_robustness.py

redteam: ## Constrained adaptive-attacker search
	$(PYTHON) scripts/adaptive_attack_search.py

bench: ## Warm sequential API latency
	$(PYTHON) scripts/benchmark_latency.py --requests 100

load: ## Eight-worker concurrent load (keep the scratch DB off synced folders)
	$(PYTHON) scripts/load_test.py --database $(if $(SCRATCH),$(SCRATCH)/oluso_load.db,artifacts/load_test.db)

evidence: evaluate robustness bench load ## Regenerate all machine-readable evidence in artifacts/

# ---- Submission ------------------------------------------------------------
demo-video: ## Rebuild the captioned demo MP4 and demo_results.json (needs ffmpeg + pillow)
	$(PYTHON) tools/build_demo_video.py --output submission/demo

writeup: ## Rebuild the technical write-up DOCX from current evidence (needs python-docx)
	$(PYTHON) tools/build_technical_writeup.py --output submission/report/Oluso_TrackA_Technical_Writeup.docx

smoke: ## Boot a clean staged copy from .env.example and require /health == 200
	$(PYTHON) scripts/release_smoke_test.py .

sbom: ## CycloneDX SBOM into artifacts/
	$(PYTHON) scripts/generate_sbom.py

package: ## Assemble the judge-facing package into submission/dist/
	$(PYTHON) tools/package_submission.py

clean: ## Remove caches and runtime databases (keeps versioned evidence)
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov build dist src/*.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -f data/*.db data/*.db-wal data/*.db-shm artifacts/load_test.db* artifacts/v5_demo.db* artifacts/agent_terminal_demo.db* artifacts/v1_platform_demo.db*
