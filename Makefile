clean:
	rm -rf dist/*

patch: clean
	bumpversion patch
	poetry build
	poetry publish -r garena
