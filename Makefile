VERSION = 1.1.0
IMAGE_NAME ?= wonkyto/techni-metrics-collector:$(VERSION)

build:
	docker build --target production -t $(IMAGE_NAME) .
build-pi:
	docker buildx build --target production --platform linux/arm64 -t $(IMAGE_NAME) --push .
build-all:
	docker buildx build --target production --platform linux/amd64,linux/arm64 -t $(IMAGE_NAME) --push .
lint:
	docker-compose run --rm lint
format:
	docker-compose run --rm format
run:
	docker-compose run --rm run
test:
	docker-compose run --rm test
pytest:
	docker-compose run --rm pytest
