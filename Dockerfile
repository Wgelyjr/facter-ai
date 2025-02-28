FROM python:3.13

WORKDIR /app

COPY src/requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY src/ /app/

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:app", "--timeout", "600"]