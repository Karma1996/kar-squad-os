.PHONY: test check build

test:
	python3 -m unittest discover -s tests -v

check:
	python3 scripts/build_release.py --check
	python3 scripts/manifest.py check --manifest docs/examples/delivery-manifest.json --profile draft

build:
	python3 scripts/build_release.py
