FROM python:3.11-slim

WORKDIR /app

COPY app.py .

# Folosim doar biblioteci standard Python — nu instalăm dependențe externe
EXPOSE 8080

ENV NF_TYPE=amf
ENV PORT=8080

# Health check pentru readinessProbe în K8s
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')" || exit 1

CMD ["python", "-u", "app.py"]
