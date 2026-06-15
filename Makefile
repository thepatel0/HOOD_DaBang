.PHONY: test test-v initdb clean

# Phase 0 bedrock — pure stdlib, no installs required.
test:
	PYTHONPATH=. python3 -m unittest discover -s tests -t .

test-v:
	PYTHONPATH=. python3 -m unittest discover -s tests -t . -v

initdb:
	PYTHONPATH=. python3 -c "from src import db; db.init_db('data/trader.db'); db.init_ledger('data/llm_ledger.db'); print('db ready')"

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -f data/trader.db data/trader.db-wal data/trader.db-shm
	rm -f data/llm_ledger.db data/llm_ledger.db-wal data/llm_ledger.db-shm
