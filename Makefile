VERSION = 1.0.2
IMAGE_NAME ?= wonkyto/techni-metrics-collector:$(VERSION)

build:
	docker build -t $(IMAGE_NAME) .
flake8:
	docker-compose run --rm flake8
run:
	docker-compose run --rm run
test:
	docker-compose run --rm test
