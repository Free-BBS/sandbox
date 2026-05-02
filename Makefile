.PHONY: install build run dev test

install:
	python -m pip install -r requirements.txt

build:
	docker build -t freebbs-sandbox-runner:latest sandbox_image

run:
	uvicorn app.main:app --host 127.0.0.1 --port 8000

dev:
	uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

test:
	python -m compileall app sandbox_image
