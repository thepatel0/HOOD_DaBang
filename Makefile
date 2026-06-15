# HOOD DaBang — canonical interpreter is the 3.13 venv (numpy/pandas/sklearn/hmmlearn).
# The Phase 0/0b bedrock is pure stdlib and also runs under any python3.
PY ?= .venv/bin/python

.PHONY: test test-v initdb clean

test:
	PYTHONPATH=. $(PY) -m unittest discover -s tests -t .

test-v:
	PYTHONPATH=. $(PY) -m unittest discover -s tests -t . -v

initdb:
	PYTHONPATH=. $(PY) -c "from src import db; db.init_db('data/trader.db'); db.init_ledger('data/llm_ledger.db'); print('db ready')"

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -f data/trader.db data/trader.db-wal data/trader.db-shm
	rm -f data/llm_ledger.db data/llm_ledger.db-wal data/llm_ledger.db-shm
