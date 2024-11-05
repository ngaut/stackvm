FROM python:3.12

WORKDIR /app/

RUN pip install poetry poetry-plugin-export gunicorn

COPY pyproject.toml /app/pyproject.toml
COPY poetry.lock /app/poetry.lock

RUN poetry export -f requirements.txt --output requirements.txt --without-hashes
RUN pip install --no-cache-dir --upgrade -r requirements.txt
RUN mkdir -p /tmp/stack_vm/runtime/

ENV GIT_PYTHON_REFRESH=quiet
ENV PYTHONPATH=/app

COPY . /app/

CMD ["gunicorn", "-w", "16", "-b", "0.0.0.0:80", "-t", "300", "main:app"]