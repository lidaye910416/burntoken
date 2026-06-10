.PHONY: help install uninstall clean run models burntoken repl test lint

PY := python3
# 如果项目本地有 .venv/（装了 -r requirements-dev.txt），优先用它
# 这样 make test 不依赖系统 Python 装好 respx/pytest
ifeq (,$(wildcard .venv/bin/python))
  PYTHON := $(PY)
else
  PYTHON := .venv/bin/python
endif
ENV_FILE := .env

help:
	@echo "burntoken - hbscloud Token 燃烧器"
	@echo
	@echo "  make install    - 装依赖 + 加 PATH/alias"
	@echo "  make run MSG=.. - 单条调用"
	@echo "  make burn       - 批量烧（code preset，20 次，4 并发）"
	@echo "  make repl       - 交互 REPL"
	@echo "  make models     - 列出模型"
	@echo "  make test       - 跑 pytest 套件（tests_py/）"
	@echo "  make lint       - 跑代码风格检查（当前为 TODO 占位）"
	@echo "  make clean      - 清日志/缓存"

install:
	# 调项目根的 ./install.sh（装依赖 + 加 PATH/alias + 生成 .env）
	./install.sh

run:
	@test -n "$(MSG)" || (echo "用法: make run MSG=\"你的问题\""; exit 1)
	./bin/burntoken -p "$(MSG)"

burn:
	./bin/burntoken burn --preset code -n 20 -P 4

repl:
	./bin/burntoken --repl

models:
	./bin/burntoken --models

test:
	@PYTHONPATH=. $(PYTHON) -m pytest tests_py/ $(PYTEST_ARGS)

lint:
	@echo "TODO: 代码风格检查尚未接入。计划使用 ruff/flake8 扫描 burntoken/ 与 tests/。"
	@exit 0

clean:
	rm -rf logs/*.log __pycache__ */__pycache__ */*/__pycache__
