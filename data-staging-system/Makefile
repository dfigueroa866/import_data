# Makefile for Data Staging System
.PHONY: help install run dev dashboard test clean setup

# Default Python command (try different options)
PYTHON := $(shell which python3 || which python)
PIP := $(shell which pip3 || which pip)

# Colors for output
GREEN := \033[0;32m
]
YELLOW := \033[1;33m
]
RED := \033[0;31m
]
BLUE := \033[0;34m
]
NC := \033[0m
]

help:
	@echo "$(GREEN)Data Staging System Commands$(NC)"
	@echo "================================"
	@echo ""
	@echo "$(YELLOW)Main Commands:$(NC)"
	@echo "  install     - Install the system and dependencies"
	@echo "  run         - Start the API server"
	@echo "  dev         - Start in development mode with auto-reload"
	@echo "  dashboard   - Start the Streamlit dashboard"
	@echo "  test-run    - Run tests"
	@echo "  clean       - Clean up cache files"
	@echo "  setup       - Complete setup including database"
	@echo ""
	@echo "$(YELLOW)Development:$(NC)"
	@echo "  check-deps  - Check if dependencies are installed"
	@echo "  install-dev - Install development dependencies"
	@echo ""

install:
	@echo "$(GREEN)📦 Installing Data Staging System...$(NC)"
	@if [ -z "$(PIP)" ]; then \
		echo "$(RED)❌ pip not found. Please install Python and pip first.$(NC)"; \
		echo "$(YELLOW)Try: brew install python (on macOS)$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Using pip: $(PIP)$(NC)"
	$(PIP) install -e .
	@echo "$(GREEN)✅ Installation complete!$(NC)"

install-deps:
	@echo "$(GREEN)📦 Installing dependencies only...$(NC)"
	@if [ -z "$(PIP)" ]; then \
		echo "$(RED)❌ pip not found. Please install Python and pip first.$(NC)"; \
		exit 1; \
	fi
	$(PIP) install -r requirements.txt
	@echo "$(GREEN)✅ Dependencies installed!$(NC)"

check-deps:
	@echo "$(BLUE)🔍 Checking dependencies...$(NC)"
	@$(PYTHON) -c "import sys; print(f'Python: {sys.version}')"
	@$(PYTHON) -c "import fastapi; print('✅ FastAPI available')\" 2>/dev/null || echo "❌ FastAPI missing"
	@$(PYTHON) -c "import pandas; print('✅ Pandas available')\" 2>/dev/null || echo "❌ Pandas missing"
	@$(PYTHON) -c "import sqlalchemy; print('✅ SQLAlchemy available')\" 2>/dev/null || echo "❌ SQLAlchemy missing"

run:
	@echo "$(GREEN)🚀 Starting Data Staging System API...$(NC)"
	@echo "$(BLUE)📍 API will be available at: http://localhost:8000$(NC)"
	@echo "$(BLUE)📚 API docs at: http://localhost:8000/docs$(NC)"
	@echo ""
	$(PYTHON) run_app.py

dev:
	@echo "$(GREEN)🔧 Starting in development mode...$(NC)"
	@echo "$(BLUE)📍 API will be available at: http://localhost:8000$(NC)"
	@echo "$(BLUE)📚 API docs at: http://localhost:8000/docs$(NC)"
	@echo ""
	$(PYTHON) -m uvicorn data_staging.api.main:app --reload --host 0.0.0.0 --port 8000

dashboard:
	@echo "$(GREEN)📊 Starting Dashboard...$(NC)"
	@echo "$(BLUE)📍 Dashboard will be available at: http://localhost:8501$(NC)"
	@echo ""
	$(PYTHON) run_dashboard.py

test-run:
	@echo "$(GREEN)🧪 Running tests...$(NC)"
	@if [ -d "tests" ]; then \
		$(PYTHON) -m pytest tests/ -v; \
	else \
		echo "$(YELLOW)⚠️  No tests directory found$(NC)"; \
	fi

clean:
	@echo "$(GREEN)🧹 Cleaning up...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)✅ Cleanup complete!$(NC)"

setup:
	@echo "$(GREEN)🚀 Complete setup...$(NC)"
	@$(MAKE) install-deps
	@if [ ! -f ".env" ]; then \
		if [ -f ".env.example" ]; then \
			cp .env.example .env; \
			echo "$(GREEN)✅ Created .env from .env.example$(NC)"; \
			echo "$(YELLOW)⚠️  Please edit .env with your database credentials$(NC)"; \
		fi \
	fi
	@echo "$(GREEN)🎉 Setup complete! Run 'make run' to start the system$(NC)"

# Alternative commands for different systems
install-mac:
	@echo "$(GREEN)🍎 Installing on macOS...$(NC)"
	@if ! command -v brew >/dev/null 2>&1; then \
		echo "$(RED)❌ Homebrew not found. Please install it first:$(NC)"; \
		echo "$(BLUE)/bin/bash -c \"\$$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"$(NC)"; \
		exit 1; \
	fi
	brew install python
	python3 -m pip install -e .

install-ubuntu:
	@echo "$(GREEN)🐧 Installing on Ubuntu...$(NC)"
	sudo apt update
	sudo apt install -y python3 python3-pip
	python3 -m pip install -e .

# Show system info
info:
	@echo "$(GREEN)ℹ️  System Information$(NC)"
	@echo "======================"
	@echo "Python: $(PYTHON)"
	@echo "Pip: $(PIP)"
	@echo "OS: $$(uname -s)"
	@echo "Working Directory: $$(pwd)"
	@echo ""
	@$(MAKE) check-deps