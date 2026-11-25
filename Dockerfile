FROM python:3.12-alpine

WORKDIR /app

COPY . .

# Game files are fetched at build time (too big for phone/GitHub web upload).
# fetch_build.py normalizes gzip/brotli CDN responses to plain content AND
# verifies every file's magic bytes, so a broken download fails the build
# instead of shipping corrupt JS. The brotli CLI decompresses compressed
# responses; gzip is handled by Python's stdlib.
RUN apk add --no-cache brotli && python3 fetch_build.py

ENV PORT=8080
EXPOSE 8080

CMD ["python3", "server.py"]
