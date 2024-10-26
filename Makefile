.PHONY: test

makemigrations:
	@echo "Creating migrations..."
	@if [ -z "$(NAME)" ]; then \
		poetry run alembic revision --autogenerate; \
	else \
		poetry run alembic revision --autogenerate -m "$(NAME)"; \
	fi

migrate:
	@echo "Migrating database..."
	@poetry run alembic upgrade head