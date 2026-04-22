FROM python:3.12-alpine AS builder

WORKDIR /app
RUN apk add --no-cache gcc musl-dev libffi-dev
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.12-alpine AS production

RUN addgroup -S appgroup && adduser -S appuser -G appgroup
WORKDIR /app

COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

COPY . .

USER appuser

EXPOSE 8000