db-reset:
	docker compose down -v
	docker compose up -d postgres
	docker compose up flyway
	docker compose run --rm flyway info
	docker compose up flyway