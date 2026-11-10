.PHONY: test check build generate

test:
	python3 -m unittest discover -s tests -v

generate:
	python3 scripts/generate.py --write

check:
	python3 scripts/generate.py --check
	python3 scripts/build_release.py --check
	python3 scripts/manifest.py check --manifest docs/examples/delivery-manifest.json --profile draft
	python3 scripts/policy.py check --manifest docs/examples/delivery-manifest.json --profile h3
	python3 scripts/policy.py check --manifest docs/examples/low-risk-manifest.json --profile h3
	python3 scripts/autonomy.py check --manifest docs/examples/low-risk-manifest.json --profile h3
	python3 scripts/queue.py check --queue docs/examples/queue.json

build:
	python3 scripts/build_release.py
