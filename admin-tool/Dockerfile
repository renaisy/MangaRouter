FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY newapi_admin.py templates_presets.py app.py ./

RUN useradd -r -u 1000 app && chown -R app /app
USER app

EXPOSE 18503

CMD ["streamlit", "run", "app.py", \
     "--server.port=18503", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
