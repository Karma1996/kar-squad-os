.PHONY: test check build

test:
	python3 -m unittest discover -s tests -v

check:
	python3 scripts/build_release.py --check

build:
	python3 scripts/build_release.py
