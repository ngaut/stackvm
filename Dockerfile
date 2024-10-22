FROM python:3.12 as requirements-stage

WORKDIR /tmp

RUN pip install poetry

COPY ./pyproject.toml ./poetry.lock* /tmp/

RUN poetry export -f requirements.txt --output requirements.txt --without-hashes

FROM python:3.12

WORKDIR /code

COPY --from=requirements-stage /tmp/requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
RUN pip install "fastapi[all]" uvicorn

COPY ./main.py /code/main.py
COPY ./spec.md /code/spec.md
COPY ./static /code/static
COPY ./templates /code/templates
COPY ./tools /code/tools
COPY ./plan_example.md /code/plan_example.md
COPY ./app /code/app
COPY ./tools /code/tools

RUN mkdir -p /tmp/stack_vm/runtime/

EXPOSE 80

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80", "--log-level", "debug"]